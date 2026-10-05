"""Explicit checkpoint/rollback primitive, not exposed through the CLI."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class Checkpoint:
    def __init__(self, repo_path: str, staging: Path):
        self.repo_path = Path(repo_path).resolve()
        self.staging = staging
        self._rolled_back = False

    @classmethod
    def capture(cls, repo_path: str) -> "Checkpoint":
        repo = Path(repo_path).resolve()
        if not repo.is_dir() or not (repo / ".git").exists():
            raise ValueError("checkpoint requires a Git repository")
        staging = Path(tempfile.mkdtemp(prefix="anti-slop-checkpoint-"))
        for item in repo.iterdir():
            if item.name == ".git":
                continue
            destination = staging / item.name
            if item.is_dir() and not item.is_symlink():
                shutil.copytree(item, destination, symlinks=True)
            else:
                shutil.copy2(item, destination, follow_symlinks=False)
        return cls(str(repo), staging)

    def rollback(self) -> None:
        for item in self.repo_path.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
        for item in self.staging.iterdir():
            destination = self.repo_path / item.name
            if item.is_dir() and not item.is_symlink():
                shutil.copytree(item, destination, symlinks=True)
            else:
                shutil.copy2(item, destination, follow_symlinks=False)
        self._rolled_back = True

    def close(self) -> None:
        shutil.rmtree(self.staging, ignore_errors=True)

    def __enter__(self) -> "Checkpoint":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def create_checkpoint(repo_path: str) -> Checkpoint:
    return Checkpoint.capture(repo_path)
