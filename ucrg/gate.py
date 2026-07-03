"""Decision gate — the ordered rule (escalate-up -> overlay -> readiness -> verdict),
parameterised by the per-cell trigger data in the engine JSON."""
from .engine import gate_rule


def gate_inputs_from(signals: dict, classification: dict) -> dict:
    p = classification.get("primary", {})
    level = p.get("level", 1)
    impact = "high" if "high" in (signals.get("impact"), signals.get("impact_failure")) else \
             ("medium" if signals.get("impact") == "medium" else "low")
    sensitivity = signals.get("sensitivity", "none") or "none"
    if signals.get("action") == "act" and signals.get("steps") == "multi" and signals.get("hitl") == "auto":
        posture = "autonomous"
    elif signals.get("writes") or signals.get("action") == "act":
        posture = "writes"
    else:
        posture = "assistive"
    scope = "cross-bu" if signals.get("sharing") else ("cross-system" if signals.get("multi_system") else "single")
    regulated = bool(signals.get("regulated"))
    return {"domain": p.get("domain", "AU"), "level": level, "impact": impact,
            "sensitivity": sensitivity, "posture": posture, "scope": scope, "regulated": regulated}


def run_decision_gate(inputs: dict) -> dict:
    d, level = inputs["domain"], inputs["level"]
    impact, sens = inputs["impact"], inputs["sensitivity"]
    posture, scope, regulated = inputs["posture"], inputs["scope"], inputs["regulated"]
    rule = gate_rule(d, level)
    triggers, conditions = [], []

    # 1) escalate-up check (L1-2)
    if level <= 2:
        if sens != "none": triggers.append("sensitive data at a low level")
        if posture in ("writes", "autonomous"): triggers.append("it takes actions / writes")
        if scope in ("cross-system", "cross-bu"): triggers.append("spans multiple systems")
        if impact == "high": triggers.append("high impact")
        if triggers:
            return {"verdict": "ESCALATE", "level_used": level, "recommended_level": level + 1,
                    "reason": "Under-provisioned for its risk — re-scope to the next level.",
                    "triggers": triggers, "conditions": [], "rule": rule, "provisional": False,
                    "inputs": inputs}

    # 2) overlay check (L3+)
    overlay = []
    if level >= 3:
        if impact == "high": overlay += ["impact assessment", "board / ethics review"]
        if sens != "none": overlay += ["data-protection review (DPIA)"]
        if regulated: overlay += ["fairness assessment", "human oversight on high-stakes", "dual approval"]
        if scope in ("cross-bu",): overlay += ["data-sharing agreements (DPAs)", "purpose-limitation review"]

    # 3) readiness gate (L4-5) — provisional
    provisional = False
    if level >= 4:
        conditions.append("L%d governance must be confirmable: model lifecycle, monitoring, ethics board" % level)
        provisional = True

    # compose verdict
    if level <= 2 and not overlay:
        verdict = "APPROVE"
    elif overlay or level >= 3:
        verdict = "APPROVE_WITH_ENHANCED_GOVERNANCE"
    else:
        verdict = "APPROVE"

    note = ""
    if provisional:
        note = ("Provisional — if Dev/Governance cannot meet the conditions, "
                "the verdict becomes REDESIGN_DOWN, or REJECT only when impact is high / domain is regulated.")

    return {"verdict": verdict, "level_used": level, "recommended_level": level,
            "reason": "Proceed at this level" + (" with the governance overlay." if overlay else "."),
            "triggers": triggers, "overlay": overlay, "conditions": conditions,
            "provisional": provisional, "note": note, "rule": rule, "inputs": inputs}
