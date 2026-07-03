"""MLflow pyfunc wrapper for Databricks Model Serving.

Stateless turn protocol — the client passes back `session_state` on every call so
replicas can scale without sticky sessions.

Request columns (DataFrame or single dict):
  action         start | send | reset
  session_id     client correlation id (echoed back)
  message        user text (required for send)
  session_state  JSON blob from prior response (required for send after start)

Response columns:
  session_id, message, done, session_state, output_json, error
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import mlflow.pyfunc
import pandas as pd

from .driver import UCRGAgent


def _read_system_prompt(context) -> str:
    artifact = (context.artifacts or {}).get("system_prompt")
    if artifact:
        return Path(artifact).read_text(encoding="utf-8")
    bundled = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"
    return bundled.read_text(encoding="utf-8") if bundled.exists() else ""


def _backend(context) -> str:
    cfg = context.model_config or {}
    return cfg.get("backend") or os.environ.get("UCRG_LLM_BACKEND", "anthropic")


def _row_value(row, key: str, default: str = "") -> str:
    if key not in row.index:
        return default
    val = row[key]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return default
    return str(val)


def _handle(action: str, session_id: str, message: str, session_state: str,
            backend: str, system_prompt: str) -> dict:
    action = (action or "send").strip().lower()
    session_id = session_id or "default"

    if action == "reset":
        return {
            "session_id": session_id,
            "message": "",
            "done": False,
            "session_state": "",
            "output_json": "",
            "error": "",
        }

    if action == "start":
        agent = UCRGAgent(backend=backend, system_prompt=system_prompt)
        msg = agent.start()
        blob = agent.dump_session()
        return {
            "session_id": session_id,
            "message": msg,
            "done": False,
            "session_state": UCRGAgent.dumps_session(blob),
            "output_json": "",
            "error": "",
        }

    if action == "send":
        if not session_state:
            return {
                "session_id": session_id,
                "message": "",
                "done": False,
                "session_state": "",
                "output_json": "",
                "error": "session_state is required for action=send",
            }
        try:
            blob = UCRGAgent.loads_session(session_state)
            agent = UCRGAgent.load_session(blob, backend=backend, system_prompt=system_prompt)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            return {
                "session_id": session_id,
                "message": "",
                "done": False,
                "session_state": session_state,
                "output_json": "",
                "error": f"invalid session_state: {exc}",
            }

        result = agent.send(message)
        out_blob = agent.dump_session()
        output_json = ""
        if result.get("output"):
            output_json = json.dumps(result["output"], ensure_ascii=False)
        return {
            "session_id": session_id,
            "message": result.get("message", ""),
            "done": bool(result.get("done")),
            "session_state": UCRGAgent.dumps_session(out_blob),
            "output_json": output_json,
            "error": "",
        }

    return {
        "session_id": session_id,
        "message": "",
        "done": False,
        "session_state": session_state,
        "output_json": "",
        "error": f"unknown action: {action}",
    }


class UCRGServingModel(mlflow.pyfunc.PythonModel):
    """Register with code_paths=['ucrg', 'data', 'prompts']."""

    def load_context(self, context):
        engine_path = (context.artifacts or {}).get("ucrg_engine")
        if engine_path:
            os.environ["UCRG_ENGINE_PATH"] = engine_path
        self.system_prompt = _read_system_prompt(context)
        self.backend = _backend(context)

    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        backend = self.backend or _backend(context)
        system_prompt = self.system_prompt or _read_system_prompt(context)

        if isinstance(model_input, dict):
            model_input = pd.DataFrame([model_input])

        rows = []
        for _, row in model_input.iterrows():
            rows.append(_handle(
                action=_row_value(row, "action", "send"),
                session_id=_row_value(row, "session_id"),
                message=_row_value(row, "message"),
                session_state=_row_value(row, "session_state"),
                backend=backend,
                system_prompt=system_prompt,
            ))
        return pd.DataFrame(rows)
