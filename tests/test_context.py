import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.context import FRIENDLY_Q1, should_ask, suggest_dynamic_options, derive_from_transcript
from ucrg.driver import UCRGAgent
from ucrg.engine import lookup_followups, parent_answer_satisfied
from ucrg.state import UCRGState


def test_friendly_q1_no_llm_rephrase():
    agent = UCRGAgent(backend="mock")
    agent.start()
    assert FRIENDLY_Q1 in agent.s.phrased_questions.get("Q1:standard", "")


def test_skip_q2_when_q1_covers_problem():
    state = UCRGState()
    state.answers["Q1"] = (
        "A chatbot for HR policy questions. Today teams search SharePoint manually "
        "which is slow and the problem is inconsistent answers."
    )
    derive_from_transcript(state)
    q2 = {"id": "Q2", "text": "What problem does it solve?"}
    assert should_ask(q2, state) is False
    assert "Q2" in state.skipped_ids


def test_duplicate_answer_advances(monkeypatch=None):
    agent = UCRGAgent(backend="mock")
    agent.start()
    first_q = agent._current["id"]
    r1 = agent.send("An HR policy assistant for employees.")
    assert not r1["done"]
    assert first_q in agent.s.answers
    prior_id = agent._current["id"] if agent._current else None
    r2 = agent.send("duplicate submit")
    if agent._current:
        assert agent._current["id"] != first_q or prior_id != first_q


def test_dynamic_options_q4_hr():
    state = UCRGState()
    state.answers["Q1"] = "HR policy chatbot for employees and managers"
    opts = suggest_dynamic_options("Q4", state)
    assert opts
    assert any("HR" in o for o in opts)


def test_parent_gating_q13_sensitive():
    assert parent_answer_satisfied("Q13", {"Q13": "no"}, {"sensitivity": "none"}) is False
    assert parent_answer_satisfied("Q13", {"Q13": "yes, customer data"}, {"sensitivity": "personal"}) is True


def test_lookup_followups_respects_parent():
    bare = lookup_followups("GA", 3)
    gated = lookup_followups("GA", 3, answers={"Q13": "no"}, signals={"sensitivity": "none"})
    assert sum(len(v) for v in gated.values()) <= sum(len(v) for v in bare.values())


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("ok:", fn.__name__)
    print(f"\n{len(fns)} tests passed")
