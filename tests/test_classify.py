"""Classification regression tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ucrg.classify import classify_use_case


def test_classify_accepts_list_domain_hint():
    r = classify_use_case({"domain_hint": ["GA", "DS"]})
    assert r["primary"]["domain"] == "GA"


def test_classify_ignores_invalid_list_domain_hint():
    r = classify_use_case({"domain_hint": ["invalid", 42], "analytics_kind": "predict"})
    assert r["primary"]["domain"] == "DS"


def test_classify_accepts_lowercase_domain_hint_string():
    r = classify_use_case({"domain_hint": "aa", "steps": "multi"})
    assert r["primary"]["domain"] == "AA"
