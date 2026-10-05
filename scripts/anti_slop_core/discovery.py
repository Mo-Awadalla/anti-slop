"""Read-only Git discovery, candidate extraction, and snapshot creation."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

from .models import DiscoveryInfo


class DiscoveryError(RuntimeError):
    pass


class DirtySourceError(DiscoveryError):
    pass


_COMMAND_LINE = re.compile(r"(?:^|\s)(python(?:3)?(?:\s+-m\s+[^\s]+)?|pytest(?:\s+[^#\n]+)?|npm\s+(?:test|run\s+test)|cargo\s+test|go\s+test|make(?:\s+\w+)?)(?:\s|$)")
_DOC_NAMES = {"readme", "readme.md", "readme.rst", "makefile", "tox.ini", "pyproject.toml", ".travis.yml", "justfile"}


def _git(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=False)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise DiscoveryError(f"git discovery failed: {detail.strip()}") from exc
    return result.stdout.strip()


def _candidate_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = Path(current) / name
            lower = name.lower()
            rel = path.relative_to(root).as_posix().lower()
            if lower in _DOC_NAMES or "/.github/workflows/" in f"/{rel}/" or "/.gitlab-ci" in f"/{rel}/" or (lower.endswith((".yml", ".yaml")) and ("ci" in rel or "workflow" in rel)):
                yield path


def _extract_candidates(root: Path) -> tuple[str, ...]:
    candidates: list[str] = []
    for path in _candidate_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            match = _COMMAND_LINE.search(line)
            if not match:
                continue
            raw = match.group(1).strip()
            try:
                argv = shlex.split(raw, comments=True, posix=True)
            except ValueError:
                continue
            if argv and not any(token in {"|", ";", ">", "<", "&&", "||"} for token in argv):
                candidates.append(" ".join(argv))
    return tuple(dict.fromkeys(candidates))


def discover(repo_path: str | Path) -> DiscoveryInfo:
    path = Path(repo_path)
    if not path.is_absolute():
        raise DiscoveryError("repo_path must be absolute")
    if not path.is_dir():
        raise DiscoveryError("repo_path is not a directory")
    root = Path(_git(path, "rev-parse", "--show-toplevel")).resolve()
    head = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "DETACHED"
    dirty_output = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    return DiscoveryInfo(str(root), head, branch, bool(dirty_output), _extract_candidates(root))


def source_fingerprint(root: str | Path) -> str:
    root_path = Path(root).resolve()
    digest = hashlib.sha256()
    entries: list[Path] = []
    for current, dirs, files in os.walk(root_path, followlinks=False):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            path = Path(current) / name
            if path.is_symlink():
                raise DiscoveryError(f"symlink source is not allowed: {path}")
            entries.append(path)
    for path in sorted(entries):
        rel = path.relative_to(root_path).as_posix().encode()
        data = path.read_bytes()
        digest.update(len(rel).to_bytes(8, "big")); digest.update(rel)
        digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def create_snapshot(info: DiscoveryInfo, snapshot_root: str | Path) -> str:
    if info.dirty:
        raise DirtySourceError("source repository is dirty; execution stopped")
    source = Path(info.git_root).resolve()
    target = Path(snapshot_root).resolve()
    try:
        if os.path.commonpath((str(source), str(target))) == str(source):
            raise DiscoveryError("snapshot_root must not be inside the source repository")
    except ValueError as exc:
        raise DiscoveryError("source and snapshot are on incompatible paths") from exc
    if target.exists():
        raise DiscoveryError("snapshot_root already exists; refusing to overwrite")
    for current, dirs, files in os.walk(source, followlinks=False):
        for name in list(dirs) + list(files):
            if (Path(current) / name).is_symlink():
                raise DiscoveryError("symlinked source content is not allowed")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"), symlinks=True)
    return str(target)


def clean_snapshot(repo: str | Path, destination: Path) -> Path:
    info = discover(repo)
    return Path(create_snapshot(info, destination))
