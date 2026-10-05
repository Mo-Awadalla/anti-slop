"""Linux Bubblewrap isolation with a finite timeout and no host fallback."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .process_limits import DEFAULT_LIMITS, ProcessLimits, run_bounded


class SandboxUnavailable(RuntimeError):
    pass


class Sandbox:
    def __init__(self, workspace: str | Path, limits: ProcessLimits = DEFAULT_LIMITS):
        self.workspace = Path(workspace).resolve()
        self.limits = limits
        if sys.platform != "linux":
            raise SandboxUnavailable("Bubblewrap execution requires Linux; use the Docker launcher on this host")
        if not self.workspace.is_dir():
            raise ValueError("sandbox workspace must be a directory")
        if shutil.which("bwrap") is None:
            raise SandboxUnavailable("bwrap is unavailable")

    def argv(self, command: list[str], cwd: str = ".", timeout: float | None = None) -> list[str]:
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
            "bwrap", "--die-with-parent", "--new-session", "--unshare-user", "--unshare-net",
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
        resource_script = Path(__file__).with_name("resource_exec.py")
        args.extend(("--ro-bind", str(resource_script), "/anti-slop-resources.py"))
        timeout = self.limits.timeout_seconds if timeout is None else timeout
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        resource_command = [
            "/usr/bin/python3", "-B", "/anti-slop-resources.py",
            str(self.limits.address_space_bytes), str(self.limits.file_size_bytes),
            str(self.limits.processes), str(self.limits.open_files),
            str(max(1, math.ceil(timeout))), *command,
        ]
        args.extend((
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--dir", "/tmp/home", "--bind", str(self.workspace), "/workspace",
            "--chdir", work, "--setenv", "PATH", "/usr/bin:/bin",
            "--setenv", "HOME", "/tmp/home", "--setenv", "LC_ALL", "C.UTF-8",
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--", *resource_command,
        ))
        return args

    def run(self, command: list[str], cwd: str = ".", timeout: float | None = None) -> subprocess.CompletedProcess:
        try:
            result = run_bounded(
                self.argv(command, cwd, timeout), limits=self.limits, timeout=timeout,
                env={"PATH": "/usr/bin:/bin", "HOME": "/tmp/home"},
            )
        except FileNotFoundError as exc:
            raise SandboxUnavailable(str(exc)) from exc
        stderr = (result.stderr or b"").decode("utf-8", "replace")
        if result.returncode and stderr.lstrip().startswith("bwrap:"):
            raise SandboxUnavailable(stderr.strip())
        return result


BubblewrapSandbox = Sandbox
