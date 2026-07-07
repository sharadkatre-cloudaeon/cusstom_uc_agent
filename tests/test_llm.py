import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.llm import (
    PHRASE_QUESTION_INSTRUCTION,
    _clean_phrase_output,
    _phrase_instruction,
)


def test_phrase_instruction_includes_output_rule():
    assert "Respond with just the question text" in PHRASE_QUESTION_INSTRUCTION
    assert "no preamble" in PHRASE_QUESTION_INSTRUCTION
    assert _phrase_instruction(True) != _phrase_instruction(False)


def test_clean_phrase_output_strips_meta_and_separators():
    raw = (
        "Here's a natural, friendly way to open:\n"
        "---\n"
        '**"To kick things off — can you tell me in your own words what '
        'you\'d like this to do?"**'
    )
    cleaned = _clean_phrase_output(raw)
    assert cleaned.startswith("To kick things off")
    assert "---" not in cleaned
    assert "**" not in cleaned
    assert "Here's a natural" not in cleaned


def test_clean_phrase_output_strips_wrapping_quotes():
    assert (
        _clean_phrase_output('"What problem does it solve?"')
        == "What problem does it solve?"
    )


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\n{len(fns)} tests passed")
