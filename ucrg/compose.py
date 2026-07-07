"""Compose the two deliverables from accumulated state: an SDD-style requirements
document and a framework scorecard (both Markdown)."""
from .engine import form_questions, segment_label, DOMAIN_NAMES


def _sdd(state) -> str:
    lines = ["# Use-Case Requirements (SDD)", ""]
    for seg in range(1, 8):
        lines.append(f"## {segment_label(seg)}")
        for q in form_questions(seg):
            ans = state.answers.get(q["id"]) or state.derived.get(q["id"]) or "_(not provided)_"
            lines.append(f"- **{q['question']}**")
            lines.append(f"  {ans}")
        lines.append("")
    return "\n".join(lines)


def _scorecard(state) -> str:
    p = state.classification.get("primary", {})
    g = state.gate_verdict
    lines = ["# Framework Scorecard", "",
             "## Classification (internal — for the development team)",
             f"- Domain: {p.get('domain_name', '?')} ({p.get('domain', '?')})",
             f"- Maturity level: L{p.get('level', '?')} — {p.get('name', '?')}",
             f"- Confidence: {p.get('confidence', '?')}", ""]

    lines += ["## Decision-gate verdict",
              f"- Verdict: **{g.get('verdict', 'n/a')}**",
              f"- Level used: L{g.get('level_used', '?')}"]
    if g.get("recommended_level") and g.get("verdict") == "ESCALATE":
        lines.append(f"- Recommended level: L{g['recommended_level']}")
    if g.get("reason"):
        lines.append(f"- Reason: {g['reason']}")
    if g.get("triggers"):
        lines.append(f"- Triggers fired: {', '.join(g['triggers'])}")
    if g.get("overlay"):
        lines.append(f"- Governance overlay: {', '.join(g['overlay'])}")
    if g.get("conditions"):
        lines.append(f"- Conditions: {', '.join(g['conditions'])}")
    if g.get("note"):
        lines.append(f"- Note: {g['note']}")
    lines.append("")

    lines += ["## Gate inputs"]
    for k, v in (g.get("inputs") or {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    lines += ["## Open-items register (for Development / Security / Legal)",
              f"_{len(state.open_items)} technical questions tagged out of the interview._", ""]
    for it in state.open_items:
        lines.append(f"- [{it['id']}] ({it.get('area', '')}) {it['open_item']}")
    lines.append("")
    return "\n".join(lines)


def compose_output(state) -> dict:
    return {"sdd": _sdd(state), "scorecard": _scorecard(state)}
