"""Silent classification: accumulated signals -> AI domain(s) + maturity level.
Heuristic and deterministic (a real build may delegate this to the LLM)."""
from .engine import DOMAIN_NAMES, LEVEL_NAMES


def _normalize_domain_hint(raw) -> str | None:
    """Return first valid domain code from LLM output (string or list-like)."""
    valid = set(DOMAIN_NAMES.keys())

    if isinstance(raw, str):
        cand = raw.strip().upper()
        return cand if cand in valid else None

    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            if not isinstance(item, str):
                continue
            cand = item.strip().upper()
            if cand in valid:
                return cand
    return None


def _level_for(domain: str, s: dict) -> int:
    if domain == "GA":
        if s.get("customised_model"): return 4
        if s.get("needs_knowledge"): return 3
        return 2 if s.get("examples") else 1
    if domain == "AA":
        if s.get("multi_agent"): return 4
        if s.get("steps") == "multi" and s.get("multi_system"): return 3
        if s.get("steps") == "multi": return 2
        return 1
    if domain == "AU":
        if s.get("logic") == "judgement": return 4          # AI-augmented
        if s.get("multi_system"): return 3                  # orchestrated
        return 2 if s.get("writes") else 1
    if domain == "DS":
        return {"dashboard": 1, "diagnose": 2, "predict": 3,
                "recommend": 4, "adaptive": 5}.get(s.get("analytics_kind"), 1)
    return 1


def classify_use_case(signals: dict) -> dict:
    """Return {"primary": {domain, level, confidence}, "domains": [...]}"""
    dom = _normalize_domain_hint(signals.get("domain_hint"))
    if not dom:
        if signals.get("analytics_kind"):
            dom = "DS"
        elif signals.get("action") == "act" or signals.get("steps") == "multi":
            dom = "AA"
        elif signals.get("logic") == "rules":
            dom = "AU"
        else:
            dom = "GA"
    level = _level_for(dom, signals)

    # confidence grows as more decisive signals arrive
    decisive = [signals.get(k) for k in ("domain_hint", "action", "steps", "needs_knowledge", "analytics_kind")]
    conf = round(min(0.95, 0.4 + 0.12 * sum(1 for d in decisive if d)), 2)

    primary = {"domain": dom, "level": level,
               "name": LEVEL_NAMES.get(dom, ["?"] * 5)[level - 1],
               "domain_name": DOMAIN_NAMES.get(dom, dom), "confidence": conf}
    return {"primary": primary, "domains": [primary]}


def is_firm(classification: dict) -> bool:
    p = classification.get("primary")
    return bool(p) and p.get("confidence", 0) >= 0.6
