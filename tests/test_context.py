import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.context import FRIENDLY_Q1, should_ask, suggest_dynamic_options, derive_from_transcript, mark_skipped
from ucrg.driver import UCRGAgent
from ucrg.engine import lookup_followups, parent_answer_satisfied
from ucrg.state import UCRGState


def test_friendly_q1_no_llm_rephrase():
    agent = UCRGAgent(backend="mock")
    agent.start()
    assert FRIENDLY_Q1 in agent.s.phrased_questions.get("Q1:standard", "")


def test_gap_question_q13_after_q1_mentions_data():
    from ucrg.context import build_unique_question
    state = UCRGState()
    state.answers["Q1"] = "HR chatbot using internal policy documents and employee data"
    q13 = {"id": "Q13", "text": "Does any of it include personal, customer, or confidential data?"}
    gap = build_unique_question(q13, state)
    assert gap is not None
    assert "confirm" in gap.lower() or "governance" in gap.lower()
    assert gap != q13["text"]


def test_gap_question_q4_asks_volume_not_users():
    from ucrg.context import build_unique_question
    state = UCRGState()
    state.answers["Q1"] = "Chatbot for HR employees and managers"
    q4 = {"id": "Q4", "text": "Who will use it, roughly how many, and how often?"}
    gap = build_unique_question(q4, state)
    assert gap is not None
    assert "how many" in gap.lower() or "how often" in gap.lower()


def test_gap_question_q17_reuses_action_context():
    from ucrg.context import build_unique_question
    state = UCRGState()
    state.answers["Q8"] = "Both suggest and act depending on context."
    q17 = {
        "id": "Q17",
        "text": "For any decision or action it takes, must a human approve first, or can it act on its own?",
    }
    gap = build_unique_question(q17, state)
    assert gap is not None
    assert "already described" in gap.lower()
    assert "human approval" in gap.lower()


def test_followup_redundant_when_overlaps_parent():
    from ucrg.context import followup_is_redundant
    from ucrg.engine import form_questions
    form_by_id = {fq["id"]: fq for fq in form_questions()}
    state = UCRGState()
    state.answers["Q13"] = "Yes, customer personal data"
    item = {
        "id": "FU-1",
        "parent": "Q13",
        "question": "Does any personal or customer confidential data get processed?",
    }
    assert followup_is_redundant(item, state, form_by_id) is True


def test_followup_redundant_before_parent_answered():
    """Near-identical Ask-BU wording must not re-ask the form topic."""
    from ucrg.context import followup_is_redundant
    from ucrg.engine import form_questions
    form_by_id = {fq["id"]: fq for fq in form_questions()}
    state = UCRGState()
    item = {
        "id": "AU-DGP-3.2",
        "parent": "Q16",
        "question": form_by_id["Q16"]["question"],
    }
    assert followup_is_redundant(item, state, form_by_id) is True


def test_parent_unanswered_blocks_followups():
    assert parent_answer_satisfied("Q13", {}, {}) is False
    assert parent_answer_satisfied("Q16", {}, {}) is False


def test_gate_critical_never_skipped():
    state = UCRGState()
    state.answers["Q1"] = (
        "Customer-facing HR chatbot using internal policy documents and customer data "
        "from SharePoint. It affects employees and connects to Workday."
    )
    derive_from_transcript(state)
    for qid in ("Q5", "Q13", "Q14", "Q15"):
        q = {"id": qid, "text": qid, "gate_critical": True}
        assert should_ask(q, state) is True


def test_skip_q2_when_q1_covers_problem():
    state = UCRGState()
    state.answers["Q1"] = (
        "A chatbot for HR policy questions. Today teams search SharePoint manually "
        "which is slow and the problem is inconsistent answers."
    )
    derive_from_transcript(state)
    q2 = {"id": "Q2", "text": "What problem does it solve?", "gate_critical": False}
    assert should_ask(q2, state) is False
    mark_skipped(state, "Q2", "covered in your description of the idea")
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
