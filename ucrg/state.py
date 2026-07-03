"""Shared agent state — one accumulating understanding, used by both the
lightweight driver and the LangGraph graph."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UCRGState:
    current_segment: int = 0                       # 0 before start, then 1..7
    answers: dict = field(default_factory=dict)    # {question_id: answer_text}
    signals: dict = field(default_factory=dict)    # extracted gate/classification signals
    classification: dict = field(default_factory=dict)   # {"primary": {domain, level, confidence}, "domains": [...]}
    open_items: list = field(default_factory=list)       # tagged Dev/Sec/Legal questions (deduped by id)
    asked_followup_ids: set = field(default_factory=set)
    attempts: dict = field(default_factory=dict)         # question_id -> rephrase attempts
    gate_verdict: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)           # {"sdd": str, "scorecard": str}
    transcript: list = field(default_factory=list)       # [(role, text), ...]
    done: bool = False
