"""Read-only Git discovery, candidate extraction, and snapshot creation."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import stat
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


def _git_bytes(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise DiscoveryError(f"git discovery failed: {detail.decode(errors='replace').strip()}") from exc
    return result.stdout


def _git(repo: Path, *args: str) -> str:
    return os.fsdecode(_git_bytes(repo, *args)).strip()


def _tracked_paths(root: Path) -> tuple[str, ...]:
    # NUL separation preserves quoted names, whitespace and newlines. The
    # index is usable only together with the before/after clean-state guards.
    paths = tuple(os.fsdecode(value) for value in _git_bytes(root, "ls-files", "--cached", "-z").split(b"\0") if value)
    for path in paths:
        if any(part in ("", ".", "..", ".git") for part in path.split("/")) or os.path.isabs(path):
            raise DiscoveryError("unsafe tracked path")
    return tuple(sorted(set(paths)))


def _open_tracked(root: Path, relative: str):
    """Open only regular tracked bytes, without following any path symlink."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        file_descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        metadata = os.fstat(file_descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(file_descriptor)
            raise DiscoveryError(f"nonregular tracked content is not allowed: {relative}")
        return os.fdopen(file_descriptor, "rb"), metadata
    except OSError as exc:
        raise DiscoveryError(f"cannot safely read tracked content: {relative}: {exc}") from exc
    finally:
        os.close(descriptor)


def _candidate_files(root: Path) -> Iterable[Path]:
    for relative in _tracked_paths(root):
        path = root / relative
        lower = path.name.lower()
        rel = relative.lower()
        if path.is_file() and not path.is_symlink() and (lower in _DOC_NAMES or "/.github/workflows/" in f"/{rel}/" or "/.gitlab-ci" in f"/{rel}/" or (lower.endswith((".yml", ".yaml")) and ("ci" in rel or "workflow" in rel))):
            yield path


def _extract_candidates(root: Path) -> tuple[str, ...]:
    candidates: list[str] = []
    for path in _candidate_files(root):
        try:
            stream, _ = _open_tracked(root, path.relative_to(root).as_posix())
            with stream:
                text = stream.read().decode("utf-8", errors="replace")
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
    """Identify tracked bytes/modes and Git state, never read ignored secrets."""
    root_path = Path(root).resolve()
    digest = hashlib.sha256()
    digest.update((root_path.stat().st_mode & 0o7777).to_bytes(4, "big"))
    for args in (("rev-parse", "HEAD"), ("rev-parse", "--abbrev-ref", "HEAD"),
                 ("status", "--porcelain=v1", "-z", "--untracked-files=all"),
                 ("ls-files", "--stage", "-z")):
        identity = _git_bytes(root_path, *args)
        digest.update(len(identity).to_bytes(8, "big"))
        digest.update(identity)
    for relative in _tracked_paths(root_path):
        name = os.fsencode(relative)
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        if not (root_path / relative).exists() and not (root_path / relative).is_symlink():
            digest.update(b"MISSING")
            continue
        stream, metadata = _open_tracked(root_path, relative)
        digest.update(stat.S_IMODE(metadata.st_mode).to_bytes(4, "big"))
        digest.update(metadata.st_size.to_bytes(8, "big"))
        with stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
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
    current = discover(source)
    if current.dirty or (current.head, current.branch) != (info.head, info.branch):
        raise DirtySourceError("source revision or clean state changed before snapshot")
    before = source_fingerprint(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    try:
        for relative in _tracked_paths(source):
            stream, metadata = _open_tracked(source, relative)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with stream, destination.open("xb") as output:
                shutil.copyfileobj(stream, output, length=1024 * 1024)
            destination.chmod(stat.S_IMODE(metadata.st_mode))
        after = discover(source)
        if after.dirty or (after.head, after.branch) != (info.head, info.branch) or source_fingerprint(source) != before:
            raise DirtySourceError("source revision, tracked content or clean state changed during snapshot")
    except BaseException:
        # Only our newly created disposable copy is removed, never the source.
        shutil.rmtree(target)
        raise
    return str(target)


def clean_snapshot(repo: str | Path, destination: Path) -> Path:
    info = discover(repo)
    return Path(create_snapshot(info, destination))
