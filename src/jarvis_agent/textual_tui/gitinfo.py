from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class GitInfo:
    branch: str = ""
    is_worktree: bool = False
    main_worktree: Path | None = None


def get_git_info(project_root: Path) -> GitInfo:
    branch = _run_git(project_root, "branch", "--show-current")
    if not branch:
        branch = _run_git(project_root, "rev-parse", "--short", "HEAD")

    git_dir = _run_git(project_root, "rev-parse", "--git-dir")
    common_dir = _run_git(project_root, "rev-parse", "--git-common-dir")
    is_worktree = False
    if git_dir and common_dir:
        git_dir_path = _resolve_git_path(project_root, git_dir)
        common_dir_path = _resolve_git_path(project_root, common_dir)
        is_worktree = git_dir_path != common_dir_path

    main_worktree = _main_worktree_path(project_root) if is_worktree else None
    return GitInfo(branch=branch, is_worktree=is_worktree, main_worktree=main_worktree)


def _run_git(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _resolve_git_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _main_worktree_path(project_root: Path) -> Path | None:
    output = _run_git(project_root, "worktree", "list", "--porcelain")
    if not output:
        return None
    for block in output.split("\n\n"):
        first_line = block.splitlines()[0] if block.splitlines() else ""
        if not first_line.startswith("worktree "):
            continue
        candidate = Path(first_line.removeprefix("worktree ")).expanduser().resolve()
        if candidate != project_root.resolve():
            return candidate
    return None


