from __future__ import annotations

from typing import Any

from jarvis_agent.project.extractors.base import BaseTreeSitterExtractor
from jarvis_agent.project.parser import ParsedSource


class PythonTreeSitterExtractor(BaseTreeSitterExtractor):
    language = "python"

    SYMBOL_QUERY = """
    (class_definition
      name: (identifier) @name) @definition.class

    (function_definition
      name: (identifier) @name
      parameters: (parameters) @parameters) @definition.function
    """

    REFERENCE_QUERY = """
    (identifier) @reference
    """

    def extract_symbols(self, parsed: ParsedSource, relative_path: str) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        for _, captures in self.parser.matches(parsed, self.SYMBOL_QUERY):
            name_node = first_capture(captures, "name")
            if name_node is None:
                continue
            name = self.node_text(parsed, name_node)
            if class_node := first_capture(captures, "definition.class"):
                symbols.append(
                    self.make_symbol(
                        name=name,
                        kind="class",
                        file=relative_path,
                        node=class_node,
                        signature=f"class {name}",
                    )
                )
                continue
            if function_node := first_capture(captures, "definition.function"):
                parameters_node = first_capture(captures, "parameters")
                parameters = self.node_text(parsed, parameters_node) if parameters_node is not None else "()"
                symbols.append(
                    self.make_symbol(
                        name=name,
                        kind="function",
                        file=relative_path,
                        node=function_node,
                        signature=f"def {name}{parameters}",
                    )
                )
        return symbols

    def extract_identifier_references(self, parsed: ParsedSource) -> list[tuple[str, int, str]]:
        captures = self.parser.captures(parsed, self.REFERENCE_QUERY)
        references: list[tuple[str, int, str]] = []
        for node in captures.get("reference", []):
            name = self.node_text(parsed, node)
            line_number = node.start_point.row + 1
            references.append((name, line_number, self.line_text(parsed, line_number)))
        return references


def first_capture(captures: dict[str, list[Any]], name: str):
    values = captures.get(name, [])
    return values[0] if values else None
