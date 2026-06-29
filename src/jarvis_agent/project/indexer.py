from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis_agent.config import IndexConfig


@dataclass(frozen=True)
class FileRecord:
    path: Path
    relative_path: str
    size: int
    kind: str


@dataclass(frozen=True)
class ProjectIndex:
    root: Path
    files: tuple[FileRecord, ...]

    def by_suffix(self, suffix: str) -> tuple[FileRecord, ...]:
        return tuple(record for record in self.files if record.path.name.endswith(suffix))

    def summary(self) -> str:
        counts: dict[str, int] = {}
        for record in self.files:
            counts[record.kind] = counts.get(record.kind, 0) + 1
        parts = ", ".join(f"{kind}: {count}" for kind, count in sorted(counts.items()))
        return f"{len(self.files)} indexed files" + (f" ({parts})" if parts else "")


class ProjectIndexer:
    def __init__(self, config: IndexConfig) -> None:
        self.config = config

    def build(self, root: Path) -> ProjectIndex:
        root = root.expanduser().resolve()
        records: list[FileRecord] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if self._is_ignored(path, root):
                continue
            if not self._is_included(path):
                continue
            size = path.stat().st_size
            if size > self.config.max_file_bytes:
                continue
            records.append(
                FileRecord(
                    path=path,
                    relative_path=path.relative_to(root).as_posix(),
                    size=size,
                    kind=self._kind(path),
                )
            )
        return ProjectIndex(root=root, files=tuple(sorted(records, key=lambda item: item.relative_path)))

    def _is_ignored(self, path: Path, root: Path) -> bool:
        relative_parts = path.relative_to(root).parts
        return any(part in self.config.ignore_dirs for part in relative_parts)

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

