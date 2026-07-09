"""MLflow ChatAgent wrapper around the UCRG interview agent.

Deployed via mlflow.pyfunc.log_model(python_model=__file__, code_paths=[...])
and databricks.agents.deploy(...). Becomes an OpenAI-compatible Model Serving
endpoint visible in the Databricks Playground / Review App.

State persistence
-----------------
Model Serving is stateless. The client round-trips ``session_state`` through
``custom_inputs`` / ``custom_outputs`` each turn:

    First turn:
        messages       = [{"role": "user", "content": "hi"}]
        custom_inputs  = {}
    Response:
        messages       = [{"role": "assistant", "content": "<greeting + Q1>"}]
        custom_outputs = {..., "session_state": "<json blob>"}

    Subsequent turns (production frontend):
        custom_inputs  = {"session_state": <prior custom_outputs.session_state>}

    Playground / Review App (text-only, no state echo):
        The full ``messages[]`` history is replayed each turn — first user
        message is the conversation opener; later messages are answers.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from mlflow.models import set_model
from mlflow.pyfunc import ChatAgent
from mlflow.types.agent import (
    ChatAgentChunk,
    ChatAgentMessage,
    ChatAgentResponse,
    ChatContext,
)

from ucrg.driver import UCRGAgent
from ucrg.response_meta import build_response_meta
from ucrg.session_cache import (
    SnapshotCache,
    TurnCache,
    apply_new_user_messages,
    conversation_key,
    parent_assistant_key,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ucrg_databricks_agent")


def _system_prompt_path() -> Path:
    env = os.environ.get("UCRG_SYSTEM_PROMPT_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "prompts" / "system_prompt.md"


def _read_system_prompt() -> str:
    path = _system_prompt_path()
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _backend() -> str:
    return os.environ.get("UCRG_LLM_BACKEND", "databricks")


def _build_view(agent: UCRGAgent, result: dict[str, Any]) -> dict[str, Any]:
    output_json = ""
    if result.get("output"):
        output_json = json.dumps(result["output"], ensure_ascii=False)
    return {
        "session_state": UCRGAgent.dumps_session(agent.dump_session()),
        "done": bool(result.get("done", agent.s.done)),
        "output_json": output_json,
        "current_segment": agent.s.current_segment,
        "classification": agent.s.classification,
        "gate_verdict": agent.s.gate_verdict,
        "open_items": agent.s.open_items,
        **build_response_meta(agent),
    }


def _format_assistant_text(result: dict[str, Any]) -> str:
    text = result.get("message", "") or ""
    if result.get("done") and result.get("output"):
        out = result["output"]
        sdd = out.get("sdd", "")
        scorecard = out.get("scorecard", "")
        if sdd or scorecard:
            text = (
                f"{text}\n\n--- SDD ---\n{sdd}\n\n--- Scorecard ---\n{scorecard}"
            )
    return text


def _new_agent() -> UCRGAgent:
    return UCRGAgent(backend=_backend(), system_prompt=_read_system_prompt())


def _apply_user_turn(agent: UCRGAgent, user_text: str) -> dict[str, Any]:
    return agent.send((user_text or "").strip())


def _load_agent(blob: dict) -> UCRGAgent:
    return UCRGAgent.load_session(
        blob, backend=_backend(), system_prompt=_read_system_prompt()
    )


def _snapshot_agent(agent: UCRGAgent) -> str:
    return UCRGAgent.dumps_session(agent.dump_session())


# Playground does not round-trip session_state. Cache by conversation_id and,
# as fallback, by the assistant message id Playground echoes on the next turn.
_CONV_CACHE = TurnCache[UCRGAgent]()
_ASST_CACHE = SnapshotCache()


def _replay_from_messages(user_messages: list[ChatAgentMessage]) -> tuple[UCRGAgent, dict[str, Any]]:
    agent = _new_agent()
    greeting = agent.start()
    if len(user_messages) <= 1:
        return agent, {"message": greeting, "done": False}
    result: dict[str, Any] = {"message": greeting, "done": False}
    for msg in user_messages[1:]:
        result = _apply_user_turn(agent, msg.content or "")
    return agent, result


def _last_agent_message(agent: UCRGAgent) -> dict[str, Any]:
    last_agent = next(
        (t for role, t in reversed(agent.s.transcript) if role == "agent"),
        "",
    )
    return {"message": last_agent, "done": agent.s.done}


class UCRGChatAgent(ChatAgent):
    """ChatAgent that wraps the UCRG start/send interview loop."""

    def predict(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ) -> ChatAgentResponse:
        ci = custom_inputs or {}
        prior = ci.get("session_state")
        user_messages = [m for m in messages if m.role == "user"]
        conv_key = conversation_key(context, ci)
        parent_key = parent_assistant_key(messages)
        agent: UCRGAgent
        result: dict[str, Any]
        path = "fast"
        processed = 0

        if prior:
            try:
                blob = prior if isinstance(prior, dict) else UCRGAgent.loads_session(prior)
                agent = _load_agent(blob)
                last_user = user_messages[-1] if user_messages else None
                if last_user is not None:
                    result = _apply_user_turn(agent, last_user.content or "")
                else:
                    result = {"message": "", "done": agent.s.done}
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("invalid session_state, falling back: %s", exc)
                path = "replay"
                agent, result = _replay_from_messages(user_messages)

        elif conv_key and (cached := _CONV_CACHE.get(conv_key)):
            path = "conv-cache"
            agent, processed = cached
            if len(user_messages) > processed:
                result = apply_new_user_messages(
                    user_messages,
                    processed,
                    lambda text: _apply_user_turn(agent, text),
                )
            else:
                result = _last_agent_message(agent)

        elif parent_key and (snap := _ASST_CACHE.get(parent_key)):
            path = "asst-cache"
            agent = _load_agent(UCRGAgent.loads_session(snap))
            last_user = user_messages[-1] if user_messages else None
            if last_user is not None:
                result = _apply_user_turn(agent, last_user.content or "")
            else:
                result = _last_agent_message(agent)

        else:
            path = "replay"
            agent, result = _replay_from_messages(user_messages)

        response_id = str(uuid.uuid4())
        if conv_key:
            _CONV_CACHE.set(conv_key, agent, len(user_messages))
        _ASST_CACHE.set(f"asst:{response_id}", _snapshot_agent(agent))

        log.info(
            "predict | path=%s conv=%s parent=%s user_msgs=%d segment=%d",
            path,
            conv_key or "-",
            parent_key or "-",
            len(user_messages),
            agent.s.current_segment,
        )

        view = _build_view(agent, result)
        if result.get("baseline_category"):
            view["baseline_category"] = result["baseline_category"]
        view["debug"] = {
            "path": path,
            "conversation_id": conv_key,
            "parent_assistant_key": parent_key,
            "user_msgs": len(user_messages),
            "response_id": response_id,
        }
        assistant_text = _format_assistant_text(result)

        return ChatAgentResponse(
            messages=[
                ChatAgentMessage(
                    role="assistant",
                    content=assistant_text,
                    id=response_id,
                )
            ],
            custom_outputs=view,
        )

    def predict_stream(
        self,
        messages: list[ChatAgentMessage],
        context: Optional[ChatContext] = None,
        custom_inputs: Optional[dict[str, Any]] = None,
    ):
        """Streaming interface required by Databricks Playground / Review App."""
        response = self.predict(messages, context, custom_inputs)
        msg = (
            response.messages[-1]
            if response.messages
            else ChatAgentMessage(role="assistant", content="", id=str(uuid.uuid4()))
        )
        yield ChatAgentChunk(delta=msg, custom_outputs=response.custom_outputs)


AGENT = UCRGChatAgent()
set_model(AGENT)
