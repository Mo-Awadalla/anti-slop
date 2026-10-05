"""Linux Bubblewrap command isolation; never falls back unsandboxed."""
from __future__ import annotations
import os, shutil, subprocess
from pathlib import Path
class SandboxUnavailable(RuntimeError): pass
class Sandbox:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()
        if shutil.which("bwrap") is None: raise SandboxUnavailable("bwrap is unavailable")
    def argv(self, command: list[str], cwd: str = ".") -> list[str]:
        if not command or any(not isinstance(x, str) for x in command): raise ValueError("argv must be non-empty strings")
        work = "/workspace/" + cwd.lstrip("/") if cwd != "." else "/workspace"
        return ["bwrap", "--die-with-parent", "--unshare-net", "--clearenv", "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin", "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64", "--ro-bind", "/etc", "/etc", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--bind", str(self.workspace), "/workspace", "--chdir", work, "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "HOME", "/tmp/home", "--", *command]
    def run(self, command: list[str], cwd: str = ".", timeout: float = 300) -> subprocess.CompletedProcess:
        try: return subprocess.run(self.argv(command, cwd), capture_output=True, timeout=timeout, env={"PATH":"/usr/bin:/bin", "HOME":"/tmp/home"})
        except FileNotFoundError as exc: raise SandboxUnavailable(str(exc)) from exc


BubblewrapSandbox = Sandbox
