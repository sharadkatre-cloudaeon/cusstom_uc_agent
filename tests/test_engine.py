"""Sanity tests — run with:  python -m pytest -q   (or)   python tests/test_engine.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.engine import lookup_followups, gate_rule, form_questions
from ucrg.gate import run_decision_gate


def test_activation_counts_ga_l3():
    # Without parent answers only CLS-parented items activate.
    bare = lookup_followups("GA", 3)
    assert bare["ask"] == [] and bare["auto"] == []
    assert all(i.get("parent") == "CLS" for i in bare["tag"])

    answers = {
        "Q3": "HR",
        "Q6": "yes, fairness risk",
        "Q8": "writes to systems",
        "Q9": "rules based",
        "Q13": "yes, customer personal data",
        "Q14": "yes, needs company documents",
        "Q16": "yes, shared outside the team",
        "Q17": "a person reviews before it is used",
        "Q18": "legal and compliance review",
        "Q20": "cost limit of 10k",
    }
    signals = {
        "sensitivity": "personal",
        "needs_knowledge": True,
        "sharing": True,
        "hitl": "review",
        "fairness_risk": True,
        "posture": "writes",
    }
    r = lookup_followups("GA", 3, answers=answers, signals=signals)
    assert (len(r["ask"]), len(r["auto"]), len(r["tag"])) == (9, 3, 14)


def test_cumulative_is_monotonic():
    # Use satisfying parents so level growth is not masked by gating.
    answers = {
        "Q3": "ops",
        "Q5": "yes high impact",
        "Q6": "yes",
        "Q8": "writes",
        "Q9": "rules",
        "Q13": "yes personal",
        "Q14": "yes knowledge",
        "Q16": "yes sharing",
        "Q17": "human reviews",
        "Q18": "compliance",
        "Q20": "budget ok",
    }
    signals = {
        "sensitivity": "personal",
        "needs_knowledge": True,
        "sharing": True,
        "hitl": "review",
        "impact": "high",
        "fairness_risk": True,
        "posture": "writes",
    }
    prev = 0
    for lvl in range(1, 6):
        total = sum(
            len(v)
            for v in lookup_followups("AA", lvl, answers=answers, signals=signals).values()
        )
        assert total >= prev
        prev = total


def test_form_has_22_questions():
    assert len(form_questions()) == 22


def test_gate_escalates_low_level_with_sensitive_data():
    v = run_decision_gate({"domain": "AA", "level": 1, "impact": "low",
                           "sensitivity": "personal", "posture": "assistive",
                           "scope": "single", "regulated": False})
    assert v["verdict"] == "ESCALATE" and v["recommended_level"] == 2


def test_gate_overlay_at_l3_high_impact():
    v = run_decision_gate({"domain": "GA", "level": 3, "impact": "high",
                           "sensitivity": "personal", "posture": "assistive",
                           "scope": "single", "regulated": True})
    assert v["verdict"] == "APPROVE_WITH_ENHANCED_GOVERNANCE" and v["overlay"]


def test_gate_l4_is_provisional():
    v = run_decision_gate({"domain": "DS", "level": 4, "impact": "high",
                           "sensitivity": "personal", "posture": "writes",
                           "scope": "cross-bu", "regulated": True})
    assert v["provisional"] is True


if __name__ == "__main__":
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_")]
    for f in fns:
        f(); print("ok:", f.__name__)
    print(f"\n{len(fns)} tests passed")
