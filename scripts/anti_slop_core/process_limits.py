"""Bounded subprocess evidence and immutable per-check resource policy."""

from __future__ import annotations

import math
import os
import selectors
import signal
import subprocess
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessLimits:
    output_bytes: int = 1024 * 1024
    address_space_bytes: int = 1024 * 1024 * 1024
    file_size_bytes: int = 64 * 1024 * 1024
    processes: int = 128
    open_files: int = 256
    timeout_seconds: float = 300

    def __post_init__(self):
        for value in (self.output_bytes, self.address_space_bytes, self.file_size_bytes,
                      self.processes, self.open_files):
            if type(value) is not int or value <= 0:
                raise ValueError("resource limits must be positive integers")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout must be finite and positive")


DEFAULT_LIMITS = ProcessLimits()
READ_CHUNK_BYTES = 64 * 1024


class OutputLimitExceeded(subprocess.SubprocessError):
    def __init__(self, command, stdout: bytes, stderr: bytes, limit: int):
        super().__init__(f"check exceeded aggregate stdout/stderr limit ({limit} bytes)")
        self.cmd = command
        self.stdout = stdout
        self.stderr = stderr
        self.limit = limit


def with_diagnostic(stdout: bytes, stderr: bytes, message: str, cap: int = DEFAULT_LIMITS.output_bytes):
    """Reserve diagnostic space without ever enlarging aggregate evidence past cap."""
    marker = ("\n" + message + "\n").encode("utf-8")[:cap]
    available = cap - len(marker)
    stdout = stdout[:available]
    stderr = stderr[:available - len(stdout)] + marker
    return stdout, stderr


def _kill_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_bounded(command, *, timeout=None, limits: ProcessLimits = DEFAULT_LIMITS,
                cwd=None, env=None) -> subprocess.CompletedProcess:
    """Capture both pipes under one cap; wall time includes inherited pipe handles.

    The new process group lets timeout/output termination kill descendants too.
    Bubblewrap additionally owns a PID namespace: killing its monitor tears down
    descendants that create new sessions inside that namespace.
    """
    timeout = limits.timeout_seconds if timeout is None else timeout
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    captures = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    try:
        with selectors.DefaultSelector() as selector:
            for name, pipe in (("stdout", process.stdout), ("stderr", process.stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or process.poll() is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _kill_group(process)
                    stdout, stderr = with_diagnostic(bytes(captures["stdout"]), bytes(captures["stderr"]),
                                                     "check timed out", limits.output_bytes)
                    raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
                for key, _ in selector.select(min(remaining, 0.05)):
                    chunk = os.read(key.fileobj.fileno(), READ_CHUNK_BYTES)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = limits.output_bytes - total
                    captures[key.data].extend(chunk[:available])
                    total += min(len(chunk), available)
                    if len(chunk) > available:
                        _kill_group(process)
                        stdout, stderr = with_diagnostic(bytes(captures["stdout"]), bytes(captures["stderr"]),
                                                         "check exceeded aggregate stdout/stderr limit", limits.output_bytes)
                        raise OutputLimitExceeded(command, stdout, stderr, limits.output_bytes)
        return subprocess.CompletedProcess(command, process.wait(), bytes(captures["stdout"]), bytes(captures["stderr"]))
    finally:
        # Closing handles, rather than communicate(), cannot wait on an escaped
        # descendant retaining a pipe. Always kill the group before cleanup.
        _kill_group(process)
        process.stdout.close()
        process.stderr.close()
        process.wait(timeout=2)
