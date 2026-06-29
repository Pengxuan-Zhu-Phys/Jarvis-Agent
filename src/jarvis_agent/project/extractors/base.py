from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from jarvis_agent.project.parser import ParsedSource, TreeSitterParser


class BaseTreeSitterExtractor(ABC):
    language: str

    def __init__(self, parser: TreeSitterParser) -> None:
        self.parser = parser

    @abstractmethod
    def extract_symbols(self, parsed: ParsedSource, relative_path: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def extract_identifier_references(self, parsed: ParsedSource) -> list[tuple[str, int, str]]:
        raise NotImplementedError

    def node_text(self, parsed: ParsedSource, node) -> str:
        return parsed.text(node)

    def line_text(self, parsed: ParsedSource, line_number: int) -> str:
        lines = parsed.source.decode("utf-8", errors="ignore").splitlines()
        if not 1 <= line_number <= len(lines):
            return ""
        return lines[line_number - 1].strip()

    def make_symbol(
        self,
        *,
        name: str,
        kind: str,
        file: str,
        node,
        signature: str,
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "name": name,
            "file": file,
            "start_line": node.start_point.row + 1,
            "end_line": node.end_point.row + 1,
            "signature": signature.strip(),
        }
