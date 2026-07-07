"""Parse answer_type metadata into user-facing choice hints."""

from __future__ import annotations

import json

_FREE_TEXT_TYPES = frozenset({
    "text",
    "name / role",
    "text + read/write",
    "-",
    "",
})

_CUSTOM_ANSWER_SUFFIX = " — or answer in your own words."

_ELABORATION_ANSWER_TYPES = frozenset({
    "Yes / No + which",
    "Yes / No / which",
})


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


_YES_NO_TYPES = frozenset({
    "Yes / No",
    "Yes / No + which",
    "Yes / No / which",
})

# Extra inputs keyed by form question id (business domain, not AI classification).
_QUESTION_ADDITIONAL_FIELDS: dict[str, list[dict]] = {
    "Q3": [
        {
            "id": "domain",
            "label": "Business domain or department",
            "widget": "text_short",
            "placeholder": "e.g. HR, Finance, Operations",
        },
    ],
}


def resolve_elaboration(answer_type: str | None) -> dict | None:
    """Optional free-text field shown when user picks certain choices."""
    if not answer_type:
        return None
    normalized = answer_type.strip()
    if normalized in _ELABORATION_ANSWER_TYPES:
        return {
            "when": ["Yes"],
            "field": {
                "id": "elaboration",
                "label": "Please specify",
                "widget": "text_long",
                "placeholder": "Tell us a bit more…",
            },
        }
    return None


def resolve_input_widget(answer_type: str | None, options: list[str] | None) -> str:
    """Map answer_type metadata to a frontend widget id.

    Explicit mapping prevents the UI from guessing (e.g. date picker on Q22).
    """
    if not answer_type:
        return "text_long"

    normalized = answer_type.strip()
    if normalized.lower() == "name / role":
        return "text_short"

    if normalized.lower() in _FREE_TEXT_TYPES:
        return "text_long"

    if normalized == "Yes / No / Not sure":
        return "yes_no_unsure"

    if normalized in _YES_NO_TYPES:
        return "yes_no"

    if normalized == "Text / Not sure":
        return "text_long"

    if options:
        return "single_select"

    return "text_long"


def resolve_additional_fields(qid: str | None, configured: list[dict] | None = None) -> list[dict]:
    """Return extra inputs the client should collect alongside the primary answer."""
    if configured is not None:
        return list(configured)
    return list(_QUESTION_ADDITIONAL_FIELDS.get(qid or "", []))


def _flatten_choice_payload(payload: dict) -> str:
    choice = (
        payload.get("choice")
        or payload.get("value")
        or payload.get("answer")
        or ""
    )
    if isinstance(choice, list):
        choice = ", ".join(str(c) for c in choice)
    choice = str(choice).strip()
    elaboration = (payload.get("elaboration") or payload.get("which") or "").strip()
    custom = (payload.get("custom") or payload.get("other") or "").strip()

    if choice and elaboration:
        return f"{choice} — {elaboration}"
    if choice and custom:
        return f"{choice} — {custom}"
    return choice or elaboration or custom


def normalize_user_answer(qid: str, text: str) -> str:
    """Flatten structured frontend payloads into stored answer text."""
    trimmed = (text or "").strip()
    if not trimmed.startswith("{"):
        return trimmed

    try:
        payload = json.loads(trimmed)
    except json.JSONDecodeError:
        return trimmed

    if not isinstance(payload, dict):
        return trimmed

    if qid == "Q3":
        owner = (
            payload.get("owner")
            or payload.get("name")
            or payload.get("value")
            or payload.get("answer")
            or ""
        ).strip()
        domain = (payload.get("domain") or "").strip()
        if owner and domain:
            return f"{owner} — domain: {domain}"
        return owner or domain or trimmed

    flattened = _flatten_choice_payload(payload)
    return flattened or trimmed


def question_input_view(question: dict | None) -> dict | None:
    """Normalise the active question for client-side widget rendering."""
    if not question:
        return None

    answer_type = question.get("answer_type")
    options = question.get("options")
    if options is None and answer_type:
        options = parse_answer_options(answer_type)
    dynamic = question.get("dynamic_options")
    if dynamic:
        options = list(dynamic)

    widget = resolve_input_widget(answer_type, options)
    additional_fields = resolve_additional_fields(
        question.get("id"),
        question.get("additional_fields"),
    )
    elaboration = resolve_elaboration(answer_type)
    display_text = question.get("display_text") or question.get("text")

    return {
        "id": question.get("id"),
        "text": display_text,
        "kind": question.get("kind", "standard"),
        "answer_type": answer_type,
        "options": options,
        "options_source": "dynamic" if dynamic else "static",
        "widget": widget,
        "additional_fields": additional_fields,
        "elaboration": elaboration,
        "allows_custom_answer": widget in {"single_select", "yes_no", "yes_no_unsure"},
        "allows_not_sure": True,
    }
