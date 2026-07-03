# Framework Scorecard

## Classification (internal — for the development team)
- Domain: Generative AI (GA)
- Maturity level: L3 — grounded in your data
- Confidence: 0.88

## Decision-gate verdict
- Verdict: **APPROVE_WITH_ENHANCED_GOVERNANCE**
- Level used: L3
- Reason: Proceed at this level.

## Gate inputs
- domain: GA
- level: 3
- impact: low
- sensitivity: none
- posture: writes
- scope: single
- regulated: False

## Open-items register (for Development / Security / Legal)
_14 technical questions tagged out of the interview._

- [GA-INF-1.1] (InfoSec) How are model API keys and access to the GenAI service protected (RBAC, MFA, network restrictions)?
- [GA-INF-1.2] (InfoSec) Could any prompts or outputs expose secrets or sensitive operational details, even if we don't intend to send such data?
- [GA-INF-1.3] (InfoSec) Are we restricting use to approved providers only (no shadow AI / unapproved SaaS)?
- [GA-DGP-1.2] (Data Governance) Do we have a DPA with the model provider, and do we know how long they retain and use our prompts/outputs?
- [GA-INF-2.1] (InfoSec) Who can create, edit, or approve exemplar prompts, and is there an audit trail for those changes?
- [GA-INF-2.2] (InfoSec) Have we checked that exemplars cannot accidentally leak credentials, internal configs, or sensitive system behaviour?
- [GA-INF-2.3] (InfoSec) Have we run basic adversarial/prompt-injection tests against our exemplar-based prompts before wider rollout?
- [GA-DGP-2.2] (Data Governance) Is provenance, consent, and classification for exemplar data recorded (source, permitted use, retention)?
- [GA-DGP-2.3] (Data Governance) Does our agreement with the provider clearly state whether exemplars/prompts can or cannot be used for their own training?
- [GA-AIG-2.3] (AI Governance) Are prompt/exemplar changes reviewed and approved by someone accountable (not just edited ad-hoc)?
- [GA-INF-3.1] (InfoSec) Who has write access to the RAG corpus and pipelines, and how is that access technically enforced (roles, service accounts, CI/CD)?
- [GA-INF-3.2] (InfoSec) Are the vector store, embedding service, and RAG APIs isolated and monitored (network segmentation, logging, SOC integration)?
- [GA-INF-3.3] (InfoSec) What controls detect and respond to RAG corpus poisoning (malicious or manipulated documents entering the KB)?
- [GA-DGP-3.2] (Data Governance) Are PII and Restricted data in the corpus subject to documented ingestion rules (redaction, minimisation, retention, deletion)?
