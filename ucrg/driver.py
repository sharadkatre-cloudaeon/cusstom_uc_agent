"""UCRGAgent — a framework-light orchestrator that runs the exact node logic
from the LangGraph design as a simple start()/send() loop. This is what the CLI
uses, so the project runs and is testable with no extra runtime.

graph.py provides the equivalent LangGraph StateGraph for production.
"""
import json
import re
from dataclasses import asdict

from .state import UCRGState
from .engine import form_questions, segment_label, lookup_followups
from .classify import classify_use_case, is_firm
from .gate import gate_inputs_from, run_decision_gate
from .compose import compose_output
from .llm import make_llm, is_not_sure

GREETING = ("Hi! Tell me about the idea you'd like to register and I'll ask a few "
            "questions so the build team has everything they need. You can always say "
            "\"not sure\" and I'll flag it for the technical team.")


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
        # "not sure" handling on follow-ups: rephrase once, then tag and move on
        if q["kind"] == "followup" and is_not_sure(user_text):
            self.s.attempts[q["id"]] = self.s.attempts.get(q["id"], 0) + 1
            if self.s.attempts[q["id"]] < 2:
                text = self.llm.phrase(q["text"], simpler=True)
                self._current = {**q, "kind": "rephrase"}
                self.s.transcript.append(("agent", text))
                return {"message": text, "done": False}
            self._tag_open_item(q)             # give up gracefully -> open item
        else:
            self._record(q, user_text)

        nxt = self._advance()
        self.s.transcript.append(("agent", nxt["message"]))
        return nxt

    # -- internals ------------------------------------------------------
    def _load_segment(self, seg: int):
        self._std = [{"id": fq["id"], "text": fq["question"], "kind": "standard"}
                     for fq in form_questions(seg)]
        self._fu = []

    def _next_question(self):
        if self._fu:
            q = self._fu.pop(0)
        elif self._std:
            q = self._std.pop(0)
        else:
            return None
        self._current = q
        return self.llm.phrase(q["text"], simpler=(q["kind"] == "rephrase"))

    def _record(self, q, text):
        self.s.answers[q["id"]] = text
        self.s.signals.update(self.llm.extract_signals(q["id"], q["text"], text))
        self.s.classification = classify_use_case(self.s.signals)
        # refresh follow-ups when the segment's standard questions are exhausted
        if q["kind"] == "standard" and not self._std:
            self._refresh_followups()

    def _refresh_followups(self):
        if not is_firm(self.s.classification):
            return
        p = self.s.classification["primary"]
        activated = lookup_followups(p["domain"], p["level"])
        # queue business-answerable follow-ups whose home segment is the current one
        for item in activated["ask"]:
            if item["id"] in self.s.asked_followup_ids:
                continue
            if self.s.current_segment in _segments_in(item["asked_in"]):
                self.s.asked_followup_ids.add(item["id"])
                self._fu.append({"id": item["id"], "text": item["question"], "kind": "followup"})
        # tag technical items into the open-items register (deduped)
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

        # segment exhausted -> next segment, or finish
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
