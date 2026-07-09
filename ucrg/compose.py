"""Compose the two deliverables from accumulated state: an SDD-style requirements
document and a framework scorecard (both Markdown)."""
from .engine import form_questions, segment_label, DOMAIN_NAMES


def _md_cell(value) -> str:
    """Escape pipe chars so markdown tables stay intact."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _kv_table(rows: list[tuple[str, str]]) -> list[str]:
    lines = ["| Field | Value |", "| --- | --- |"]
    for field, value in rows:
        lines.append(f"| {_md_cell(field)} | {_md_cell(value)} |")
    return lines


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
    lines = [
        "# Framework Scorecard",
        "",
        "## Classification (internal — for the development team)",
        *_kv_table(
            [
                ("Domain", f"{p.get('domain_name', '?')} ({p.get('domain', '?')})"),
                ("Maturity level", f"L{p.get('level', '?')} — {p.get('name', '?')}"),
                ("Confidence", str(p.get("confidence", "?"))),
            ]
        ),
        "",
    ]

    verdict_rows: list[tuple[str, str]] = [
        ("Verdict", f"**{g.get('verdict', 'n/a')}**"),
        ("Level used", f"L{g.get('level_used', '?')}"),
    ]
    if g.get("recommended_level") and g.get("verdict") == "ESCALATE":
        verdict_rows.append(("Recommended level", f"L{g['recommended_level']}"))
    if g.get("reason"):
        verdict_rows.append(("Reason", g["reason"]))
    if g.get("triggers"):
        verdict_rows.append(("Triggers fired", ", ".join(g["triggers"])))
    if g.get("overlay"):
        verdict_rows.append(("Governance overlay", ", ".join(g["overlay"])))
    if g.get("conditions"):
        verdict_rows.append(("Conditions", ", ".join(g["conditions"])))
    if g.get("note"):
        verdict_rows.append(("Note", g["note"]))

    lines += ["## Decision-gate verdict", *_kv_table(verdict_rows), ""]

    gate_inputs = g.get("inputs") or {}
    lines += [
        "## Gate inputs",
        *_kv_table([(str(k), str(v)) for k, v in gate_inputs.items()]),
        "",
    ]

    lines += [
        "## Open-items register (for Development / Security / Legal)",
        f"_{len(state.open_items)} technical questions tagged out of the interview._",
        "",
        "| ID | Area | Open item |",
        "| --- | --- | --- |",
    ]
    for it in state.open_items:
        lines.append(
            f"| {_md_cell(it['id'])} | {_md_cell(it.get('area', ''))} | {_md_cell(it['open_item'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def compose_output(state) -> dict:
    return {"sdd": _sdd(state), "scorecard": _scorecard(state)}
