from __future__ import annotations

"""runtime.events

Turn Event Protocol v1 (streamable, provider-agnostic, UI-agnostic).

This module intentionally contains *only*:
- a stable event envelope definition
- strongly-typed payload helpers
- a small factory for producing correctly ordered events

Wiring these events through LangGraph / nodes / UI is done elsewhere.
"""

from dataclasses import dataclass, field
import time
import uuid
from typing import Any, Dict, Literal, Optional, TypedDict, cast


# -------------------------
# Protocol constants (v1)
# -------------------------

EVENT_PROTOCOL_VERSION: int = 1

EventType = Literal[
    # turn lifecycle
    "turn_start",
    "turn_end",
    # node spans
    "node_start",
    "node_end",
    # thinking stream
    "thinking_start",
    "thinking_delta",
    "thinking_end",
    # assistant stream
    "assistant_start",
    "assistant_delta",
    "assistant_end",
    # world commit
    "world_commit",
    "world_update",
    "state_update",
    # structured logging
    "log_line",
]

LogLevel = Literal["debug", "info", "warning", "error"]

ThinkingStream = Literal["thinking"]
AssistantRole = Literal["you"]


class TurnEvent(TypedDict):
    """Event envelope for Turn Event Protocol v1."""

    v: int
    type: EventType
    turn_id: str
    seq: int
    ts_ms: int
    node_id: Optional[str]
    span_id: Optional[str]
    payload: Dict[str, Any]


# -------------------------
# Factory
# -------------------------


@dataclass
class TurnEventFactory:
    """Creates protocol-correct events for a single turn.

    - seq is monotonically increasing for the life of this factory
    - ts_ms is wall-clock epoch millis
    - span_id creation is centralized to avoid per-node divergence
    """

    turn_id: str
    _seq: int = 0
    _started_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def now_ms(self) -> int:
        return int(time.time() * 1000)

    def new_span_id(self, *, node_id: str) -> str:
        # Include node_id for grep/debug; uuid ensures global uniqueness.
        return f"{node_id}:{uuid.uuid4().hex}"

    def make(
        self,
        *,
        type: EventType,
        payload: Optional[Dict[str, Any]] = None,
        node_id: Optional[str] = None,
        span_id: Optional[str] = None,
        ts_ms: Optional[int] = None,
    ) -> TurnEvent:
        return TurnEvent(
            v=EVENT_PROTOCOL_VERSION,
            type=type,
            turn_id=self.turn_id,
            seq=self.next_seq(),
            ts_ms=self.now_ms() if ts_ms is None else int(ts_ms),
            node_id=node_id,
            span_id=span_id,
            payload=payload or {},
        )

    # -------------------------
    # Convenience constructors
    # -------------------------

    def turn_start(
        self,
        *,
        user_text: str,
        chat_turn_index: Optional[int] = None,
        provider: Optional[str] = None,
        models: Optional[Dict[str, str]] = None,
    ) -> TurnEvent:
        payload: Dict[str, Any] = {"user_text": user_text}
        if chat_turn_index is not None:
            payload["chat_turn_index"] = int(chat_turn_index)
        if provider is not None:
            payload["provider"] = str(provider)
        if models is not None:
            payload["models"] = dict(models)
        return self.make(type="turn_start", payload=payload)

    def turn_end_ok(self, *, duration_ms: Optional[int] = None) -> TurnEvent:
        payload: Dict[str, Any] = {"status": "ok"}
        if duration_ms is not None:
            payload["duration_ms"] = int(duration_ms)
        return self.make(type="turn_end", payload=payload)

    def turn_end_error(
        self,
        *,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> TurnEvent:
        payload: Dict[str, Any] = {
            "status": "error",
            "error": {"code": code, "message": message, "details": details or {}},
        }
        if duration_ms is not None:
            payload["duration_ms"] = int(duration_ms)
        return self.make(type="turn_end", payload=payload)

    def node_start(
        self,
        *,
        node_id: str,
        span_id: str,
        label: Optional[str] = None,
        attempt: int = 1,
    ) -> TurnEvent:
        payload: Dict[str, Any] = {"attempt": int(attempt)}
        if label is not None:
            payload["label"] = str(label)
        return self.make(type="node_start", node_id=node_id, span_id=span_id, payload=payload)

    def node_end_ok(self, *, node_id: str, span_id: str, duration_ms: Optional[int] = None) -> TurnEvent:
        payload: Dict[str, Any] = {"status": "ok"}
        if duration_ms is not None:
            payload["duration_ms"] = int(duration_ms)
        return self.make(type="node_end", node_id=node_id, span_id=span_id, payload=payload)

    def node_end_error(
        self,
        *,
        node_id: str,
        span_id: str,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
    ) -> TurnEvent:
        payload: Dict[str, Any] = {
            "status": "error",
            "error": {"code": code, "message": message, "details": details or {}},
        }
        if duration_ms is not None:
            payload["duration_ms"] = int(duration_ms)
        return self.make(type="node_end", node_id=node_id, span_id=span_id, payload=payload)

    def thinking_start(self, *, node_id: str, span_id: str, stream: ThinkingStream = "thinking") -> TurnEvent:
        return self.make(type="thinking_start", node_id=node_id, span_id=span_id, payload={"stream": stream})

    def thinking_delta(self, *, node_id: str, span_id: str, text: str, stream: ThinkingStream = "thinking") -> TurnEvent:
        return self.make(
            type="thinking_delta",
            node_id=node_id,
            span_id=span_id,
            payload={"stream": stream, "text": text},
        )

    def thinking_end(self, *, node_id: str, span_id: str, stream: ThinkingStream = "thinking") -> TurnEvent:
        return self.make(type="thinking_end", node_id=node_id, span_id=span_id, payload={"stream": stream})

    def log_line(
        self,
        *,
        level: LogLevel,
        message: str,
        logger: str,
        node_id: Optional[str] = None,
        span_id: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
    ) -> TurnEvent:
        payload: Dict[str, Any] = {
            "level": level,
            "message": message,
            "logger": logger,
            "fields": fields or {},
        }
        return self.make(type="log_line", node_id=node_id, span_id=span_id, payload=payload)

    def assistant_start(self, *, message_id: str, role: AssistantRole = "you") -> TurnEvent:
        return self.make(type="assistant_start", payload={"message_id": message_id, "role": role})

    def assistant_delta(self, *, message_id: str, text: str) -> TurnEvent:
        return self.make(type="assistant_delta", payload={"message_id": message_id, "text": text})

    def assistant_end(self, *, message_id: str) -> TurnEvent:
        return self.make(type="assistant_end", payload={"message_id": message_id})

    def world_commit(self, *, world_before: Dict[str, Any], world_after: Dict[str, Any], delta: Dict[str, Any]) -> TurnEvent:
        return self.make(
            type="world_commit",
            payload={"world_before": world_before, "world_after": world_after, "delta": delta},
        )

    def world_update(self, *, node_id: str, span_id: str, world: Dict[str, Any]) -> TurnEvent:
        return self.make(
            type="world_update",
            node_id=node_id,
            span_id=span_id,
            payload={"world": world},
        )

    def state_update(self, *, node_id: str, span_id: str, when: str, state: Dict[str, Any]) -> TurnEvent:
        # 'when' is typically "node_start" or "node_end"
        return self.make(
            type="state_update",
            node_id=node_id,
            span_id=span_id,
            payload={"when": when, "state": state},
        )


# -------------------------
# Validation helpers
# -------------------------


def is_turn_event(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    for k in ("v", "type", "turn_id", "seq", "ts_ms", "node_id", "span_id", "payload"):
        if k not in obj:
            return False
    if obj.get("v") != EVENT_PROTOCOL_VERSION:
        return False
    if not isinstance(obj.get("payload"), dict):
        return False
    return True


def assert_turn_event(obj: Any) -> TurnEvent:
    if not is_turn_event(obj):
        raise TypeError(f"Not a TurnEvent v{EVENT_PROTOCOL_VERSION}: {obj!r}")
    return cast(TurnEvent, obj)
