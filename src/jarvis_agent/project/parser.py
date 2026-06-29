from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Parser, Query, QueryCursor, Tree
import tree_sitter_cpp
import tree_sitter_python


@dataclass(frozen=True)
class ParsedSource:
    path: Path
    language: str
    source: bytes
    tree: Tree

    def text(self, node) -> str:
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")


class TreeSitterParser:
    def __init__(self) -> None:
        self.languages = {
            "python": Language(tree_sitter_python.language()),
            "cpp": Language(tree_sitter_cpp.language()),
        }
        self.parsers = {name: Parser(language) for name, language in self.languages.items()}

    def supports(self, language: str) -> bool:
        return language in self.parsers

    def parse(self, path: Path, language: str) -> ParsedSource | None:
        parser = self.parsers.get(language)
        if parser is None:
            return None
        try:
            source = path.read_bytes()
        except OSError:
            return None
        return ParsedSource(path=path, language=language, source=source, tree=parser.parse(source))

    def query(self, language: str, query: str) -> Query:
        return Query(self.languages[language], query)

    def matches(self, parsed: ParsedSource, query: str):
        compiled = self.query(parsed.language, query)
        return QueryCursor(compiled).matches(parsed.tree.root_node)

    def captures(self, parsed: ParsedSource, query: str):
        compiled = self.query(parsed.language, query)
        return QueryCursor(compiled).captures(parsed.tree.root_node)
