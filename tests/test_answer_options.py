import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.answer_options import append_choice_hint, parse_answer_options


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
