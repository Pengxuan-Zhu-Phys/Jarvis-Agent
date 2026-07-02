from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias


PROTOCOL_VERSION = 1
_RESERVED_METADATA_KEYS = {"protocol_version"}


@dataclass(frozen=True, slots=True)
class UserPrompt:
    """User turn entering the transcript."""

    text: str
    timestamp: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssistantTextDelta:
    """Streamed assistant text chunk."""

    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssistantTextEnd:
    """Assistant text stream completion marker."""

    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    """Tool invocation start marker."""

    name: str
    args: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Tool invocation result output."""

    name: str
    output: str
    ok: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LogLine:
    """Line appended to the active live log block."""

    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Status:
    """Transient status message."""

    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Error:
    """Error message entering the transcript."""

    message: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Metrics:
    """Model or runtime metrics summary."""

    summary: str
    detail: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Summary:
    """Structured summary block."""

    title: str
    body: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


AgentEvent: TypeAlias = (
    UserPrompt
    | AssistantTextDelta
    | AssistantTextEnd
    | ToolCallStarted
    | ToolResult
    | LogLine
    | Status
    | Error
    | Metrics
    | Summary
)

_AGENT_EVENT_TYPES = (
    UserPrompt,
    AssistantTextDelta,
    AssistantTextEnd,
    ToolCallStarted,
    ToolResult,
    LogLine,
    Status,
    Error,
    Metrics,
    Summary,
)


def validate_event(event: AgentEvent) -> None:
    """Validate an event against the v1 protocol contract."""

    if not isinstance(event, _AGENT_EVENT_TYPES):
        raise TypeError(f"unsupported agent event: {type(event).__name__}")

    metadata = getattr(event, "metadata", {})
    if not isinstance(metadata, Mapping):
        raise TypeError("event metadata must be a mapping")

    protocol_version = metadata.get("protocol_version", PROTOCOL_VERSION)
    if not isinstance(protocol_version, int):
        raise TypeError("metadata protocol_version must be an integer")
    if protocol_version > PROTOCOL_VERSION:
        raise ValueError(f"event protocol version {protocol_version} is newer than supported version {PROTOCOL_VERSION}")

    unknown_reserved = _RESERVED_METADATA_KEYS.intersection(metadata) - {"protocol_version"}
    if unknown_reserved:
        keys = ", ".join(sorted(unknown_reserved))
        raise ValueError(f"reserved metadata keys are not allowed: {keys}")
