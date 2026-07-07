"""Shared response metadata for API clients (ChatAgent, pyfunc serving)."""

from __future__ import annotations

from .answer_options import question_input_view
from .engine import build_segment_progress


def build_response_meta(agent) -> dict:
    """Progress + active-question widget metadata for the frontend."""
    progress = build_segment_progress(
        agent.s.current_segment,
        done=agent.s.done,
    )
    return {
        **progress,
        "current_question": question_input_view(agent._current),
        "skipped_questions": sorted(agent.s.skipped_ids),
        "derived_answers": dict(agent.s.derived),
    }
