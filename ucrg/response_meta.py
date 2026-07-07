"""Shared response metadata for API clients (ChatAgent, pyfunc serving)."""

from __future__ import annotations

from .answer_options import question_input_view, build_answer_surface, ui_widget_policy
from .engine import build_segment_progress


def build_response_meta(agent) -> dict:
    """Progress + active-question widget metadata for the frontend."""
    progress = build_segment_progress(
        agent.s.current_segment,
        done=agent.s.done,
    )
    current_question = question_input_view(agent._current)
    return {
        **progress,
        "current_question": current_question,
        "answer_surface": build_answer_surface(
            current_question,
            segment=agent.s.current_segment,
        ),
        "ui_widget_policy": ui_widget_policy(),
        "skipped_questions": sorted(agent.s.skipped_ids),
        "derived_answers": dict(agent.s.derived),
    }
