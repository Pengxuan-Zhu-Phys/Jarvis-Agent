from __future__ import annotations

from dataclasses import dataclass, field

from rich.cells import cell_len


@dataclass
class TurnRecord:
    prompt: str
    timestamp: str
    created_at: float
    output: str = ""
    metrics: str = ""
    metrics_detail: str = ""
    context_tokens: int | None = None


@dataclass
class HistoryModel:
    """Pure turn-history state used by the Textual view."""

    records: list[TurnRecord] = field(default_factory=list)
    current_turn_index: int | None = None
    expanded_turn_prompts: set[int] = field(default_factory=set)

    def add_turn(self, record: TurnRecord) -> int:
        self.records.append(record)
        self.current_turn_index = len(self.records) - 1
        self.expanded_turn_prompts.clear()
        return self.current_turn_index

    def visible_turn_index(self, visible_index: int, expanded: bool) -> int | None:
        if not self.records:
            return None
        turn_index = visible_index if expanded else self.current_turn_index if self.current_turn_index is not None else len(self.records) - 1
        return turn_index if 0 <= turn_index < len(self.records) else None

    def toggle_prompt(self, turn_index_value, *, max_prompt_chars: int) -> bool:
        try:
            turn_index = int(turn_index_value)
        except (TypeError, ValueError):
            return False
        if not 0 <= turn_index < len(self.records):
            return False
        if not prompt_needs_expansion(self.records[turn_index].prompt, max_prompt_chars):
            return False
        if turn_index in self.expanded_turn_prompts:
            self.expanded_turn_prompts.remove(turn_index)
        else:
            self.expanded_turn_prompts.add(turn_index)
        return True


def prompt_needs_expansion(prompt: str, max_prompt_chars: int) -> bool:
    """Return whether a prompt needs expanded display in the history panel."""

    return "\n" in prompt or cell_len(prompt) > max_prompt_chars


def history_toggle_label(index: int, expanded: bool = False) -> str:
    return ("▾" if expanded else "▸") + f" {index}"


def history_index_label(index: int) -> str:
    return f"  {index}"
