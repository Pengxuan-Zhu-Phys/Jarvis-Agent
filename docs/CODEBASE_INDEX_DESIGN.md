# Codebase Index Design

Jarvis-Agent uses a JSON + in-memory codebase index for `/index`. The goal is to keep indexing deterministic, inspectable, and simple enough to evolve before introducing heavier storage or tool-calling infrastructure.

## Storage

Each indexed project owns its cache under the project root:

```text
<project-root>/.jarvis/index/codebase_index.json
```

The cache is intentionally a single JSON file. It is easy to inspect, delete, diff, and regenerate.

## JSON Schema

```json
{
  "version": "1.0",
  "project_root": "/path/to/project",
  "last_indexed": "2026-06-29T13:40:00",
  "files": {
    "src/worker.py": {
      "hash": "a1b2c3d4...",
      "language": "python",
      "mtime": 1719660000,
      "size": 12480
    }
  },
  "symbols": {
    "initialize_worker": {
      "kind": "function",
      "name": "initialize_worker",
      "file": "src/worker.py",
      "start_line": 45,
      "end_line": 78,
      "signature": "def initialize_worker(cfg)"
    }
  },
  "references": {
    "initialize_worker": [
      {
        "file": "src/factory.py",
        "line": 102,
        "context": "initialize_worker(config)"
      }
    ]
  }
}
```

`files` records scanned file metadata and a content hash for incremental decisions.

`symbols` records definitions. The symbol name is the preferred key. If a project contains duplicate symbol names, Jarvis-Agent may store collision-safe keys such as `name@path:line`, while keeping the original name in the `name` field.

`references` records simple textual references by symbol name. The current implementation is conservative and is meant to support package navigation and prompt construction, not compiler-accurate cross-reference analysis.

## In-Memory Model

`CodebaseIndex` loads the JSON file into dictionaries:

```python
files: dict[str, dict]
symbols: dict[str, dict]
references: dict[str, list[dict]]
last_indexed: str
```

Queries operate directly on these dictionaries:

- `find_definition(symbol_name)`
- `find_references(symbol_name)`
- `get_file_symbols(file_path)`
- `search_symbols(keyword)`
- `get_index_stats()`

## `/index` Flow

1. Load existing `codebase_index.json` if present.
2. Walk the project using `FileScanner`.
3. Filter ignored directories and unsupported file types.
4. Hash each candidate file.
5. Compare hashes against the cached index.
6. Parse only new or changed files.
7. Remove deleted files from `files`, `symbols`, and `references`.
8. Rebuild references from the indexed source files.
9. Write the updated in-memory index back to JSON.
10. Return a compact summary: scanned, updated, removed, skipped, symbols, references.

## Components

| Component | Responsibility | Tree-sitter |
| --- | --- | --- |
| `FileScanner` | Walk project, filter files, compute hashes | No |
| `TreeSitterParser` | Unified parser manager for Python/C++ grammars | Yes |
| `SymbolExtractor` | Dispatch to language-specific Tree-sitter extractors | Yes |
| `CodebaseIndex` | In-memory index plus JSON load/save/query | No |
| `ProjectIndexer` | Coordinate `/index` workflow | No |

## Parser Strategy

The indexer requires Tree-sitter for source parsing. It uses:

- `tree-sitter-python` for Python classes, functions, and identifier references.
- `tree-sitter-cpp` for C/C++ classes, structs, namespaces, function definitions, and identifier references.
- Language-specific extractors under `jarvis_agent.project.extractors`.

The `SymbolExtractor` boundary is deliberately narrow so individual language extractors can improve without changing the cache schema or command behavior.

## Tradeoffs

Benefits:

- No database dependency.
- Inspectable cache file.
- Fast in-memory queries.
- Incremental parsing by hash.
- Simple enough for the prompt-based phase.

Limitations:

- Large projects may produce a large JSON file.
- Reference detection is textual, not compiler-accurate.
- Complex C++ semantic resolution may still require clang-based analysis later.
