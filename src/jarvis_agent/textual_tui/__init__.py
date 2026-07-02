from __future__ import annotations

from jarvis_agent.config import AgentConfig

from .errors import TextualUnavailable
from .gitinfo import GitInfo, get_git_info
from .text_utils import (
    _compact_middle_path,
    _compact_path,
    _escape_markup,
    _exact_time_label,
    _format_token_count,
    _home_relative_path,
    _relative_time_label,
    _single_line,
    compact_metrics,
    current_time_label,
    estimate_context_tokens,
    location_to_text_index,
    pacman_ghost_frame,
    parse_context_metric_tokens,
    ping_pong_offset,
    slash_suggestion_context,
    split_output_metrics,
    split_output_metrics_detail,
    text_index_to_location,
    wrap_output_text,
    wrap_plain_text,
)


def run_textual_ui(config: AgentConfig) -> int:
    try:
        from .app import JarvisAgentApp
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise TextualUnavailable("Textual is not installed. Install with: pip install -e '.[tui]'") from exc

    JarvisAgentApp(config).run()
    return 0


__all__ = [
    "GitInfo",
    "TextualUnavailable",
    "_compact_middle_path",
    "_compact_path",
    "_escape_markup",
    "_exact_time_label",
    "_format_token_count",
    "_home_relative_path",
    "_relative_time_label",
    "_single_line",
    "compact_metrics",
    "current_time_label",
    "estimate_context_tokens",
    "get_git_info",
    "location_to_text_index",
    "pacman_ghost_frame",
    "parse_context_metric_tokens",
    "ping_pong_offset",
    "run_textual_ui",
    "slash_suggestion_context",
    "split_output_metrics",
    "split_output_metrics_detail",
    "text_index_to_location",
    "wrap_output_text",
    "wrap_plain_text",
]
