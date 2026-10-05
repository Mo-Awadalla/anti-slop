"""Trusted fixture execution, separate from real sandbox boundary tests.

LocalFixtureSandbox is a test double, never a production fallback. It runs only
commands authored in these tests against disposable fixture repositories. Its
use exercises the orchestration and the test oracle; it proves no isolation.
"""

import hashlib
import os
import subprocess
from pathlib import Path

from anti_slop_core.process_limits import run_bounded


class LocalFixtureSandbox:
    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def run(self, command, cwd=".", timeout=None):
        working = Path(cwd) if Path(cwd).is_absolute() else self.workspace / cwd
        return run_bounded(
            command,
            cwd=working,
            timeout=10 if timeout is None else timeout,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(self.workspace)},
        )


def commit_fixture(root, files):
    root = Path(root)
    root.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "--all"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)


def digest(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def tree_identity(root):
    """Include contents, modes, Git metadata, and any symlink targets."""
    result = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_symlink():
            value = ("symlink", os.readlink(path))
        elif path.is_file():
            value = (path.stat().st_mode, path.read_bytes())
        else:
            continue
        result[path.relative_to(root).as_posix()] = value
    return result
