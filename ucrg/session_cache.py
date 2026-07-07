"""In-process session caches for stateless Model Serving (Playground / Review App)."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable, Generic, Optional, TypeVar

from mlflow.types.agent import ChatAgentMessage, ChatContext

T = TypeVar("T")
_CACHE_MAX = 256


class _LruCache(Generic[T]):
    def __init__(self, maxsize: int = _CACHE_MAX) -> None:
        self._data: OrderedDict[str, T] = OrderedDict()
        self._max = maxsize
        self._lock = threading.Lock()

    def get(self, key: str) -> T | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def set(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)


class TurnCache(Generic[T]):
    """Caches (state, processed_user_count) keyed by conversation id."""

    def __init__(self, maxsize: int = _CACHE_MAX) -> None:
        self._inner = _LruCache[tuple[T, int]](maxsize)

    def get(self, key: str) -> tuple[T, int] | None:
        return self._inner.get(key)

    def set(self, key: str, state: T, user_msg_count: int) -> None:
        self._inner.set(key, (state, user_msg_count))


class SnapshotCache:
    """Caches serialized session blobs keyed by assistant message id."""

    def __init__(self, maxsize: int = _CACHE_MAX) -> None:
        self._inner = _LruCache[str](maxsize)

    def get(self, key: str) -> str | None:
        return self._inner.get(key)

    def set(self, key: str, snapshot: str) -> None:
        self._inner.set(key, snapshot)


def conversation_key(
    context: Optional[ChatContext | dict[str, Any]],
    custom_inputs: dict[str, Any],
) -> str | None:
    """Resolve Playground conversation id from every field serving may populate."""
    if context is not None:
        if isinstance(context, dict):
            cid = context.get("conversation_id")
        else:
            cid = getattr(context, "conversation_id", None)
        if isinstance(cid, str) and cid:
            return cid

    for src in (
        custom_inputs,
        custom_inputs.get("context"),
        custom_inputs.get("databricks_options"),
    ):
        if isinstance(src, dict):
            cid = src.get("conversation_id")
            if isinstance(cid, str) and cid:
                return cid

    sid = custom_inputs.get("session_id")
    return sid if isinstance(sid, str) and sid else None


def parent_assistant_key(messages: list[ChatAgentMessage]) -> str | None:
    """Playground echoes assistant ``id`` on the next turn — chain state from it."""
    last_user_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_idx = i
            break
    if last_user_idx is None or last_user_idx == 0:
        return None
    for i in range(last_user_idx - 1, -1, -1):
        if messages[i].role != "assistant":
            continue
        mid = getattr(messages[i], "id", None)
        if isinstance(mid, str) and mid:
            return f"asst:{mid}"
        break
    return None


def apply_new_user_messages(
    user_messages: list[ChatAgentMessage],
    processed: int,
    apply_turn: Callable[[str], Any],
) -> Any:
    result: Any = None
    for msg in user_messages[processed:]:
        result = apply_turn(msg.content or "")
    return result
