from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import tomllib


CONFIG_NAME = ".jarvis-agent.toml"
JARVIS_HOME_ENV = "JARVIS_HOME"
AGENT_STATE_NAME = "agent_state.json"
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
    config = apply_local_state(AgentConfig(project=project, model=model, index=index))
    ensure_local_agent_state(config)
    return config


def write_default_config(path: Path, project_root: Path | None = None) -> None:
    if path.exists():
        raise FileExistsError(f"Config already exists: {path}")
    path.write_text(default_config_text(project_root), encoding="utf-8")


def jarvis_home() -> Path:
    configured = os.environ.get(JARVIS_HOME_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".jarvis"


def local_agent_state_path() -> Path:
    return jarvis_home() / AGENT_STATE_NAME


def load_local_state() -> dict:
    path = local_agent_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def apply_local_state(config: AgentConfig) -> AgentConfig:
    state = load_local_state()
    model_data = state.get("model", {})
    if not isinstance(model_data, dict):
        return config

    model = config.model
    try:
        model = replace(
            model,
            backend=str(model_data.get("backend", model.backend)),
            model=str(model_data.get("model", model.model)),
            max_tokens=int(model_data.get("max_tokens", model.max_tokens)),
            temperature=float(model_data.get("temperature", model.temperature)),
        )
    except (TypeError, ValueError):
        return config
    return replace(config, model=model)


def ensure_local_agent_state(config: AgentConfig) -> Path:
    return save_local_model_state(config)


def save_local_model_state(config: AgentConfig) -> Path:
    path = local_agent_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "1.0",
        "model": {
            "backend": config.model.backend,
            "model": config.model.model,
            "max_tokens": config.model.max_tokens,
            "temperature": config.model.temperature,
            "display": model_badge_name(config.model.model),
        },
        "available_models": [
            {
                "backend": config.model.backend,
                "model": model,
                "display": model_badge_name(model),
            }
            for model in AVAILABLE_MODELS
        ],
        "display": {
            "model_badge": f"{model_badge_name(config.model.model)} · {config.model.backend}",
        },
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def model_badge_name(model: str) -> str:
    name = model.rsplit("/", 1)[-1]
    parts = name.replace("_", "-").split("-")
    family = next((part for part in parts if part.startswith("Qwen")), "")
    role = "Coder" if "Coder" in parts else ""
    size = next((part for part in parts if part.endswith("B") and any(character.isdigit() for character in part)), "")
    label = " ".join(part for part in (family, role, size) if part)
    if label:
        return label
    return compact_model_name(model, max_chars=24)


def compact_model_name(model: str, max_chars: int = 42) -> str:
    tail = model.rsplit("/", 1)[-1]
    if len(tail) <= max_chars:
        return tail
    return f"{tail[:max_chars - 1]}…"
