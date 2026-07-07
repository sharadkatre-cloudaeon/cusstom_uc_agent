"""LLM abstraction.

Backends:
  - MockLLM        : zero-dependency, offline. Keyword rules only.
  - DatabricksLLM  : ChatDatabricks against a workspace FM / PT serving endpoint.
                     Uses ambient notebook auth in dev and automatic passthrough
                     M2M OAuth when deployed (declare DatabricksServingEndpoint in
                     log_model resources — no PAT or apiToken).
  - AnthropicLLM   : direct Anthropic API via ANTHROPIC_API_KEY (external model).

The agent logic (driver/graph) is identical for all — only text understanding differs.
"""
from __future__ import annotations
import json
import os
import re

from .answer_options import append_choice_hint

_PHRASE_OUTPUT_RULE = (
    "Respond with just the question text — no quotes, no labels, "
    "no preamble, no commentary, no markdown separators."
)

PHRASE_QUESTION_INSTRUCTION = (
    "Rephrase the following intake question in one short, business-friendly "
    "sentence for a non-technical business user. "
    "Stay strictly within the intent — do not add new details.\n"
    "If prior conversation context is provided, ask ONLY for information that "
    "is still missing. Do not repeat or rephrase facts the user already gave. "
    "Do not ask the same topic twice in different words.\n"
    "Do not list answer options — they are appended separately.\n\n"
    + _PHRASE_OUTPUT_RULE
)

PHRASE_QUESTION_SIMPLER_INSTRUCTION = (
    "Rephrase the following intake question even more simply for a "
    "non-technical business user, in one short sentence. "
    "Stay strictly within the intent — do not add new details.\n"
    "Do not list answer options — they are appended separately.\n\n"
    + _PHRASE_OUTPUT_RULE
)

_META_PREFIXES = (
    "here's",
    "here is",
    "natural",
    "friendly way",
    "you could",
    "try asking",
)


def _phrase_prompt(question_text: str, simpler: bool, context: str | None) -> str:
    base = f"{_phrase_instruction(simpler)}\n\nTemplate: {question_text}"
    if context:
        base = f"{base}\n\n{context}"
    return base


def _already_covered_prompt(qid: str, question_text: str, state) -> str:
    prior = []
    for k, v in sorted(state.answers.items()):
        prior.append(f"[{k}] {v}")
    blob = "\n".join(prior) or "(none)"
    return (
        f"Question to ask ({qid}): {question_text}\n\n"
        f"Answers so far:\n{blob}\n\n"
        "Is this question already fully answered by the transcript above? "
        "Reply with ONLY yes or no."
    )


def _phrase_instruction(simpler: bool) -> str:
    return PHRASE_QUESTION_SIMPLER_INSTRUCTION if simpler else PHRASE_QUESTION_INSTRUCTION


def _parse_yes_no_reply(raw: str) -> bool:
    t = (raw or "").strip().lower()
    return t.startswith("y") and not t.startswith("no")


def _clean_phrase_output(text: str) -> str:
    """Strip common LLM meta-formatting from phrased questions."""
    t = (text or "").strip()
    if not t:
        return t

    if "---" in t:
        parts = [p.strip() for p in t.split("---") if p.strip()]
        for candidate in reversed(parts):
            if "?" in candidate or len(candidate.split()) >= 4:
                t = candidate
                break

    bold = re.match(r"^\*\*(.+)\*\*$", t, re.S)
    if bold:
        t = bold.group(1).strip()

    while len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        t = t[1:-1].strip()

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(lines) > 1:
        first = lines[0].lower()
        if any(p in first for p in _META_PREFIXES):
            t = "\n".join(lines[1:]).strip()

    return t.strip()


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
        if any(w in t for w in ("serious", "major", "critical", "severe")):
            s["impact_failure"] = "high"
        elif any(w in t for w in ("minor", "low", "small", "annoyance")):
            s["impact_failure"] = "low"
        else:
            s["impact_failure"] = "medium"
    return s


def is_no(t: str) -> bool:
    t = t.lower()
    return any(w in t for w in _NO)


class MockLLM:
    name = "mock"

    def phrase(
        self,
        question_text: str,
        simpler: bool = False,
        options: list[str] | None = None,
        context: str | None = None,
    ) -> str:
        if simpler:
            base = "Let me put that more simply — " + question_text
        else:
            base = question_text
        return base

    def already_covered(self, qid: str, question_text: str, state) -> bool:
        return False

    def extract_signals(self, qid: str, question_text: str, answer_text: str) -> dict:
        return keyword_signals(qid, answer_text)


class DatabricksLLM:
    """Workspace-hosted model via a serving endpoint — no manual token handling."""

    name = "databricks"

    def __init__(self, system_prompt: str = ""):
        from databricks_langchain import ChatDatabricks
        from langchain_core.messages import HumanMessage, SystemMessage

        self._HumanMessage = HumanMessage
        self._SystemMessage = SystemMessage
        endpoint = os.environ.get(
            "DATABRICKS_LLM_ENDPOINT", "databricks-claude-opus-4-6"
        )
        self.llm = ChatDatabricks(endpoint=endpoint, temperature=0.3)
        self.system = system_prompt

    def _invoke(self, prompt: str) -> str:
        messages = []
        if self.system:
            messages.append(self._SystemMessage(content=self.system))
        messages.append(self._HumanMessage(content=prompt))
        resp = self.llm.invoke(messages)
        content = resp.content
        return content if isinstance(content, str) else str(content)

    def phrase(
        self,
        question_text: str,
        simpler: bool = False,
        options: list[str] | None = None,
        context: str | None = None,
    ) -> str:
        prompt = _phrase_prompt(question_text, simpler, context)
        base = _clean_phrase_output(self._invoke(prompt))
        return base

    def already_covered(self, qid: str, question_text: str, state) -> bool:
        raw = self._invoke(_already_covered_prompt(qid, question_text, state))
        return _parse_yes_no_reply(raw)

    def extract_signals(self, qid: str, question_text: str, answer_text: str) -> dict:
        schema_hint = (
            "Return ONLY a JSON object of relevant signals among: domain_hint(GA/DS/AA/AU), "
            "action(act/suggest), logic(judgement/rules), steps(multi/single), needs_knowledge(bool), "
            "impact(high/medium/low), fairness_risk(bool), sensitivity(special/personal/none), "
            "writes(bool), multi_system(bool), sharing(bool), hitl(human/auto), regulated(bool), "
            "analytics_kind(dashboard/diagnose/predict/recommend/adaptive). Omit keys you can't infer."
        )
        raw = self._invoke(
            f"Question ({qid}): {question_text}\nUser answer: {answer_text}\n\n{schema_hint}"
        )
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return json.loads(m.group(0)) if m else {}
        except Exception:
            return keyword_signals(qid, answer_text)


class AnthropicLLM:
    """Real backend. Requires `pip install anthropic` and ANTHROPIC_API_KEY."""
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", system_prompt: str = ""):
        import anthropic  # lazy
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.model = model
        self.system = system_prompt

    def phrase(
        self,
        question_text: str,
        simpler: bool = False,
        options: list[str] | None = None,
        context: str | None = None,
    ) -> str:
        prompt = _phrase_prompt(question_text, simpler, context)
        msg = self.client.messages.create(
            model=self.model, max_tokens=120, system=self.system,
            messages=[{"role": "user", "content": prompt}])
        base = _clean_phrase_output("".join(b.text for b in msg.content if b.type == "text"))
        return base

    def already_covered(self, qid: str, question_text: str, state) -> bool:
        msg = self.client.messages.create(
            model=self.model, max_tokens=8, system=self.system,
            messages=[{"role": "user", "content": _already_covered_prompt(qid, question_text, state)}])
        raw = "".join(b.text for b in msg.content if b.type == "text")
        return _parse_yes_no_reply(raw)

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
    if backend == "databricks":
        return DatabricksLLM(system_prompt=system_prompt)
    if backend == "anthropic":
        return AnthropicLLM(system_prompt=system_prompt)
    return MockLLM()
