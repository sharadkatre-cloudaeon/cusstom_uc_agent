import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.answer_options import (
    append_choice_hint,
    normalize_user_answer,
    parse_answer_options,
    resolve_input_widget,
    question_input_view,
)
from ucrg.engine import build_segment_progress, question_dict, form_questions


def test_parse_yes_no_not_sure():
    assert parse_answer_options("Yes / No / Not sure") == ["Yes", "No", "Not sure"]


def test_parse_suggests_acts():
    assert parse_answer_options("Suggests / Acts") == ["Suggests", "Acts"]


def test_parse_text_is_free_form():
    assert parse_answer_options("Text") is None


def test_parse_text_not_sure():
    assert parse_answer_options("Text / Not sure") == ["Not sure"]


def test_parse_yes_no_plus_which():
    assert parse_answer_options("Yes / No + which") == ["Yes", "No"]


def test_parse_minor_moderate_serious():
    assert parse_answer_options("Minor / Moderate / Serious") == [
        "Minor", "Moderate", "Serious"
    ]


def test_resolve_minor_moderate_serious_widget():
    options = parse_answer_options("Minor / Moderate / Serious")
    assert resolve_input_widget("Minor / Moderate / Serious", options) == "impact_severity"


def test_resolve_yes_no_unsure_widget():
    options = parse_answer_options("Yes / No / Not sure")
    assert resolve_input_widget("Yes / No / Not sure", options) == "yes_no_unsure"


def test_question_input_view_q3_includes_domain_field():
    q = question_dict(form_questions(1)[2])
    assert q["id"] == "Q3"
    view = question_input_view(q)
    assert view["widget"] == "text_short"
    assert len(view["additional_fields"]) == 1
    assert view["additional_fields"][0]["id"] == "domain"
    assert view["additional_fields"][0]["widget"] == "text_short"


def test_normalize_user_answer_q3_structured():
    raw = '{"owner": "Jane Doe, Head of HR", "domain": "Human Resources"}'
    assert normalize_user_answer("Q3", raw) == (
        "Jane Doe, Head of HR — domain: Human Resources"
    )


def test_resolve_elaboration_yes_no_which():
    from ucrg.answer_options import resolve_elaboration
    elab = resolve_elaboration("Yes / No + which")
    assert elab["when"] == ["Yes"]
    assert elab["field"]["id"] == "elaboration"


def test_normalize_choice_elaboration():
    raw = '{"choice": "Yes", "elaboration": "pricing and eligibility"}'
    assert normalize_user_answer("Q5", raw) == "Yes — pricing and eligibility"


def test_question_input_view_q5_elaboration():
    from ucrg.engine import form_questions, question_dict
    q5 = question_dict([q for q in form_questions(2) if q["id"] == "Q5"][0])
    view = question_input_view(q5)
    assert view["widget"] == "yes_no"
    assert view["elaboration"] is not None
    assert view["elaboration"]["when"] == ["Yes"]


def test_question_input_view_q16_yes_no_with_elaboration():
    from ucrg.engine import form_questions, question_dict
    from ucrg.answer_options import build_answer_surface
    q16 = question_dict([q for q in form_questions(5) if q["id"] == "Q16"][0])
    view = question_input_view(q16)
    assert view["id"] == "Q16"
    assert view["widget"] == "yes_no"
    assert view["options"] == ["Yes", "No"]
    assert view["elaboration"] is not None
    surface = build_answer_surface(view, segment=5)
    assert surface["resolveSource"] == "agent"
    assert surface["widget"] == "yes_no"
    assert {o["id"] for o in surface["options"]} == {"yes", "no"}


def test_question_input_view_q9_rules_judgement():
    from ucrg.engine import form_questions, question_dict
    q9 = question_dict([q for q in form_questions(3) if q["id"] == "Q9"][0])
    view = question_input_view(q9)
    assert view["id"] == "Q9"
    assert view["widget"] == "rules_judgement"
    assert view["options"] == ["Rules", "Judgement"]
    assert view["options_locked"] is True
    assert view["options_source"] == "static"


def test_question_input_view_q4_volume_bands_only():
    from ucrg.engine import form_questions, question_dict
    q4 = question_dict([q for q in form_questions(2) if q["id"] == "Q4"][0])
    view = question_input_view(q4)
    assert view["widget"] == "volume_bands"
    assert view["options"][0] == "1–10"
    assert view["options_source"] == "static"


def test_question_input_view_q22():
    from ucrg.answer_options import build_answer_surface, ui_widget_policy
    q = question_dict(form_questions(7)[-1])
    view = question_input_view(q)
    assert view["id"] == "Q22"
    assert view["widget"] == "impact_severity"
    assert view["options"] == ["Minor", "Moderate", "Serious"]
    assert "You can choose from" not in view["text"]
    surface = build_answer_surface(view, segment=7)
    assert surface["widget"] == "impact_severity"
    assert surface["resolveSource"] == "agent"
    assert "date_picker" in surface["forbiddenWidgets"]
    assert len(surface["options"]) == 3
    policy = ui_widget_policy()
    assert "date_picker" in policy["forbiddenWidgets"]


def test_build_segment_progress():
    progress = build_segment_progress(3)
    assert progress["current_segment"] == 3
    assert progress["total_segments"] == 7
    assert len(progress["segments"]) == 7
    assert progress["segments"][2]["status"] == "current"
    assert progress["segments"][0]["status"] == "complete"
    assert progress["segments"][3]["status"] == "pending"


def test_build_segment_progress_done():
    progress = build_segment_progress(7, done=True)
    assert all(seg["status"] == "complete" for seg in progress["segments"])


def test_append_choice_hint():
    out = append_choice_hint("Does it act alone?", ["Yes", "No"])
    assert "You can choose from: Yes · No" in out
    assert "answer in your own words" in out


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\n{len(fns)} tests passed")
