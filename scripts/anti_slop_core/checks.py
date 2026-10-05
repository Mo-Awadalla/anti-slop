"""Tokenized check execution and evidence capture."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time
from typing import Iterable, Optional

from .artifacts import ArtifactStore
from .models import ArtifactRef, AttemptStatus, CheckRecord, CheckSpec, CommandAttempt
from .sandbox import BubblewrapSandbox, SandboxUnavailable
from .process_limits import DEFAULT_LIMITS, OutputLimitExceeded, with_diagnostic


def _safe_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _runner_available(argv: tuple[str, ...], sandbox=None, cwd: str = ".") -> bool:
    executable = argv[0]
    if "/" in executable and not os.path.isabs(executable) and sandbox is not None:
        from pathlib import Path
        base = Path(cwd) if os.path.isabs(cwd) else Path(sandbox.workspace) / cwd
        candidate = base / executable
        return candidate.is_file() and os.access(candidate, os.X_OK)
    if os.path.isabs(executable):
        return os.path.isfile(executable) and os.access(executable, os.X_OK)
    return shutil.which(executable, path="/usr/bin:/bin") is not None


def _artifacts(store: ArtifactStore, check_id: str, number: int, stdout: bytes, stderr: bytes) -> tuple[ArtifactRef, ArtifactRef]:
    prefix = f"checks/{_safe_id(check_id)}/attempt-{number}"
    return store.put_bytes(prefix + ".stdout", stdout, "text/plain"), store.put_bytes(prefix + ".stderr", stderr, "text/plain")


def run_check(spec: CheckSpec, sandbox: BubblewrapSandbox, store: ArtifactStore) -> tuple[CheckRecord, tuple[ArtifactRef, ...]]:
    attempts: list[CommandAttempt] = []
    artifacts: list[ArtifactRef] = []
    count = 2 if spec.rerun else 1
    capture_cap = getattr(sandbox, "limits", DEFAULT_LIMITS).output_bytes
    for number in range(1, count + 1):
        if not _runner_available(spec.argv, sandbox, spec.cwd):
            stdout, stderr, status, code = b"", f"runner unavailable: {spec.argv[0]}\n".encode(), AttemptStatus.UNAVAILABLE, None
            start = time.monotonic()
        else:
            start = time.monotonic()
            try:
                result = sandbox.run(spec.argv, spec.cwd, spec.timeout_seconds)
                stdout = result.stdout or b""
                stderr = result.stderr or b""
                code = result.returncode
                text = stderr.decode("utf-8", "replace").lower()
                if code in (125, 126, 127) and ("bwrap" in text or "execvp" in text or "no such file" in text):
                    status = AttemptStatus.UNAVAILABLE
                else:
                    status = AttemptStatus.PASSED if code == 0 else AttemptStatus.FAILED
                if code < 0:
                    stdout, stderr = with_diagnostic(stdout, stderr, f"check terminated by signal {-code}; not a passing result", capture_cap)
            except OutputLimitExceeded as exc:
                stdout, stderr = exc.stdout, exc.stderr
                code, status = None, AttemptStatus.FAILED
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or b""
                stderr = exc.stderr or b""
                if isinstance(stdout, str): stdout = stdout.encode()
                if isinstance(stderr, str): stderr = stderr.encode()
                if b"check timed out" not in stderr:
                    stdout, stderr = with_diagnostic(stdout, stderr, "check timed out", capture_cap)
                code, status = None, AttemptStatus.FAILED
            except SandboxUnavailable as exc:
                stdout, stderr, code, status = b"", (str(exc) + "\n").encode(), None, AttemptStatus.UNAVAILABLE
            except (OSError, ValueError) as exc:
                stdout, stderr, code, status = b"", (str(exc) + "\n").encode(), None, AttemptStatus.BLOCKED
        duration = (time.monotonic() - start) * 1000
        stdout_ref, stderr_ref = _artifacts(store, spec.id, number, stdout, stderr)
        artifacts.extend((stdout_ref, stderr_ref))
        attempts.append(CommandAttempt(spec.id, spec.argv, spec.cwd, status, code, duration, stdout_ref, stderr_ref, status not in (AttemptStatus.UNAVAILABLE, AttemptStatus.BLOCKED)))
    return CheckRecord(spec.id, _derive_record_status(attempts), tuple(attempts), (), spec.required), tuple(artifacts)


def _derive_record_status(attempts: Iterable[CommandAttempt]):
    from .manifest import derive_check_status
    from .models import CheckStatus
    values = tuple(attempts)
    record = CheckRecord(values[0].check_id if values else "", CheckStatus.PENDING, values)
    return derive_check_status(record)


def unavailable_checks(checks: Iterable[CheckSpec], store: ArtifactStore, reason: str) -> tuple[tuple[CheckRecord, ...], tuple[ArtifactRef, ...]]:
    records = []
    artifacts = []
    for spec in checks:
        stdout_ref, stderr_ref = _artifacts(store, spec.id, 1, b"", (reason + "\n").encode())
        attempt = CommandAttempt(spec.id, spec.argv, spec.cwd, AttemptStatus.UNAVAILABLE, None, 0.0, stdout_ref, stderr_ref, False)
        records.append(CheckRecord(spec.id, _derive_record_status((attempt,)), (attempt,), (), spec.required))
        artifacts.extend((stdout_ref, stderr_ref))
    return tuple(records), tuple(artifacts)


def run_checks(checks: Iterable[CheckSpec], sandbox: BubblewrapSandbox, store: ArtifactStore) -> tuple[tuple[CheckRecord, ...], tuple[ArtifactRef, ...]]:
    records: list[CheckRecord] = []
    artifacts: list[ArtifactRef] = []
    for spec in checks:
        record, refs = run_check(spec, sandbox, store)
        records.append(record)
        artifacts.extend(refs)
    return tuple(records), tuple(artifacts)
