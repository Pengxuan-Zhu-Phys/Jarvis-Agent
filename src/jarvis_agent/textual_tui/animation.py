from __future__ import annotations

from dataclasses import dataclass

from .text_utils import pacman_ghost_frame, ping_pong_offset


@dataclass(frozen=True, slots=True)
class LogoMonitorConfig:
    rows: int = 8
    cols_per_side: int = 4
    reveal_frames: int = 8
    monitor_frames: int = 18


LEFT_MONITOR_SERIES = (
    (1, 2, 1, 3, 2, 4, 1, 2),
    (2, 1, 3, 2, 4, 2, 3, 1),
    (1, 3, 4, 1, 2, 3, 2, 4),
    (3, 2, 1, 4, 3, 1, 4, 2),
    (2, 4, 2, 3, 1, 4, 2, 1),
    (4, 1, 2, 2, 3, 2, 1, 3),
)
RIGHT_MONITOR_SERIES = (
    (2, 1, 3, 1, 4, 2, 1, 3),
    (1, 3, 2, 4, 2, 1, 3, 2),
    (3, 2, 4, 1, 3, 2, 4, 1),
    (4, 1, 2, 3, 1, 4, 2, 3),
    (2, 4, 1, 2, 3, 1, 4, 2),
    (1, 2, 3, 4, 2, 3, 1, 4),
)


def render_logo_monitor_frame(
    frame: int,
    logo_pattern: tuple[str, ...],
    left_logo_widths: tuple[int, ...],
    right_logo_widths: tuple[int, ...],
    config: LogoMonitorConfig = LogoMonitorConfig(),
) -> str:
    """Render the animated logo monitor frame."""

    reveal_row = min(frame, config.rows - 1)
    final_phase = frame >= config.reveal_frames + config.monitor_frames
    rows: list[str] = []
    for y in range(config.rows):
        cells: list[str] = []
        for x in range(config.rows):
            color = logo_cell_color(
                x,
                y,
                frame,
                reveal_row,
                final_phase,
                logo_pattern,
                left_logo_widths,
                right_logo_widths,
                config,
            )
            cells.append(f"[{color}]⬤[/]")
        rows.append(" ".join(cells))
    return "\n".join(rows)


def logo_cell_color(
    x: int,
    y: int,
    frame: int,
    reveal_row: int,
    final_phase: bool,
    logo_pattern: tuple[str, ...],
    left_logo_widths: tuple[int, ...],
    right_logo_widths: tuple[int, ...],
    config: LogoMonitorConfig = LogoMonitorConfig(),
) -> str:
    left_background = "#2f7fd8"
    left_active = "#ffffff"
    right_background = "#134a8d"
    right_active = "#f6d33f"
    inactive = "#303745"

    if y > reveal_row:
        return inactive

    if final_phase:
        cell = logo_pattern[y][x]
        if x < config.cols_per_side:
            return left_active if cell == "W" else left_background
        return right_active if cell == "Y" else right_background

    if x < config.cols_per_side:
        widths = current_monitor_widths("left", frame, left_logo_widths, right_logo_widths, config)
        active = x >= config.cols_per_side - widths[y]
        return left_active if active else left_background
    widths = current_monitor_widths("right", frame, left_logo_widths, right_logo_widths, config)
    active = x - config.cols_per_side < widths[y]
    return right_active if active else right_background


def current_monitor_widths(
    side: str,
    frame: int,
    left_logo_widths: tuple[int, ...],
    right_logo_widths: tuple[int, ...],
    config: LogoMonitorConfig = LogoMonitorConfig(),
) -> tuple[int, ...]:
    series = LEFT_MONITOR_SERIES if side == "left" else RIGHT_MONITOR_SERIES
    index = max(0, frame - config.reveal_frames)
    if index >= config.monitor_frames - 6:
        return left_logo_widths if side == "left" else right_logo_widths
    return series[index % len(series)]


__all__ = [
    "LogoMonitorConfig",
    "current_monitor_widths",
    "logo_cell_color",
    "pacman_ghost_frame",
    "ping_pong_offset",
    "render_logo_monitor_frame",
]
