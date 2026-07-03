# Framework Scorecard

## Classification (internal — for the development team)
- Domain: Data Science & Analytics (DS)
- Maturity level: L3 — predicts outcomes
- Confidence: 0.88

## Decision-gate verdict
- Verdict: **APPROVE_WITH_ENHANCED_GOVERNANCE**
- Level used: L3
- Reason: Proceed at this level.

## Gate inputs
- domain: DS
- level: 3
- impact: low
- sensitivity: none
- posture: writes
- scope: single
- regulated: False

## Open-items register (for Development / Security / Legal)
_15 technical questions tagged out of the interview._

- [DS-INF-1.1] (InfoSec) Who can access sensitive dashboards/reports, and is access role-based and logged?
- [DS-INF-1.2] (InfoSec) Can BI tools or users accidentally change production data, or are they strictly read-only?
- [DS-INF-1.3] (InfoSec) Are ETL/BI configuration changes (e.g. KPI definitions) tracked and auditable?
- [DS-DGP-1.2] (Data Governance) Do dashboards with personal or sensitive data enforce minimisation and role-based access?
- [DS-INF-2.1] (InfoSec) How is code and configuration (e.g. analysis scripts) version-controlled and reviewed?
- [DS-INF-2.2] (InfoSec) Can analysts export large volumes of sensitive data without oversight?
- [DS-INF-2.3] (InfoSec) Are there controls on data egress from analytic sandboxes (no uncontrolled local copies)?
- [DS-DGP-2.2] (Data Governance) How long do we retain analytic extracts, and where are they stored?
- [DS-AIG-2.1] (AI Governance) Are we careful not to treat correlations found in diagnostic analysis as causal without additional evidence?
- [DS-AIG-2.3] (AI Governance) Are key assumptions and limitations of diagnostic studies documented and communicated?
- [DS-INF-3.1] (InfoSec) Are model APIs/score services protected with authentication, authorisation, and rate limits?
- [DS-INF-3.2] (InfoSec) Are model-serving environments segregated (network, IAM) from user-facing applications and the open internet?
- [DS-INF-3.3] (InfoSec) Are model calls and errors logged in a way that supports security monitoring and incident investigation?
- [DS-DGP-3.2] (Data Governance) Has a DPIA been completed for models that materially impact individuals (risk, eligibility, pricing)?
- [DS-DGP-3.3] (Data Governance) Are retention and deletion rules defined for model training datasets and feature stores?
