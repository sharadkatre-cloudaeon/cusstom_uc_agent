"""Parse answer_type metadata into user-facing choice hints."""

from __future__ import annotations

_FREE_TEXT_TYPES = frozenset({
    "text",
    "name / role",
    "text + read/write",
    "-",
    "",
})

_CUSTOM_ANSWER_SUFFIX = " — or answer in your own words."


def parse_answer_options(answer_type: str | None) -> list[str] | None:
    """Return selectable options for an answer_type, or None for free-text-only."""
    if not answer_type:
        return None
    normalized = answer_type.strip()
    if normalized.lower() in _FREE_TEXT_TYPES:
        return None

    if normalized == "Text / Not sure":
        return ["Not sure"]

    # "Yes / No + which" -> Yes / No; elaboration is free text.
    if "+" in normalized:
        normalized = normalized.split("+", 1)[0].strip()

    # "Yes / No / which" -> Yes / No.
    if normalized.lower().endswith("/ which"):
        normalized = normalized[: -len("/ which")].strip()

    parts = [part.strip() for part in normalized.split("/")]
    parts = [part for part in parts if part and part.lower() != "text"]
    return parts or None


def append_choice_hint(question: str, options: list[str] | None) -> str:
    """Append a choice hint when options exist; always mention custom answers."""
    text = (question or "").strip()
    if not options:
        return text
    joined = " · ".join(options)
    return f"{text}\n\nYou can choose from: {joined}{_CUSTOM_ANSWER_SUFFIX}"
