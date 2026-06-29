from __future__ import annotations

from typing import Any

from jarvis_agent.project.extractors.base import BaseTreeSitterExtractor
from jarvis_agent.project.parser import ParsedSource


class CppTreeSitterExtractor(BaseTreeSitterExtractor):
    language = "cpp"

    SYMBOL_QUERY = """
    (class_specifier
      name: (type_identifier) @name) @definition.class

    (struct_specifier
      name: (type_identifier) @name) @definition.struct

    (namespace_definition
      name: (namespace_identifier) @name) @definition.namespace

    (function_definition
      declarator: (function_declarator) @declarator) @definition.function
    """

    REFERENCE_QUERY = """
    [
      (identifier)
      (type_identifier)
      (namespace_identifier)
    ] @reference
    """

    def extract_symbols(self, parsed: ParsedSource, relative_path: str) -> list[dict[str, Any]]:
        symbols: list[dict[str, Any]] = []
        for _, captures in self.parser.matches(parsed, self.SYMBOL_QUERY):
            if class_node := first_capture(captures, "definition.class"):
                name_node = first_capture(captures, "name")
                if name_node is not None:
                    name = self.node_text(parsed, name_node)
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
            if struct_node := first_capture(captures, "definition.struct"):
                name_node = first_capture(captures, "name")
                if name_node is not None:
                    name = self.node_text(parsed, name_node)
                    symbols.append(
                        self.make_symbol(
                            name=name,
                            kind="struct",
                            file=relative_path,
                            node=struct_node,
                            signature=f"struct {name}",
                        )
                    )
                continue
            if namespace_node := first_capture(captures, "definition.namespace"):
                name_node = first_capture(captures, "name")
                if name_node is not None:
                    name = self.node_text(parsed, name_node)
                    symbols.append(
                        self.make_symbol(
                            name=name,
                            kind="namespace",
                            file=relative_path,
                            node=namespace_node,
                            signature=f"namespace {name}",
                        )
                    )
                continue
            if function_node := first_capture(captures, "definition.function"):
                declarator = first_capture(captures, "declarator")
                if declarator is None:
                    continue
                name = self.function_name(parsed, declarator)
                if not name:
                    continue
                symbols.append(
                    self.make_symbol(
                        name=name,
                        kind="function",
                        file=relative_path,
                        node=function_node,
                        signature=self.node_text(parsed, declarator),
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

    def function_name(self, parsed: ParsedSource, declarator) -> str:
        leaf = find_function_name_node(declarator)
        return self.node_text(parsed, leaf) if leaf is not None else ""


def find_function_name_node(node):
    if node.type == "qualified_identifier":
        identifiers = [child for child in node.children if child.type == "identifier"]
        if identifiers:
            return identifiers[-1]
    if node.type == "identifier":
        return node
    for child in node.children:
        found = find_function_name_node(child)
        if found is not None:
            return found
    return None


def first_capture(captures: dict[str, list[Any]], name: str):
    values = captures.get(name, [])
    return values[0] if values else None
