"""Context-aware interview helpers — skip, derive, and phrase with prior answers."""

from __future__ import annotations

import re

from .llm import is_no, is_not_sure, is_yes, keyword_signals

# Fixed friendly copy for Q1 (no LLM rephrase).
FRIENDLY_Q1 = (
    "What's the idea in your own words — what would you love this to help with?"
)

_PHRASE_SKIP_IDS = frozenset({"Q1"})

# Keyword heuristics: skip a question when prior answers already cover it.
_COVERAGE_HINTS: dict[str, tuple[str, ...]] = {
    "Q2": (
        "problem", "solve", "today", "currently", "manual", "spreadsheet",
        "existing", "handled", "pain", "issue", "because",
    ),
    "Q4": (
        "users", "user", "people", "team", "staff", "employees", "customers",
        "agents", "managers", "daily", "weekly", "monthly", "roughly", "about",
        " hundred", " thousand", " dozen", "everyone",
    ),
    "Q8": (
        "suggest", "draft", "recommend", "review", "approve", "act", "automatic",
        "itself", "execute", "change", "write", "human",
    ),
    "Q11": (
        "create", "generate", "analyse", "analyze", "predict", "report",
        "dashboard", "process", "move", "transfer", "summar", "recommend",
    ),
    "Q14": (
        "internal", "wiki", "document", "knowledge base", "our data", "company",
        "policy", "handbook", "sharepoint", "intranet", "ground",
    ),
}


def _prior_text(state) -> str:
    parts = []
    for qid in sorted(state.answers.keys()):
        parts.append(f"[{qid}] {state.answers[qid]}")
    for qid in sorted(state.derived.keys()):
        parts.append(f"[{qid} derived] {state.derived[qid]}")
    return "\n".join(parts).lower()


def _heuristic_covered(qid: str, state) -> bool:
    hints = _COVERAGE_HINTS.get(qid)
    if not hints:
        return False
    blob = _prior_text(state)
    if not blob.strip():
        return False
    return sum(1 for h in hints if h in blob) >= 2


def should_ask(question: dict, state, llm=None) -> bool:
    """Return False when the question is already answered or clearly covered."""
    qid = question.get("id") or ""
    if not qid:
        return True
    if qid in state.answers or qid in state.derived:
        return False
    if _heuristic_covered(qid, state):
        return False
    if llm is not None and hasattr(llm, "already_covered"):
        try:
            if llm.already_covered(qid, question.get("text", ""), state):
                return False
        except Exception:
            pass
    return True


def mark_skipped(state, qid: str, reason: str):
    state.skipped_ids.add(qid)
    state.derived[qid] = f"(skipped — {reason})"


def build_phrase_context(state) -> str:
    """Compact summary for contextual question phrasing."""
    if not state.answers and not state.derived:
        return ""
    lines = []
    for qid, ans in sorted(state.answers.items()):
        lines.append(f"- {qid}: {ans[:200]}")
    return "Prior answers:\n" + "\n".join(lines[-5:])


def derive_from_transcript(state):
    """Infer answers/signals from rich early answers so later questions can skip."""
    blob = _prior_text(state)
    if not blob.strip():
        return

    q1 = state.answers.get("Q1", "")
    if q1:
        for sig in (keyword_signals("Q11", q1), keyword_signals("Q8", q1),
                    keyword_signals("Q13", q1), keyword_signals("Q5", q1)):
            state.signals.update({k: v for k, v in sig.items() if v is not None})

    if _heuristic_covered("Q2", state) and "Q2" not in state.answers:
        mark_skipped(state, "Q2", "covered in your description of the idea")
    if _heuristic_covered("Q4", state) and "Q4" not in state.answers:
        mark_skipped(state, "Q4", "covered when you described who would use it")
    if _heuristic_covered("Q14", state) and "Q14" not in state.answers:
        mark_skipped(state, "Q14", "covered when you mentioned internal knowledge needs")

    q7 = state.answers.get("Q7", "")
    if q7 and "Q8" not in state.answers and _heuristic_covered("Q8", state):
        mark_skipped(state, "Q8", "covered in your walkthrough of what happens")


def suggest_dynamic_options(qid: str, state) -> list[str] | None:
    """Suggest contextual select options from prior answers (best-effort)."""
    blob = _prior_text(state)
    if not blob.strip():
        return None

    if qid == "Q4":
        opts = []
        if any(w in blob for w in ("hr", "human resources", "policy")):
            opts.extend(["HR team", "Managers", "All employees"])
        if any(w in blob for w in ("customer", "client", "member")):
            opts.extend(["Customer service agents", "Customers (self-serve)"])
        if any(w in blob for w in ("finance", "accounting", "invoice")):
            opts.extend(["Finance team", "Accounts payable"])
        if any(w in blob for w in ("sales", "marketing")):
            opts.extend(["Sales reps", "Marketing team"])
        # dedupe preserving order
        seen: set[str] = set()
        out = []
        for o in opts:
            if o not in seen:
                seen.add(o)
                out.append(o)
        return out[:6] or None

    if qid == "Q15":
        systems = []
        for m in re.finditer(r"\b(salesforce|sap|workday|servicenow|sharepoint|jira|confluence|excel|outlook)\b", blob):
            systems.append(m.group(1).title())
        if systems:
            seen: set[str] = set()
            out = []
            for s in systems:
                if s not in seen:
                    seen.add(s)
                    out.append(s)
            return out[:6]
    return None
