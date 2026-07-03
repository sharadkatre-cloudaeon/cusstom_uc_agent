"""LLM abstraction.

Two backends:
  - MockLLM      : zero-dependency, offline. Phrases the canned plain questions and
                   interprets answers with keyword rules. Lets the whole flow + engine
                   + gate be tested with no API key.
  - AnthropicLLM : uses the `anthropic` SDK + ANTHROPIC_API_KEY when you want real
                   natural-language phrasing and extraction.

The agent logic (driver/graph) is identical for both — only the text understanding differs.
"""
from __future__ import annotations
import json
import os
import re


# ----------------------------------------------------------------------
# keyword interpretation shared by MockLLM (and a sane fallback for the real LLM)
# ----------------------------------------------------------------------
_YES = ("yes", "yeah", "yep", "correct", "true", "definitely", "absolutely", "we do", "it does")
_NO = ("no", "nope", "not really", "none", "n/a", "we don't", "it doesn't")
_NOT_SURE = ("not sure", "don't know", "dont know", "dunno", "no idea", "unsure", "maybe", "skip", "idk")


def is_yes(t: str) -> bool:
    t = t.lower()
    return any(w in t for w in _YES) and not any(w in t for w in _NO)


def is_not_sure(t: str) -> bool:
    return any(w in t.lower() for w in _NOT_SURE)


def keyword_signals(qid: str, text: str) -> dict:
    """Map a free-text answer to gate/classification signals. Best-effort, deterministic."""
    t = text.lower()
    s: dict = {}
    if qid == "Q5":
        s["impact"] = "high" if (is_yes(t) or any(w in t for w in
                      ("customer", "eligibility", "pricing", "hiring", "complaint", "public"))) else "low"
        if any(w in t for w in ("eligibility", "pricing", "hiring", "credit", "health")):
            s["regulated"] = True
    elif qid == "Q6":
        s["fairness_risk"] = is_yes(t)
    elif qid == "Q8":
        s["action"] = "act" if any(w in t for w in ("act", "itself", "change", "execute", "take action", "automatically")) else "suggest"
    elif qid == "Q9":
        s["logic"] = "judgement" if any(w in t for w in ("judg", "messy", "varied", "decide", "interpret")) else "rules"
    elif qid == "Q10":
        s["steps"] = "multi" if any(w in t for w in ("multi", "several", "steps", "plan", "workflow", "recover", "chain")) else "single"
    elif qid == "Q11":
        if any(w in t for w in ("create", "generate", "draft", "write", "summar", "content", "image", "compose")):
            s["domain_hint"] = "GA"
        elif any(w in t for w in ("analyse", "analyze", "predict", "forecast", "score", "trend", "insight", "report", "dashboard")):
            s["domain_hint"] = "DS"
            if any(w in t for w in ("dashboard", "report")): s["analytics_kind"] = "dashboard"
            elif any(w in t for w in ("predict", "forecast")): s["analytics_kind"] = "predict"
            elif any(w in t for w in ("recommend", "optimi")): s["analytics_kind"] = "recommend"
        elif any(w in t for w in ("move", "process", "transfer", "route", "data")):
            s["domain_hint"] = "AU"
    elif qid == "Q13":
        if is_no(t):
            s["sensitivity"] = "none"
        elif is_yes(t) or any(w in t for w in ("personal", "customer", "email", "name", "address", "confidential")):
            s["sensitivity"] = "special" if any(w in t for w in ("health", "financial", "biometric", "special")) else "personal"
    elif qid == "Q14":
        s["needs_knowledge"] = is_yes(t)
    elif qid == "Q15":
        s["writes"] = any(w in t for w in ("write", "change", "update", "create record", "modify", "delete")) and "read only" not in t and "read-only" not in t
        s["multi_system"] = any(w in t for w in ("multiple", "several", "systems", "other system", "various"))
    elif qid == "Q16":
        s["sharing"] = (not is_no(t)) and (is_yes(t) or any(w in t for w in ("vendor", "third", "external", "other department", "partner")))
    elif qid == "Q17":
        s["hitl"] = "auto" if any(w in t for w in ("own", "alone", "automatic", "without")) else "human"
    elif qid == "Q19":
        s["regulated"] = bool(t.strip()) and not is_not_sure(t) and not is_no(t) and any(
            w in t for w in ("law", "regul", "gdpr", "hipaa", "compliance", "policy", "pci", "act"))
    elif qid == "Q22":
        s["impact_failure"] = "high" if any(w in t for w in ("serious", "major", "critical", "severe")) else "low"
    return s


def is_no(t: str) -> bool:
    t = t.lower()
    return any(w in t for w in _NO)


class MockLLM:
    name = "mock"

    def phrase(self, question_text: str, simpler: bool = False) -> str:
        if simpler:
            return "Let me put that more simply — " + question_text
        return question_text

    def extract_signals(self, qid: str, question_text: str, answer_text: str) -> dict:
        return keyword_signals(qid, answer_text)


class AnthropicLLM:
    """Real backend. Requires `pip install anthropic` and ANTHROPIC_API_KEY."""
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", system_prompt: str = ""):
        import anthropic  # lazy
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.system = system_prompt

    def phrase(self, question_text: str, simpler: bool = False) -> str:
        instr = ("Rephrase this intake question for a non-technical business user, "
                 "even more simply, one short sentence:" if simpler else
                 "Ask this intake question naturally to a non-technical business user, one short sentence:")
        msg = self.client.messages.create(
            model=self.model, max_tokens=120, system=self.system,
            messages=[{"role": "user", "content": f"{instr}\n\n{question_text}"}])
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    def extract_signals(self, qid: str, question_text: str, answer_text: str) -> dict:
        schema_hint = ("Return ONLY a JSON object of relevant signals among: domain_hint(GA/DS/AA/AU), "
                       "action(act/suggest), logic(judgement/rules), steps(multi/single), needs_knowledge(bool), "
                       "impact(high/medium/low), fairness_risk(bool), sensitivity(special/personal/none), "
                       "writes(bool), multi_system(bool), sharing(bool), hitl(human/auto), regulated(bool), "
                       "analytics_kind(dashboard/diagnose/predict/recommend/adaptive). Omit keys you can't infer.")
        msg = self.client.messages.create(
            model=self.model, max_tokens=200, system=self.system,
            messages=[{"role": "user", "content":
                       f"Question ({qid}): {question_text}\nUser answer: {answer_text}\n\n{schema_hint}"}])
        raw = "".join(b.text for b in msg.content if b.type == "text")
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return keyword_signals(qid, answer_text)  # fall back to keywords


def make_llm(backend: str = "mock", system_prompt: str = ""):
    if backend == "anthropic":
        return AnthropicLLM(system_prompt=system_prompt)
    return MockLLM()
