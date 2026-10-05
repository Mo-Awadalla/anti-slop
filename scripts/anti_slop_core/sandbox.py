"""Linux Bubblewrap isolation with a finite timeout and no host fallback."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    pass


class Sandbox:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ValueError("sandbox workspace must be a directory")
        if shutil.which("bwrap") is None:
            raise SandboxUnavailable("bwrap is unavailable")

    def argv(self, command: list[str], cwd: str = ".") -> list[str]:
        if not command or any(not isinstance(x, str) or not x for x in command):
            raise ValueError("argv must be non-empty strings")
        candidate = Path(cwd) if os.path.isabs(cwd) else self.workspace / cwd
        try:
            relative = candidate.resolve().relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("check cwd escapes sandbox workspace") from exc
        if not candidate.is_dir():
            raise ValueError("check cwd must be an existing directory")
        work = "/workspace" if relative == Path(".") else "/workspace/" + relative.as_posix()
        args = [
            "bwrap", "--die-with-parent", "--new-session", "--unshare-net",
            "--unshare-pid", "--unshare-ipc", "--unshare-uts", "--cap-drop", "ALL",
            "--clearenv",
        ]
        for directory in ("/usr", "/bin", "/lib", "/lib64"):
            if Path(directory).exists():
                args.extend(("--ro-bind", directory, directory))
        args.extend(("--tmpfs", "/etc"))
        for system_path in ("/etc/ld.so.cache", "/etc/ssl/certs"):
            if Path(system_path).exists():
                args.extend(("--ro-bind", system_path, system_path))
        args.extend((
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--dir", "/tmp/home", "--bind", str(self.workspace), "/workspace",
            "--chdir", work, "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "HOME", "/tmp/home", "--setenv", "LC_ALL", "C.UTF-8",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *command,
        ))
        return args

    def run(self, command: list[str], cwd: str = ".", timeout: float | None = 300) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                self.argv(command, cwd), capture_output=True,
                timeout=300 if timeout is None else timeout,
                env={"PATH": "/usr/bin:/bin", "HOME": "/tmp/home"},
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable(str(exc)) from exc
        stderr = (result.stderr or b"").decode("utf-8", "replace")
        if result.returncode and stderr.lstrip().startswith("bwrap:"):
            raise SandboxUnavailable(stderr.strip())
        return result


BubblewrapSandbox = Sandbox
