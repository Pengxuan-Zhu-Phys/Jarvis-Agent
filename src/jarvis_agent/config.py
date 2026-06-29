from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


CONFIG_NAME = ".jarvis-agent.toml"
DEFAULT_MODEL = "mlx-community/Qwen3-Coder-30B-A3B-Instruct-4bit"
JOSIEFIED_QWEN25_CODER_7B = "mlx-community/Josiefied-Qwen2.5-Coder-7B-Instruct-abliterated-v1-4bit"
AVAILABLE_MODELS = (
    DEFAULT_MODEL,
    JOSIEFIED_QWEN25_CODER_7B,
)


@dataclass(frozen=True)
class ModelConfig:
    backend: str = "mlx"
    model: str = DEFAULT_MODEL
    max_tokens: int = 2048
    temperature: float = 0.2


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    name: str = "hep-package"


@dataclass(frozen=True)
class IndexConfig:
    max_file_bytes: int = 200_000
    include_extensions: tuple[str, ...] = (
        ".py",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".hh",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".md",
        ".rst",
        ".txt",
        "CMakeLists.txt",
        "Makefile",
    )
    ignore_dirs: tuple[str, ...] = (
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".venv",
        "venv",
        "build",
        "dist",
        "node_modules",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
    )


@dataclass(frozen=True)
class AgentConfig:
    project: ProjectConfig
    model: ModelConfig = field(default_factory=ModelConfig)
    index: IndexConfig = field(default_factory=IndexConfig)


def default_config_text(project_root: Path | None = None) -> str:
    root = str((project_root or Path.cwd()).expanduser())
    return f"""[project]
root = "{root}"
name = "hep-package"

[model]
backend = "mlx"
model = "{DEFAULT_MODEL}"
max_tokens = 2048
temperature = 0.2

[index]
max_file_bytes = 200000
include_extensions = [
  ".py",
  ".c",
  ".cc",
  ".cpp",
  ".cxx",
  ".h",
  ".hpp",
  ".hh",
  ".yaml",
  ".yml",
  ".toml",
  ".json",
  ".md",
  ".rst",
  ".txt",
  "CMakeLists.txt",
  "Makefile",
]
"""


def find_config(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        candidate = path / CONFIG_NAME
        if candidate.exists():
            return candidate
    return None


def load_config(path: Path | None = None, project_override: Path | None = None) -> AgentConfig:
    config_path = path or find_config()
    data: dict = {}
    if config_path is not None:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    project_data = data.get("project", {})
    model_data = data.get("model", {})
    index_data = data.get("index", {})

    project_root = project_override or Path(project_data.get("root", Path.cwd()))
    project = ProjectConfig(
        root=project_root.expanduser().resolve(),
        name=str(project_data.get("name", project_root.name or "hep-package")),
    )
    model = ModelConfig(
        backend=str(model_data.get("backend", "mlx")),
        model=str(model_data.get("model", DEFAULT_MODEL)),
        max_tokens=int(model_data.get("max_tokens", 2048)),
        temperature=float(model_data.get("temperature", 0.2)),
    )
    index = IndexConfig(
        max_file_bytes=int(index_data.get("max_file_bytes", 200_000)),
        include_extensions=tuple(index_data.get("include_extensions", IndexConfig().include_extensions)),
        ignore_dirs=tuple(index_data.get("ignore_dirs", IndexConfig().ignore_dirs)),
    )
    return AgentConfig(project=project, model=model, index=index)


def write_default_config(path: Path, project_root: Path | None = None) -> None:
    if path.exists():
        raise FileExistsError(f"Config already exists: {path}")
    path.write_text(default_config_text(project_root), encoding="utf-8")
