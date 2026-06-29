from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis_agent.project.extractors import CppTreeSitterExtractor, PythonTreeSitterExtractor
from jarvis_agent.project.parser import ParsedSource, TreeSitterParser


class SymbolExtractor:
    def __init__(self, parser: TreeSitterParser | None = None) -> None:
        self.parser = parser or TreeSitterParser()
        self.extractors = {
            "python": PythonTreeSitterExtractor(self.parser),
            "cpp": CppTreeSitterExtractor(self.parser),
        }

    def extract(self, path: Path, relative_path: str, language: str) -> list[dict[str, Any]]:
        parsed = self.parse(path, language)
        if parsed is None:
            return []
        extractor = self.extractors.get(language)
        if extractor is None:
            return []
        return extractor.extract_symbols(parsed, relative_path)

    def parse(self, path: Path, language: str) -> ParsedSource | None:
        if language not in self.extractors:
            return None
        return self.parser.parse(path, language)

    def extract_identifier_references(self, parsed: ParsedSource) -> list[tuple[str, int, str]]:
        extractor = self.extractors.get(parsed.language)
        if extractor is None:
            return []
        return extractor.extract_identifier_references(parsed)
