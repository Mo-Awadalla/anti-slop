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


def _safe_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _runner_available(argv: tuple[str, ...]) -> bool:
    executable = argv[0]
    if os.path.isabs(executable):
        return os.path.isfile(executable) and os.access(executable, os.X_OK)
    return shutil.which(executable, path="/usr/local/bin:/usr/bin:/bin") is not None


def _artifacts(store: ArtifactStore, check_id: str, number: int, stdout: bytes, stderr: bytes) -> tuple[ArtifactRef, ArtifactRef]:
    prefix = f"checks/{_safe_id(check_id)}/attempt-{number}"
    return store.put_bytes(prefix + ".stdout", stdout, "text/plain"), store.put_bytes(prefix + ".stderr", stderr, "text/plain")


def run_check(spec: CheckSpec, sandbox: BubblewrapSandbox, store: ArtifactStore) -> tuple[CheckRecord, tuple[ArtifactRef, ...]]:
    attempts: list[CommandAttempt] = []
    artifacts: list[ArtifactRef] = []
    count = 2 if spec.rerun else 1
    for number in range(1, count + 1):
        if not _runner_available(spec.argv):
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
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or b""
                stderr = exc.stderr or b""
                if isinstance(stdout, str): stdout = stdout.encode()
                if isinstance(stderr, str): stderr = stderr.encode()
                stderr += b"\ncheck timed out\n"
                code, status = None, AttemptStatus.FAILED
            except SandboxUnavailable as exc:
                stdout, stderr, code, status = b"", (str(exc) + "\n").encode(), None, AttemptStatus.UNAVAILABLE
        duration = (time.monotonic() - start) * 1000
        stdout_ref, stderr_ref = _artifacts(store, spec.id, number, stdout, stderr)
        artifacts.extend((stdout_ref, stderr_ref))
        attempts.append(CommandAttempt(spec.id, spec.argv, spec.cwd, status, code, duration, stdout_ref, stderr_ref, True))
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
        stdout_ref, stderr_ref = _artifacts(store, spec.id, 1, b"", (reason + "\\n").encode())
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
