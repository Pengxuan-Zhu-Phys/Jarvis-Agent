from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis_agent.config import AgentConfig
from jarvis_agent.hep import build_explain_file_prompt, review_yaml_file
from jarvis_agent.model import MLXBackend
from jarvis_agent.project import ProjectIndex, ProjectIndexer


@dataclass
class WorkflowEngine:
    config: AgentConfig

    def index_summary(self) -> str:
        index = ProjectIndexer(self.config.index).build(self.config.project.root)
        return self.format_index_summary(index)

    def format_index_summary(self, index: ProjectIndex) -> str:
        if index.stats is None:
            return index.summary()
        stats = index.stats
        return "\n".join(
            [
                "项目索引已完成。",
                "",
                "Summary",
                f"- project: {index.root}",
                f"- scanned files: {stats.scanned_files}",
                f"- updated files: {stats.updated_files}",
                f"- unchanged files: {stats.skipped_files}",
                f"- removed files: {stats.removed_files}",
                f"- symbols: {stats.symbols}",
                f"- references: {stats.references}",
                f"- elapsed: {stats.elapsed_seconds:.2f}s",
                f"- cache: {stats.cache_path}",
            ]
        )

    def explain_file_prompt(self, path: Path) -> str:
        return build_explain_file_prompt(path, self.config.project.root)

    def review_yaml(self, path: Path) -> str:
        return review_yaml_file(path).format()

    def ask_model(self, prompt: str) -> str:
        if self.config.model.backend != "mlx":
            raise ValueError(f"Unsupported model backend: {self.config.model.backend}")
        result = MLXBackend(self.config.model).generate(prompt)
        if result.returncode != 0:
            return f"Model command failed with exit code {result.returncode}.\n{result.stderr}"
        return result.display_text()
