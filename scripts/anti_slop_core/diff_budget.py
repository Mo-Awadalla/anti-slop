"""Exact-path, text-only diff guards and a reviewable unified patch export."""

from __future__ import annotations

import difflib
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .models import DiffLimits, PatchStep


class DiffGuardError(ValueError):
    pass


@dataclass(frozen=True)
class FileState:
    data: bytes
    mode: int


# These surfaces can change verification, dependency resolution or execution.
# The deterministic runner deliberately leaves them for an explicit reviewed
# workflow, even when a caller includes them in its exact file allowlist.
_PROTECTED_NAMES = {
    '.gitignore', '.gitattributes', '.gitmodules', '.gitlab-ci.yml',
    'package.json', 'package-lock.json', 'npm-shrinkwrap.json', 'yarn.lock',
    'pnpm-lock.yaml', 'pyproject.toml', 'setup.py', 'setup.cfg', 'tox.ini',
    'pytest.ini', 'requirements.txt', 'Pipfile', 'Pipfile.lock', 'poetry.lock',
    'uv.lock', 'Cargo.toml', 'Cargo.lock', 'go.mod', 'go.sum', 'Gemfile',
    'Gemfile.lock', 'composer.json', 'composer.lock', 'Makefile', 'justfile',
    'Dockerfile', 'docker-compose.yml', 'docker-compose.yaml', 'CMakeLists.txt',
    'AGENTS.md', 'CLAUDE.md',
}
_PROTECTED_DIRS = {'.git', '.github', '.gitlab', '.circleci', '.codex', '.agents'}
_CONFIG_SUFFIXES = {'.toml', '.yaml', '.yml', '.ini', '.cfg', '.lock'}


def safe_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or '\\' in value or os.path.isabs(value):
        raise DiffGuardError('change path must be a relative POSIX file path')
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value):
        raise DiffGuardError('change paths must not contain whitespace or control characters')
    if any(part in ('', '.', '..') for part in value.split('/')):
        raise DiffGuardError('change path contains unsafe traversal')
    return value


def protected_path(path: str) -> bool:
    item = Path(path)
    return (any(part in _PROTECTED_DIRS for part in item.parts)
            or item.name in _PROTECTED_NAMES
            or item.suffix.lower() in _CONFIG_SUFFIXES
            or item.name.startswith(('requirements-', '.env')))


def read_tree(root: str | Path) -> dict[str, FileState]:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise DiffGuardError('snapshot must be a regular directory')
    result = {}
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in list(dirs) + list(files):
            item = Path(current) / name
            relative = item.relative_to(root).as_posix()
            if item.is_symlink():
                raise DiffGuardError(f'symlinked content is not allowed: {relative}')
            if name == '.git':
                raise DiffGuardError('Git metadata must not exist in the disposable snapshot')
            if name in files:
                metadata = item.stat()
                if not stat.S_ISREG(metadata.st_mode):
                    raise DiffGuardError(f'nonregular content is not allowed: {relative}')
                result[relative] = FileState(item.read_bytes(), stat.S_IMODE(metadata.st_mode))
    return result


def tree_sha256(tree: Mapping[str, FileState]) -> str:
    digest = hashlib.sha256()
    for path, state in sorted(tree.items()):
        name = path.encode('utf-8')
        digest.update(len(name).to_bytes(8, 'big'))
        digest.update(name)
        digest.update(state.mode.to_bytes(4, 'big'))
        digest.update(len(state.data).to_bytes(8, 'big'))
        digest.update(state.data)
    return digest.hexdigest()


def directory_state(root: str | Path) -> tuple[tuple[str, int], ...]:
    """Include empty directories and permissions in check-mutation detection."""
    root = Path(root)
    values = [('.', stat.S_IMODE(root.stat().st_mode))]
    for current, dirs, _ in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(current) / name
            if path.is_symlink():
                raise DiffGuardError('symlinked directories are unsupported')
            values.append((path.relative_to(root).as_posix(), stat.S_IMODE(path.stat().st_mode)))
    return tuple(sorted(values))


def _text(state: FileState | None, path: str) -> list[str]:
    if state is None:
        return []
    if b'\0' in state.data:
        raise DiffGuardError(f'binary changes are unsupported: {path}')
    try:
        # Git patch lines are separated by LF. str.splitlines would also
        # split valid Unicode separators and lone CR characters, producing
        # an export that does not reproduce the validated bytes.
        parts = state.data.decode('utf-8').split('\n')
        return [part + '\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    except UnicodeDecodeError as exc:
        raise DiffGuardError(f'non-UTF-8 changes are unsupported: {path}') from exc


def analyze_diff(before: Mapping[str, FileState], after: Mapping[str, FileState]) -> dict:
    entries = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        old_lines, new_lines = _text(old, path), _text(new, path)
        added = deleted = 0
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
            if tag != 'equal':
                deleted += i2 - i1
                added += j2 - j1
        entries.append({
            'path': path,
            'operation': 'create' if old is None else 'delete' if new is None else 'modify',
            'before_sha256': hashlib.sha256(old.data).hexdigest() if old else None,
            'after_sha256': hashlib.sha256(new.data).hexdigest() if new else None,
            'before_mode': old.mode if old else None,
            'after_mode': new.mode if new else None,
            'added_lines': added,
            'deleted_lines': deleted,
        })
    added = sum(item['added_lines'] for item in entries)
    deleted = sum(item['deleted_lines'] for item in entries)
    return {'files': len(entries), 'added_lines': added, 'deleted_lines': deleted,
            'changed_lines': added + deleted, 'entries': entries}


def guard_diff(before: Mapping[str, FileState], after: Mapping[str, FileState], *,
               allowed_paths: tuple[str, ...], protected_paths: tuple[str, ...], limits: DiffLimits) -> dict:
    diff = analyze_diff(before, after)
    for entry in diff['entries']:
        path = safe_relative_path(entry['path'])
        if path not in allowed_paths:
            raise DiffGuardError(f'change is outside allowed_paths: {path}')
        if path in protected_paths or protected_path(path):
            raise DiffGuardError(f'protected verification/configuration surface: {path}')
        if entry['before_mode'] is not None and entry['after_mode'] is not None and entry['before_mode'] != entry['after_mode']:
            raise DiffGuardError(f'file permissions must be preserved: {path}')
    if diff['files'] > limits.max_files:
        raise DiffGuardError('diff exceeds max_files')
    if diff['changed_lines'] > limits.max_changed_lines:
        raise DiffGuardError('diff exceeds max_changed_lines')
    return diff


def apply_step(root: str | Path, step: PatchStep, *, allowed_paths: tuple[str, ...],
               protected_paths: tuple[str, ...]) -> None:
    root = Path(root).resolve()
    current = read_tree(root)
    prepared = []
    for change in step.changes:
        path = safe_relative_path(change.path)
        if path not in allowed_paths:
            raise DiffGuardError(f'change is outside allowed_paths: {path}')
        if path in protected_paths or protected_path(path):
            raise DiffGuardError(f'protected verification/configuration surface: {path}')
        target = root / path
        existing = current.get(path)
        actual = hashlib.sha256(existing.data).hexdigest() if existing else None
        if actual != change.before_sha256:
            raise DiffGuardError(f'stale before_sha256 precondition: {path}')
        if existing:
            _text(existing, path)
        if change.content is None:
            if existing is None:
                raise DiffGuardError(f'cannot delete nonexistent file: {path}')
            data = None
        else:
            data = change.content.encode('utf-8')
            _text(FileState(data, existing.mode if existing else 0o644), path)
        if target.exists() and not target.is_file():
            raise DiffGuardError(f'change target is not a regular file: {path}')
        for parent in target.parents:
            if parent == root:
                break
            if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
                raise DiffGuardError(f'unsafe parent directory: {path}')
        prepared.append((target, data, existing.mode if existing else 0o644))
    # Validate all preconditions before the first mutation.
    for target, data, mode in prepared:
        if data is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)


def unified_patch(before: Mapping[str, FileState], after: Mapping[str, FileState]) -> bytes:
    parts = []
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old == new:
            continue
        safe_relative_path(path)
        parts.append(f'diff --git a/{path} b/{path}\n')
        if old is None:
            parts.append(f'new file mode {0o100000 | new.mode:o}\n')
        elif new is None:
            parts.append(f'deleted file mode {0o100000 | old.mode:o}\n')
        old_name, new_name = ('a/' + path if old else '/dev/null'), ('b/' + path if new else '/dev/null')
        for line in difflib.unified_diff(_text(old, path), _text(new, path), fromfile=old_name, tofile=new_name):
            parts.append(line if line.endswith('\n') else line + '\n\\ No newline at end of file\n')
    return ''.join(parts).encode('utf-8')
