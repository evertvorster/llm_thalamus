from __future__ import annotations

from typing import Literal, TypedDict


class NodeStartEvent(TypedDict):
    type: Literal["node_start"]
    node: str


class NodeEndEvent(TypedDict):
    type: Literal["node_end"]
    node: str


class LogEvent(TypedDict):
    type: Literal["log"]
    text: str


class FinalEvent(TypedDict):
    type: Literal["final"]
    answer: str


Event = NodeStartEvent | NodeEndEvent | LogEvent | FinalEvent
