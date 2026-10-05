"""Filesystem checkpoints; the runner uses only disposable, Git-free copies."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path


def _copy_contents(source: Path, destination: Path) -> None:
    for item in source.iterdir():
        if item.name == '.git':
            continue
        target = destination / item.name
        if item.is_dir() and not item.is_symlink():
            shutil.copytree(item, target, symlinks=True)
        else:
            shutil.copy2(item, target, follow_symlinks=False)

def _contents_identity(root: Path) -> tuple:
    entries = []
    for current, dirs, files in os.walk(root, followlinks=False):
        if Path(current) == root:
            dirs[:] = [name for name in dirs if name != '.git']
            files = [name for name in files if name != '.git']
        for name in dirs + files:
            item = Path(current) / name
            metadata = item.lstat()
            if item.is_symlink():
                content = os.readlink(item)
            elif stat.S_ISREG(metadata.st_mode):
                digest = hashlib.sha256()
                with item.open('rb') as stream:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                content = digest.hexdigest()
            elif item.is_dir():
                content = None
            else:
                raise ValueError(f'nonregular recovery content: {item}')
            entries.append((item.relative_to(root).as_posix(), metadata.st_mode, content))
    return tuple(sorted(entries))


class CheckpointRecoveryError(RuntimeError):
    def __init__(self, staging: Path, reason: str):
        self.recovery_path = str(staging)
        self.reason = reason
        super().__init__(f'checkpoint recovery retained at {staging}: {reason}')



class Checkpoint:
    def __init__(self, repo_path: str, staging: Path, *, preserve_git: bool = True):
        self.repo_path = Path(repo_path).resolve()
        self.staging = staging
        self._rolled_back = False
        self._closed = False
        self._preserve_git = preserve_git
        self._recovery_reason = None
        self._root_mode = stat.S_IMODE(self.repo_path.stat().st_mode)

    @classmethod
    def capture(cls, repo_path: str) -> 'Checkpoint':
        """Compatibility primitive for an explicitly selected Git checkout."""
        repo = Path(repo_path).resolve()
        if not repo.is_dir() or not (repo / '.git').exists():
            raise ValueError('checkpoint requires a Git repository')
        return cls._capture(repo)

    @classmethod
    def capture_snapshot(cls, snapshot_root: str | Path) -> 'Checkpoint':
        """Capture an isolated directory without Git metadata; never a checkout."""
        original = Path(snapshot_root)
        if original.is_symlink() or not original.is_dir():
            raise ValueError('snapshot checkpoint requires a regular directory')
        snapshot = original.resolve()
        if (snapshot / '.git').exists():
            raise ValueError('snapshot checkpoint refuses Git checkouts')
        for current, dirs, files in os.walk(snapshot, followlinks=False):
            for name in list(dirs) + list(files):
                path = Path(current) / name
                if path.is_symlink() or not (path.is_dir() or stat.S_ISREG(path.stat().st_mode)):
                    raise ValueError('snapshot checkpoint refuses symlinks and nonregular files')
        return cls._capture(snapshot, preserve_git=False)

    @classmethod
    def _capture(cls, repo: Path, *, preserve_git: bool = True) -> 'Checkpoint':
        staging = Path(tempfile.mkdtemp(prefix='anti-slop-checkpoint-'))
        try:
            _copy_contents(repo, staging)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return cls(str(repo), staging, preserve_git=preserve_git)

    def rollback(self) -> None:
        if self._closed:
            raise ValueError('checkpoint is closed')
        try:
            expected = _contents_identity(self.staging)
            self.repo_path.chmod(self._root_mode)
            for item in self.repo_path.iterdir():
                if item.name == '.git' and self._preserve_git:
                    continue
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            _copy_contents(self.staging, self.repo_path)
            if _contents_identity(self.repo_path) != expected or stat.S_IMODE(self.repo_path.stat().st_mode) != self._root_mode:
                raise ValueError('restored content or modes disagree with recovery checkpoint')
        except BaseException as exc:
            self._recovery_reason = str(exc)
            raise CheckpointRecoveryError(self.staging, str(exc)) from exc
        self._rolled_back = True
        self._recovery_reason = None

    def retain_recovery(self, reason: str) -> None:
        """Keep staging when a caller cannot verify restoration."""
        self._recovery_reason = reason
        raise CheckpointRecoveryError(self.staging, reason)

    def close(self) -> None:
        if self._closed or self._recovery_reason is not None:
            return
        try:
            shutil.rmtree(self.staging)
        except OSError as exc:
            self.retain_recovery(f'cannot remove recovery staging safely: {exc}')
        self._closed = True

    def __enter__(self) -> 'Checkpoint':
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None and not self._rolled_back:
            self._recovery_reason = self._recovery_reason or str(exc)
            if not isinstance(exc, CheckpointRecoveryError):
                raise CheckpointRecoveryError(self.staging, self._recovery_reason) from exc
        self.close()


def create_checkpoint(repo_path: str) -> Checkpoint:
    return Checkpoint.capture(repo_path)
