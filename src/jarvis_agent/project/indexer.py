from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from jarvis_agent.config import IndexConfig
from jarvis_agent.project.extractor import SymbolExtractor


INDEX_VERSION = "1.0"
INDEX_RELATIVE_PATH = Path(".jarvis") / "index" / "codebase_index.json"


@dataclass(frozen=True)
class FileRecord:
    path: Path
    relative_path: str
    size: int
    kind: str


@dataclass(frozen=True)
class FileScanRecord:
    path: Path
    relative_path: str
    hash: str
    language: str
    mtime: float
    size: int

    def to_file_record(self) -> FileRecord:
        return FileRecord(path=self.path, relative_path=self.relative_path, size=self.size, kind=self.language)

    def to_json(self) -> dict[str, Any]:
        return {
            "hash": self.hash,
            "language": self.language,
            "mtime": self.mtime,
            "size": self.size,
        }


@dataclass(frozen=True)
class IndexStats:
    scanned_files: int = 0
    updated_files: int = 0
    skipped_files: int = 0
    removed_files: int = 0
    symbols: int = 0
    references: int = 0
    cache_path: Path | None = None
    elapsed_seconds: float = 0.0

    def format(self) -> str:
        return (
            f"{self.scanned_files} scanned files, "
            f"{self.updated_files} updated, "
            f"{self.skipped_files} unchanged, "
            f"{self.removed_files} removed, "
            f"{self.symbols} symbols, "
            f"{self.references} references, "
            f"{self.elapsed_seconds:.2f}s"
            + (f"\nCache: {self.cache_path}" if self.cache_path is not None else "")
        )


@dataclass
class CodebaseIndex:
    project_root: str
    version: str = INDEX_VERSION
    last_indexed: str = ""
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    symbols: dict[str, dict[str, Any]] = field(default_factory=dict)
    references: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    @classmethod
    def empty(cls, project_root: Path) -> CodebaseIndex:
        return cls(project_root=str(project_root))

    @classmethod
    def load(cls, path: Path, project_root: Path) -> CodebaseIndex:
        if not path.exists():
            return cls.empty(project_root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return cls.empty(project_root)
        return cls(
            version=str(data.get("version", INDEX_VERSION)),
            project_root=str(data.get("project_root", project_root)),
            last_indexed=str(data.get("last_indexed", "")),
            files=dict(data.get("files", {})),
            symbols=dict(data.get("symbols", {})),
            references=dict(data.get("references", {})),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.version,
            "project_root": self.project_root,
            "last_indexed": self.last_indexed,
            "files": dict(sorted(self.files.items())),
            "symbols": dict(sorted(self.symbols.items())),
            "references": dict(sorted(self.references.items())),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def remove_file(self, relative_path: str) -> None:
        self.files.pop(relative_path, None)
        self.symbols = {
            key: value for key, value in self.symbols.items() if value.get("file") != relative_path
        }
        self.references = {
            name: [reference for reference in references if reference.get("file") != relative_path]
            for name, references in self.references.items()
        }
        self.references = {name: refs for name, refs in self.references.items() if refs}

    def replace_file_symbols(self, relative_path: str, symbols: list[dict[str, Any]]) -> None:
        self.symbols = {
            key: value for key, value in self.symbols.items() if value.get("file") != relative_path
        }
        for symbol in symbols:
            self.symbols[self._symbol_key(symbol)] = symbol

    def find_definition(self, symbol_name: str) -> dict[str, Any] | None:
        if symbol_name in self.symbols:
            return self.symbols[symbol_name]
        return next((symbol for symbol in self.symbols.values() if symbol.get("name") == symbol_name), None)

    def find_references(self, symbol_name: str) -> list[dict[str, Any]]:
        return list(self.references.get(symbol_name, []))

    def get_file_symbols(self, file_path: str) -> list[dict[str, Any]]:
        normalized = Path(file_path).as_posix()
        return [symbol for symbol in self.symbols.values() if symbol.get("file") == normalized]

    def search_symbols(self, keyword: str) -> list[dict[str, Any]]:
        lowered = keyword.lower()
        return [
            symbol
            for symbol in self.symbols.values()
            if lowered in str(symbol.get("name", "")).lower()
            or lowered in str(symbol.get("signature", "")).lower()
        ]

    def get_index_stats(self) -> dict[str, int]:
        return {
            "files": len(self.files),
            "symbols": len(self.symbols),
            "references": sum(len(references) for references in self.references.values()),
        }

    def _symbol_key(self, symbol: dict[str, Any]) -> str:
        name = str(symbol.get("name", ""))
        if name and name not in self.symbols:
            return name
        file_path = str(symbol.get("file", "unknown"))
        line = str(symbol.get("start_line", "0"))
        return f"{name}@{file_path}:{line}" if name else f"{file_path}:{line}"


@dataclass(frozen=True)
class ProjectIndex:
    root: Path
    files: tuple[FileRecord, ...]
    codebase: CodebaseIndex | None = None
    stats: IndexStats | None = None

    def by_suffix(self, suffix: str) -> tuple[FileRecord, ...]:
        return tuple(record for record in self.files if record.path.name.endswith(suffix))

    def summary(self) -> str:
        if self.stats is not None:
            return self.stats.format()
        counts: dict[str, int] = {}
        for record in self.files:
            counts[record.kind] = counts.get(record.kind, 0) + 1
        parts = ", ".join(f"{kind}: {count}" for kind, count in sorted(counts.items()))
        return f"{len(self.files)} indexed files" + (f" ({parts})" if parts else "")


class FileScanner:
    def __init__(self, config: IndexConfig) -> None:
        self.config = config

    def scan(self, root: Path) -> list[FileScanRecord]:
        root = root.expanduser().resolve()
        records: list[FileScanRecord] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if self._is_ignored(path, root):
                continue
            if not self._is_included(path):
                continue
            stat = path.stat()
            if stat.st_size > self.config.max_file_bytes:
                continue
            records.append(
                FileScanRecord(
                    path=path,
                    relative_path=path.relative_to(root).as_posix(),
                    hash=sha256_file(path),
                    language=self._kind(path),
                    mtime=stat.st_mtime,
                    size=stat.st_size,
                )
            )
        return sorted(records, key=lambda item: item.relative_path)

    def _is_ignored(self, path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        ignored = set(self.config.ignore_dirs) | {".jarvis"}
        return any(part in ignored for part in relative_parts)

    def _is_included(self, path: Path) -> bool:
        name = path.name
        suffix = path.suffix
        return name in self.config.include_extensions or suffix in self.config.include_extensions

    def _kind(self, path: Path) -> str:
        name = path.name
        suffix = path.suffix.lower()
        if name in {"CMakeLists.txt", "Makefile"} or suffix in {".cmake"}:
            return "build"
        if suffix in {".yaml", ".yml", ".toml", ".json"}:
            return "config"
        if suffix in {".md", ".rst", ".txt"}:
            return "docs"
        if suffix in {".py"}:
            return "python"
        if suffix in {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh"}:
            return "cpp"
        return "other"


class ProjectIndexer:
    def __init__(self, config: IndexConfig) -> None:
        self.config = config
        self.scanner = FileScanner(config)
        self.extractor = SymbolExtractor()

    def build(self, root: Path) -> ProjectIndex:
        started_at = perf_counter()
        root = root.expanduser().resolve()
        cache_path = root / INDEX_RELATIVE_PATH
        codebase = CodebaseIndex.load(cache_path, root)
        codebase.project_root = str(root)
        codebase.version = INDEX_VERSION

        scanned = self.scanner.scan(root)
        scanned_by_path = {record.relative_path: record for record in scanned}

        old_paths = set(codebase.files)
        new_paths = set(scanned_by_path)
        removed_paths = old_paths - new_paths
        for relative_path in removed_paths:
            codebase.remove_file(relative_path)

        updated_files = 0
        skipped_files = 0
        for relative_path, record in scanned_by_path.items():
            cached = codebase.files.get(relative_path, {})
            if cached.get("hash") == record.hash:
                skipped_files += 1
                continue
            updated_files += 1
            codebase.files[relative_path] = record.to_json()
            codebase.replace_file_symbols(
                relative_path,
                self.extractor.extract(record.path, relative_path, record.language),
            )

        codebase.references = build_references(root, scanned, codebase.symbols, self.extractor)
        codebase.last_indexed = datetime.now().isoformat(timespec="seconds")
        codebase.save(cache_path)

        stats = IndexStats(
            scanned_files=len(scanned),
            updated_files=updated_files,
            skipped_files=skipped_files,
            removed_files=len(removed_paths),
            symbols=len(codebase.symbols),
            references=sum(len(references) for references in codebase.references.values()),
            cache_path=cache_path,
            elapsed_seconds=perf_counter() - started_at,
        )
        files = tuple(record.to_file_record() for record in scanned)
        return ProjectIndex(root=root, files=files, codebase=codebase, stats=stats)


def build_references(
    root: Path,
    files: list[FileScanRecord],
    symbols: dict[str, dict[str, Any]],
    extractor: SymbolExtractor,
) -> dict[str, list[dict[str, Any]]]:
    symbol_names = sorted({str(symbol.get("name", "")) for symbol in symbols.values() if symbol.get("name")})
    if not symbol_names:
        return {}
    symbol_set = set(symbol_names)
    references: dict[str, list[dict[str, Any]]] = {name: [] for name in symbol_names}
    definitions = {
        (str(symbol.get("name")), str(symbol.get("file")), int(symbol.get("start_line", 0)))
        for symbol in symbols.values()
    }
    for record in files:
        if record.language not in {"python", "cpp"}:
            continue
        parsed = extractor.parse(root / record.relative_path, record.language)
        if parsed is None:
            continue
        for name, line_number, context in extractor.extract_identifier_references(parsed):
            if name not in symbol_set:
                continue
            if (name, record.relative_path, line_number) in definitions:
                continue
            references[name].append(
                {
                    "file": record.relative_path,
                    "line": line_number,
                    "context": context,
                }
            )
    return {name: values for name, values in references.items() if values}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
