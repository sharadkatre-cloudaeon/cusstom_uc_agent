"""Context-aware interview helpers — skip, derive, and phrase with prior answers."""

from __future__ import annotations

import re

from .llm import is_no, is_not_sure, is_yes, keyword_signals

# Fixed friendly copy for Q1 (no LLM rephrase).
FRIENDLY_Q1 = (
    "What's the idea in your own words — what would you love this to help with?"
)

_PHRASE_SKIP_IDS = frozenset({"Q1"})

# Only non-gate questions may be skipped via lightweight heuristics.
_SKIPPABLE_IDS = frozenset({"Q2", "Q4"})

# When prior answers touch a topic, ask only the missing angle — not the full template again.
_QUESTION_GAPS: dict[str, dict] = {
    "Q2": {
        "touch": ("problem", "solve", "pain", "issue", "because", "need"),
        "min_touch": 2,
        "gap": "How is that handled today — manually, with an existing tool, or not at all?",
    },
    "Q4": {
        "touch": ("user", "users", "people", "team", "staff", "employee", "customer", "manager"),
        "min_touch": 1,
        "gap": "Roughly how many people would use this, and how often?",
    },
    "Q5": {
        "touch": ("customer", "employee", "user", "people", "hiring", "pricing", "complaint", "eligibility"),
        "min_touch": 1,
        "gap": (
            "Just to confirm: could its outputs materially affect individuals — "
            "eligibility, pricing, hiring, complaints, or other customer-facing decisions?"
        ),
    },
    "Q8": {
        "touch": ("suggest", "draft", "recommend", "approve", "automatic", "act", "change", "write"),
        "min_touch": 1,
        "gap": "Should it only suggest or draft things for a person to action, or actually take actions itself?",
    },
    "Q12": {
        "touch": ("data", "document", "information", "sharepoint", "wiki", "record", "database"),
        "min_touch": 1,
        "gap": "Where does that information live today, and how complete or up to date is it?",
    },
    "Q13": {
        "touch": ("personal", "customer", "confidential", "private", "pii", "sensitive", "data"),
        "min_touch": 1,
        "gap": "To confirm for governance: does any of it include personal, customer, or confidential data?",
    },
    "Q14": {
        "touch": ("document", "wiki", "policy", "knowledge", "internal", "sharepoint", "handbook", "intranet"),
        "min_touch": 1,
        "gap": "Does it need your organisation's own documents or knowledge to answer correctly?",
    },
    "Q15": {
        "touch": ("sharepoint", "workday", "salesforce", "system", "sap", "servicenow", "connect", "integrat"),
        "min_touch": 1,
        "gap": "For each system it connects to, does it only read information or also change/write records?",
    },
    "Q16": {
        "touch": ("vendor", "external", "department", "partner", "third", "share", "outside"),
        "min_touch": 1,
        "gap": "Will it share data with other departments or outside vendors?",
    },
    "Q17": {
        "touch": ("suggest", "draft", "recommend", "automatic", "autonomous", "approve", "human", "oversight"),
        "min_touch": 1,
        "gap": (
            "You already described how it suggests vs acts. "
            "For the actions it takes, should any require human approval first?"
        ),
    },
}

# Keyword heuristics: skip a question when prior answers already cover it.
_COVERAGE_HINTS: dict[str, tuple[str, ...]] = {
    "Q2": (
        "problem", "solve", "today", "currently", "manual", "spreadsheet",
        "existing", "handled", "pain", "issue", "because",
    ),
    "Q4": (
        "daily", "weekly", "monthly", "roughly", "per day", "per week",
        " hundred", " thousand", " dozen", "users per", "people per",
        "how often", "how many",
    ),
}

_STOPWORDS = frozenset({
    "what", "which", "when", "where", "does", "will", "that", "this", "with",
    "from", "have", "your", "they", "them", "their", "about", "into", "only",
    "also", "other", "some", "any", "must", "should", "would", "could",
})


def _prior_text(state) -> str:
    parts = []
    for qid in sorted(state.answers.keys()):
        parts.append(f"[{qid}] {state.answers[qid]}")
    for qid in sorted(state.derived.keys()):
        parts.append(f"[{qid} derived] {state.derived[qid]}")
    return "\n".join(parts).lower()


def _touch_count(blob: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for kw in keywords if kw in blob)


def _topic_tokens(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]+", text.lower())
        if len(w) > 3 and w not in _STOPWORDS
    }


def _token_overlap(a: str, b: str) -> float:
    ta, tb = _topic_tokens(a), _topic_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def build_unique_question(question: dict, state) -> str | None:
    """Return a gap-focused question when prior answers already touch this topic."""
    qid = question.get("id") or ""
    spec = _QUESTION_GAPS.get(qid)
    if not spec:
        return None
    blob = _prior_text(state)
    if not blob.strip():
        return None
    if _touch_count(blob, spec["touch"]) < spec["min_touch"]:
        return None
    return spec["gap"]


def followup_is_redundant(item: dict, state, form_by_id: dict) -> bool:
    """Drop follow-ups that restate the parent form question (answered or not)."""
    parent = item.get("parent") or ""
    if not parent:
        return False
    parent_meta = form_by_id.get(parent)
    if not parent_meta:
        return False
    follow = item.get("question") or ""
    parent_text = parent_meta.get("question") or ""
    if _token_overlap(follow, parent_text) >= 0.42:
        return True
    if parent not in state.answers:
        return False
    if _token_overlap(follow, state.answers.get(parent, "")) >= 0.38:
        return True
    return False


def _heuristic_covered(qid: str, state) -> bool:
    hints = _COVERAGE_HINTS.get(qid)
    if not hints:
        return False
    blob = _prior_text(state)
    if not blob.strip():
        return False
    return sum(1 for h in hints if h in blob) >= 2


def should_ask(question: dict, state, llm=None) -> bool:
    """Return False only when a non-critical question is clearly already answered."""
    qid = question.get("id") or ""
    if not qid:
        return True
    if qid in state.answers:
        return False
    # Gate-critical questions must always be asked — never infer from earlier text.
    if question.get("gate_critical"):
        return True
    if qid in state.skipped_ids:
        return False
    if qid not in _SKIPPABLE_IDS:
        return True
    if _heuristic_covered(qid, state):
        return False
    return True


def mark_skipped(state, qid: str, reason: str):
    state.skipped_ids.add(qid)
    state.derived[qid] = f"(skipped — {reason})"


def build_phrase_context(state) -> str:
    """Compact summary for contextual question phrasing."""
    if not state.answers:
        return ""
    lines = []
    for qid, ans in sorted(state.answers.items()):
        lines.append(f"- {qid}: {ans[:200]}")
    return (
        "Prior answers (do NOT re-ask facts already given — ask only what is still missing):\n"
        + "\n".join(lines[-6:])
    )


def derive_from_transcript(state):
    """Infer classification signals from rich early answers — do not skip questions."""
    q1 = state.answers.get("Q1", "")
    if not q1:
        return
    for sig in (
        keyword_signals("Q11", q1),
        keyword_signals("Q8", q1),
        keyword_signals("Q13", q1),
        keyword_signals("Q5", q1),
    ):
        state.signals.update({k: v for k, v in sig.items() if v is not None})


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
