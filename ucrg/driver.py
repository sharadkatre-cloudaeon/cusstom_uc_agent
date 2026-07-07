"""UCRGAgent — a framework-light orchestrator that runs the exact node logic
from the LangGraph design as a simple start()/send() loop. This is what the CLI
uses, so the project runs and is testable with no extra runtime.

graph.py provides the equivalent LangGraph StateGraph for production.
"""
import json
import re
from dataclasses import asdict

from .state import UCRGState
from .engine import form_questions, question_dict, segment_label, lookup_followups
from .classify import classify_use_case, is_firm
from .gate import gate_inputs_from, run_decision_gate
from .compose import compose_output
from .answer_options import normalize_user_answer
from .context import (
    FRIENDLY_Q1,
    _PHRASE_SKIP_IDS,
    build_phrase_context,
    derive_from_transcript,
    mark_skipped,
    should_ask,
    suggest_dynamic_options,
)
from .llm import make_llm, is_not_sure

GREETING = (
    "Hi! I'll ask a few simple questions about your idea so the build team "
    "knows exactly what to create. You can always say \"not sure\" and I'll "
    "flag it for the technical team."
)


def _segments_in(asked_in: str) -> set:
    return set(int(n) for n in re.findall(r"Seg\s*(\d)", asked_in or ""))


class UCRGAgent:
    def __init__(self, backend: str = "mock", system_prompt: str = ""):
        self.llm = make_llm(backend, system_prompt)
        self.s = UCRGState()
        self._std: list = []        # remaining standard questions for current segment
        self._fu: list = []         # remaining follow-ups for current segment
        self._current = None        # the question dict awaiting an answer

    # -- public API -----------------------------------------------------
    def start(self) -> str:
        self.s.current_segment = 1
        self._load_segment(1)
        first = self._next_question()
        msg = GREETING + "\n\n" + first
        self.s.transcript.append(("agent", msg))
        return msg

    def send(self, user_text: str) -> dict:
        self.s.transcript.append(("user", user_text))
        if self.s.done or self._current is None:
            return {"message": "(conversation already complete)", "done": True}

        q = self._current
        # duplicate submit guard — same question already answered
        if q["id"] in self.s.answers and q["kind"] != "rephrase":
            nxt = self._advance()
            self.s.transcript.append(("agent", nxt["message"]))
            return nxt

        # "not sure" handling on follow-ups: rephrase once, then tag and move on
        if q["kind"] == "followup" and is_not_sure(user_text):
            self.s.attempts[q["id"]] = self.s.attempts.get(q["id"], 0) + 1
            if self.s.attempts[q["id"]] < 2:
                text = self._phrase_question({**q, "kind": "rephrase"})
                self._current = {**q, "kind": "rephrase", "display_text": text}
                self.s.transcript.append(("agent", text))
                return {"message": text, "done": False}
            self._tag_open_item(q)
        else:
            self._record(q, user_text)

        nxt = self._advance()
        self.s.transcript.append(("agent", nxt["message"]))
        return nxt

    # -- internals ------------------------------------------------------
    def _load_segment(self, seg: int):
        self._std = [question_dict(fq) for fq in form_questions(seg)]
        self._fu = []

    def _pop_next_raw(self) -> dict | None:
        if self._fu:
            return self._fu.pop(0)
        if self._std:
            return self._std.pop(0)
        return None

    def _next_question(self) -> str | None:
        while True:
            q = self._pop_next_raw()
            if q is None:
                self._current = None
                return None
            if not should_ask(q, self.s, self.llm):
                mark_skipped(self.s, q["id"], "already covered from earlier answers")
                continue
            text = self._phrase_question(q)
            self._current = {**q, "display_text": text}
            self._attach_dynamic_options(self._current)
            return text

    def _attach_dynamic_options(self, q: dict):
        dyn = suggest_dynamic_options(q["id"], self.s)
        if dyn:
            self.s.dynamic_options[q["id"]] = dyn
            q["dynamic_options"] = dyn
        elif q["id"] in self.s.dynamic_options:
            q["dynamic_options"] = self.s.dynamic_options[q["id"]]

    def _phrase_question(self, q: dict) -> str:
        cache_key = f"{q['id']}:{q['kind']}"
        cached = self.s.phrased_questions.get(cache_key)
        if cached:
            return cached

        simpler = q["kind"] == "rephrase"
        if q["id"] in _PHRASE_SKIP_IDS and q["kind"] == "standard":
            base = FRIENDLY_Q1 if q["id"] == "Q1" else q["text"]
        else:
            context = build_phrase_context(self.s)
            base = self.llm.phrase(
                q["text"],
                simpler=simpler,
                options=q.get("options"),
                context=context or None,
            )
            if base == q["text"] and context and not simpler:
                base = self.llm.phrase(q["text"], simpler=simpler, options=q.get("options"))

        self.s.phrased_questions[cache_key] = base
        return base

    def _record(self, q, text):
        answer = normalize_user_answer(q["id"], text)
        self.s.answers[q["id"]] = answer
        self.s.signals.update(self.llm.extract_signals(q["id"], q["text"], answer))
        derive_from_transcript(self.s)
        self.s.classification = classify_use_case(self.s.signals)
        if q["kind"] == "standard" and not self._std:
            self._refresh_followups()

    def _refresh_followups(self):
        if not is_firm(self.s.classification):
            return
        p = self.s.classification["primary"]
        activated = lookup_followups(
            p["domain"],
            p["level"],
            answers=self.s.answers,
            signals=self.s.signals,
        )
        for item in activated["ask"]:
            if item["id"] in self.s.asked_followup_ids:
                continue
            if self.s.current_segment in _segments_in(item["asked_in"]):
                self.s.asked_followup_ids.add(item["id"])
                self._fu.append({
                    "id": item["id"],
                    "text": item["question"],
                    "kind": "followup",
                    "answer_type": "Text",
                    "options": None,
                })
        seen = {o["id"] for o in self.s.open_items}
        for item in activated["tag"]:
            if item["id"] not in seen:
                self.s.open_items.append(item)
                seen.add(item["id"])

    def _tag_open_item(self, q):
        if q["id"] not in {o["id"] for o in self.s.open_items}:
            self.s.open_items.append({"id": q["id"], "open_item": q["text"], "area": "—",
                                      "parent": "", "note": "user unsure"})

    def _advance(self) -> dict:
        nxt = self._next_question()
        if nxt is not None:
            return {"message": nxt, "done": False}

        self.s.current_segment += 1
        if self.s.current_segment > 7:
            return self._finalize()
        self._load_segment(self.s.current_segment)
        self._refresh_followups()
        intro = f"\n— {segment_label(self.s.current_segment)} —\n"
        return {"message": intro + (self._next_question() or ""), "done": False}

    def _finalize(self) -> dict:
        inputs = gate_inputs_from(self.s.signals, self.s.classification)
        self.s.gate_verdict = run_decision_gate(inputs)
        self.s.output = compose_output(self.s)
        self.s.done = True
        self._current = None
        p = self.s.classification.get("primary", {})
        summary = (f"Thanks — I have everything I need.\n"
                   f"(Internal) classified as {p.get('domain_name')} L{p.get('level')}; "
                   f"gate verdict: {self.s.gate_verdict.get('verdict')}; "
                   f"{len(self.s.open_items)} items tagged for the technical team.")
        return {"message": summary, "done": True, "output": self.s.output}

    # -- session serialization (stateless serving) ----------------------
    def dump_session(self) -> dict:
        state = asdict(self.s)
        state["asked_followup_ids"] = sorted(self.s.asked_followup_ids)
        state["skipped_ids"] = sorted(self.s.skipped_ids)
        return {
            "state": state,
            "_std": self._std,
            "_fu": self._fu,
            "_current": self._current,
        }

    @classmethod
    def load_session(cls, blob: dict, backend: str = "mock", system_prompt: str = "") -> "UCRGAgent":
        agent = cls(backend=backend, system_prompt=system_prompt)
        state = dict(blob["state"])
        state["asked_followup_ids"] = set(state.get("asked_followup_ids") or [])
        state["skipped_ids"] = set(state.get("skipped_ids") or [])
        agent.s = UCRGState(**state)
        agent._std = blob.get("_std") or []
        agent._fu = blob.get("_fu") or []
        agent._current = blob.get("_current")
        return agent

    @staticmethod
    def dumps_session(blob: dict) -> str:
        return json.dumps(blob, ensure_ascii=False)

    @staticmethod
    def loads_session(raw: str) -> dict:
        return json.loads(raw)
