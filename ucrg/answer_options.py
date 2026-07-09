"""Parse answer_type metadata into user-facing choice hints."""

from __future__ import annotations

import json
import re

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

# Q16 shares externally — elaboration captures which departments/vendors.
_ELABORATION_LABELS: dict[str, str] = {
    "Yes / No + which": "Which ones?",
    "Yes / No / which": "Which departments or vendors?",
}

# Explicit widget slugs — frontend must not guess from question text.
_ANSWER_TYPE_WIDGET: dict[str, str] = {
    "Rules / Judgement": "rules_judgement",
    "Suggests / Acts": "suggests_acts",
    "Single / Multi-step": "single_multi_step",
    "Create / Process / Analyse": "create_process_analyse",
    "Minor / Moderate / Serious": "impact_severity",
    "Human / Acts alone / Depends": "human_oversight",
    "Not needed / Helpful / Essential": "explainability_level",
}

# Q4 user-volume quick picks (only for Q4 — never reuse on other questions).
_Q4_VOLUME_BANDS = ["1–10", "11–50", "51–200", "201–1,000", "1,000+"]

# Widgets the agent will never emit — frontend must not substitute these locally.
FORBIDDEN_WIDGETS = frozenset({"date_picker", "date", "calendar"})

# Hard overrides when frontend heuristics misfire (deadline/unavailable → date picker).
_QID_WIDGET_OVERRIDES: dict[str, str] = {
    "Q22": "impact_severity",
}


def strip_choice_hint(text: str | None) -> str:
    """Remove inline option hints — options belong in answer_surface metadata only."""
    if not text:
        return ""
    marker = "\n\nYou can choose from:"
    if marker in text:
        return text.split(marker, 1)[0].strip()
    return text.strip()


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
                "label": _ELABORATION_LABELS.get(normalized, "Please specify"),
                "widget": "text_long",
                "placeholder": "Tell us a bit more…",
            },
        }
    return None


def structured_option_items(options: list[str] | None) -> list[dict]:
    """Stable {id, label} options for frontend answer surfaces."""
    if not options:
        return []
    items: list[dict] = []
    for label in options:
        slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or label.lower()
        items.append({"id": slug, "label": label})
    return items


def resolve_input_widget(
    answer_type: str | None,
    options: list[str] | None,
    *,
    qid: str | None = None,
    options_widget: str | None = None,
) -> str:
    """Map answer_type metadata to a frontend widget id.

    Explicit mapping prevents the UI from guessing (e.g. volume bands on Q9).
    """
    if options_widget:
        return options_widget

    if qid == "Q4":
        return "volume_bands"

    if qid in _QID_WIDGET_OVERRIDES:
        return _QID_WIDGET_OVERRIDES[qid]

    if not answer_type:
        return "text_long"

    normalized = answer_type.strip()
    if normalized in _ANSWER_TYPE_WIDGET:
        return _ANSWER_TYPE_WIDGET[normalized]

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

    qid = question.get("id")
    answer_type = question.get("answer_type")
    static_options = question.get("options")
    if static_options is None and answer_type:
        static_options = parse_answer_options(answer_type)

    # Volume bands are Q4-only; categorical types keep parsed static options.
    if qid == "Q4":
        static_options = list(_Q4_VOLUME_BANDS)

    dynamic = question.get("dynamic_options")
    options_widget = question.get("options_widget")
    if dynamic:
        options = list(dynamic)
        options_source = "dynamic"
    elif qid in {"Q4", "Q15"} and question.get("options"):
        options = list(question["options"])
        options_source = "dynamic"
    else:
        options = static_options
        options_source = "static"
        dynamic = None

    widget = resolve_input_widget(
        answer_type,
        static_options,
        qid=qid,
        options_widget=options_widget if dynamic else None,
    )
    additional_fields = resolve_additional_fields(
        qid,
        question.get("additional_fields"),
    )
    elaboration = resolve_elaboration(answer_type)
    display_text = strip_choice_hint(question.get("display_text") or question.get("text"))

    return {
        "id": qid,
        "text": display_text,
        "kind": question.get("kind", "standard"),
        "answer_type": answer_type,
        "options": options,
        "option_items": structured_option_items(options),
        "static_options": static_options,
        "options_source": options_source,
        "options_locked": widget in set(_ANSWER_TYPE_WIDGET.values()) or widget in {
            "yes_no", "yes_no_unsure", "volume_bands",
        },
        "widget": widget,
        "additional_fields": additional_fields,
        "elaboration": elaboration,
        "allows_custom_answer": widget in {
            "single_select",
            "multi_select",
            "yes_no",
            "yes_no_unsure",
            "volume_bands",
            *_ANSWER_TYPE_WIDGET.values(),
        },
        "allows_not_sure": True,
    }


def build_answer_surface(question_view: dict | None, *, segment: int) -> dict | None:
    """Frontend-compatible answer surface — always prefer this over local Q-id maps."""
    if not question_view:
        return None
    widget = question_view["widget"]
    if widget in FORBIDDEN_WIDGETS:
        widget = "text_long"
    return {
        "questionId": question_view["id"],
        "questionText": question_view["text"],
        "segment": segment,
        "kind": question_view.get("kind", "standard"),
        "widget": widget,
        "options": question_view.get("option_items") or [],
        "allowNotSure": question_view.get("allows_not_sure", True),
        "resolveSource": "agent",
        "elaboration": question_view.get("elaboration"),
        "additionalFields": question_view.get("additional_fields") or [],
        "optionsLocked": question_view.get("options_locked", False),
        "forbiddenWidgets": sorted(FORBIDDEN_WIDGETS),
        "dataModel": {
            "question": question_view["text"],
            "options": question_view.get("option_items") or [],
            "disabled": False,
        },
    }


def ui_widget_policy() -> dict:
    """Global UI contract shipped on every agent turn."""
    return {
        "resolveSource": "agent",
        "forbiddenWidgets": sorted(FORBIDDEN_WIDGETS),
        "neverInferWidgetFromQuestionText": True,
    }
