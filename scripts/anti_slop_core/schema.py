"""Strict standard-library JSON validation for all public contracts."""

from __future__ import annotations

import json
import math
import os
import re
from collections.abc import Mapping
from enum import Enum
from typing import Any, Iterable, Optional, Set, Type, TypeVar

from .models import (
    ArtifactRef, AttemptStatus, CheckRecord, CheckSpec, CheckStatus,
    CommandAttempt, DiscoveryInfo, Finding, FindingSeverity, ManifestStatus,
    DiffLimits, PatchChange, PatchStep, RunManifest, RunMode, RunSpec,
)


class SchemaError(ValueError):
    """Raised when a JSON value violates a public anti-slop contract."""


T = TypeVar("T")
_SHELL_META = re.compile(r"[|;&<>`\n\r]|\$\(|\$\{")
_SHELL_LAUNCHERS = {"sh", "bash", "dash", "zsh", "fish", "ksh", "csh", "tcsh", "cmd", "powershell", "pwsh"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _json_constant(value: str) -> Any:
    raise SchemaError(f"invalid JSON constant: {value}")


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(k, str) for k in value):
        raise SchemaError(f"{path} must be an object with string keys")
    return value


def _decode(value: Any, path: str) -> Any:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value, parse_constant=_json_constant, object_pairs_hook=_json_object)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SchemaError(f"{path} is not valid JSON: {exc}") from exc
    return value


def _keys(obj: Mapping[str, Any], allowed: Set[str], path: str) -> None:
    unknown = set(obj) - allowed
    if unknown:
        raise SchemaError(f"{path} contains unknown key(s): {', '.join(sorted(unknown))}")


def _required(obj: Mapping[str, Any], names: Iterable[str], path: str) -> None:
    missing = [name for name in names if name not in obj]
    if missing:
        raise SchemaError(f"{path} is missing required key(s): {', '.join(missing)}")


def _string(value: Any, path: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise SchemaError(f"{path} must be a non-empty string")
    return value


def _bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SchemaError(f"{path} must be a boolean")
    return value


def _number(value: Any, path: str, *, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise SchemaError(f"{path} must be a finite number")
    result = float(value)
    if minimum is not None and result < minimum:
        raise SchemaError(f"{path} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise SchemaError(f"{path} must be <= {maximum}")
    return result


def _integer(value: Any, path: str, *, minimum: Optional[int] = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchemaError(f"{path} must be an integer")
    if minimum is not None and value < minimum:
        raise SchemaError(f"{path} must be >= {minimum}")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaError(f"{path} must be an array")
    return value


def _enum(value: Any, enum_type: Type[Enum], path: str) -> Any:
    try:
        return enum_type(_string(value, path))
    except ValueError as exc:
        raise SchemaError(f"{path} has an unsupported value") from exc


def _absolute_path(value: Any, path: str) -> str:
    result = _string(value, path)
    if '\0' in result or not os.path.isabs(result):
        raise SchemaError(f"{path} must be an absolute path")
    return os.path.normpath(result)


def _argv(value: Any, path: str) -> tuple[str, ...]:
    values = _list(value, path)
    if not values:
        raise SchemaError(f"{path} must not be empty")
    result = []
    for index, item in enumerate(values):
        arg = _string(item, f"{path}[{index}]")
        if '\0' in arg:
            raise SchemaError(f"{path}[{index}] contains a NUL byte")
        if _SHELL_META.search(arg):
            raise SchemaError(f"{path}[{index}] contains shell syntax")
        result.append(arg)
    if os.path.basename(result[0]).lower() in _SHELL_LAUNCHERS:
        raise SchemaError(f"{path} must not invoke a shell")
    return tuple(result)


def _inside(root: str, candidate: str) -> bool:
    try:
        return os.path.commonpath((os.path.normpath(root), os.path.normpath(candidate))) == os.path.normpath(root)
    except ValueError:
        return False


def _cwd(value: Any, snapshot_root: str, path: str) -> str:
    cwd = _string(value, path)
    candidate = cwd if os.path.isabs(cwd) else os.path.join(snapshot_root, cwd)
    if not _inside(snapshot_root, candidate):
        raise SchemaError(f"{path} escapes snapshot_root")
    return cwd


def _artifact_path(value: Any, path: str) -> str:
    result = _string(value, path)
    if os.path.isabs(result) or "\\" in result or any(ord(character) < 32 or ord(character) == 127 for character in result):
        raise SchemaError(f"{path} must be a relative POSIX path")
    parts = result.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise SchemaError(f"{path} contains unsafe path traversal")
    return result


def _check_spec(value: Any, snapshot_root: str, path: str) -> CheckSpec:
    obj = _object(value, path)
    _keys(obj, {"id", "argv", "cwd", "shell", "timeout_seconds", "required", "rerun"}, path)
    _required(obj, {"id", "argv"}, path)
    timeout = None if obj.get("timeout_seconds") is None else _number(obj["timeout_seconds"], f"{path}.timeout_seconds", minimum=0)
    shell = _bool(obj.get("shell", False), f"{path}.shell")
    if shell:
        raise SchemaError(f"{path}.shell must be false")
    return CheckSpec(
        _string(obj["id"], f"{path}.id"), _argv(obj["argv"], f"{path}.argv"),
        _cwd(obj.get("cwd", "."), snapshot_root, f"{path}.cwd"), shell, timeout,
        _bool(obj.get("required", True), f"{path}.required"), _bool(obj.get("rerun", False), f"{path}.rerun"),
    )


def _path_list(value: Any, path: str, *, nonempty: bool = True) -> tuple[str, ...]:
    from .diff_budget import DiffGuardError, protected_path, safe_relative_path
    result = tuple(_artifact_path(item, f"{path}[{i}]") for i, item in enumerate(_list(value, path)))
    for item in result:
        try:
            safe_relative_path(item)
        except DiffGuardError as exc:
            raise SchemaError(f"{path}: {exc}") from exc
        if '.git' in item.split('/'):
            raise SchemaError(f"{path} cannot refer to Git metadata")
        if path == 'run_spec.allowed_paths' and protected_path(item):
            raise SchemaError(f"{path} contains a protected configuration/verification surface: {item}")
    if nonempty and not result:
        raise SchemaError(f"{path} must not be empty")
    if len(set(result)) != len(result):
        raise SchemaError(f"{path} contains duplicate paths")
    return result


def _patch_step(value: Any, path: str) -> PatchStep:
    obj = _object(value, path)
    _keys(obj, {"id", "description", "changes"}, path)
    _required(obj, {"id", "description", "changes"}, path)
    changes = []
    for index, value in enumerate(_list(obj["changes"], f"{path}.changes")):
        location = f"{path}.changes[{index}]"
        change = _object(value, location)
        _keys(change, {"path", "before_sha256", "content"}, location)
        _required(change, {"path", "before_sha256", "content"}, location)
        before = change["before_sha256"]
        if before is not None:
            before = _string(before, f"{location}.before_sha256")
            if not _SHA256.fullmatch(before):
                raise SchemaError(f"{location}.before_sha256 must be a lower-case SHA-256 digest")
        content = change["content"]
        if content is not None:
            content = _string(content, f"{location}.content", nonempty=False)
            if "\0" in content:
                raise SchemaError(f"{location}.content must be text without NUL bytes")
            try:
                content.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise SchemaError(f"{location}.content must be valid UTF-8 text") from exc
        if before is None and content is None:
            raise SchemaError(f"{location} cannot delete a nonexistent file")
        changes.append(PatchChange(_artifact_path(change["path"], f"{location}.path"), before, content))
    if not changes:
        raise SchemaError(f"{path}.changes must not be empty")
    if len({change.path for change in changes}) != len(changes):
        raise SchemaError(f"{path}.changes contains duplicate paths")
    return PatchStep(_string(obj["id"], f"{path}.id"), _string(obj["description"], f"{path}.description"), tuple(changes))


def load_run_spec(value: Any) -> RunSpec:
    obj = _object(_decode(value, "run_spec"), "run_spec")
    base = {"repo_path", "snapshot_root", "mode", "checks"}
    write = {"objective", "behavior_budget", "allowed_paths", "oracle_checks", "oracle_paths", "protected_paths", "limits", "steps"}
    _keys(obj, base | write, "run_spec")
    _required(obj, {"repo_path", "snapshot_root", "mode", "checks"}, "run_spec")
    repo_path = _absolute_path(obj["repo_path"], "run_spec.repo_path")
    snapshot_root = _absolute_path(obj["snapshot_root"], "run_spec.snapshot_root")
    checks = tuple(_check_spec(v, snapshot_root, f"run_spec.checks[{i}]") for i, v in enumerate(_list(obj["checks"], "run_spec.checks")))
    ids = [c.id for c in checks]
    if len(ids) != len(set(ids)):
        raise SchemaError("run_spec.checks contains duplicate check IDs")
    mode = _enum(obj["mode"], RunMode, "run_spec.mode")
    if mode is RunMode.DIAGNOSE:
        if set(obj) & write:
            raise SchemaError("diagnose does not accept write-mode fields")
        return RunSpec(repo_path, snapshot_root, mode, checks)
    _required(obj, write - {"protected_paths"}, "run_spec")
    objective = _string(obj["objective"], "run_spec.objective")
    if not objective.strip():
        raise SchemaError("run_spec.objective must describe the intended change")
    if obj["behavior_budget"] != "preserve":
        raise SchemaError("write modes support only behavior_budget 'preserve'")
    allowed = _path_list(obj["allowed_paths"], "run_spec.allowed_paths")
    oracle_paths = _path_list(obj["oracle_paths"], "run_spec.oracle_paths")
    protected = _path_list(obj.get("protected_paths", []), "run_spec.protected_paths", nonempty=False)
    oracles = tuple(_string(item, "run_spec.oracle_checks[]") for item in _list(obj["oracle_checks"], "run_spec.oracle_checks"))
    if not oracles or len(set(oracles)) != len(oracles):
        raise SchemaError("run_spec.oracle_checks must contain distinct check IDs")
    required_checks = {check.id for check in checks if check.required}
    if not set(oracles) <= required_checks:
        raise SchemaError("run_spec.oracle_checks must name explicitly required checks")
    limits_obj = _object(obj["limits"], "run_spec.limits")
    _keys(limits_obj, {"max_files", "max_changed_lines", "max_steps"}, "run_spec.limits")
    _required(limits_obj, {"max_files", "max_changed_lines", "max_steps"}, "run_spec.limits")
    limits = DiffLimits(*(_integer(limits_obj[key], f"run_spec.limits.{key}", minimum=1) for key in ("max_files", "max_changed_lines", "max_steps")))
    steps = tuple(_patch_step(item, f"run_spec.steps[{i}]") for i, item in enumerate(_list(obj["steps"], "run_spec.steps")))
    if len(steps) > limits.max_steps:
        raise SchemaError("run_spec.steps exceeds max_steps")
    if len({step.id for step in steps}) != len(steps):
        raise SchemaError("run_spec.steps contains duplicate IDs")
    if set(allowed) & (set(oracle_paths) | set(protected)):
        raise SchemaError("allowed_paths overlaps protected oracle or declared protected paths")
    if any(change.path not in allowed for step in steps for change in step.changes):
        raise SchemaError("step changes must be explicitly listed in allowed_paths")
    return RunSpec(repo_path, snapshot_root, mode, checks, objective, "preserve", allowed, oracles, oracle_paths, protected, limits, steps)


def _artifact(value: Any, path: str) -> ArtifactRef:
    obj = _object(value, path)
    _keys(obj, {"path", "sha256", "size_bytes", "media_type"}, path)
    _required(obj, {"path"}, path)
    digest = obj.get("sha256")
    if digest is not None:
        digest = _string(digest, f"{path}.sha256").lower()
        if not _SHA256.fullmatch(digest):
            raise SchemaError(f"{path}.sha256 must be a SHA-256 hex digest")
    size = obj.get("size_bytes")
    if size is not None:
        size = _integer(size, f"{path}.size_bytes", minimum=0)
    media = obj.get("media_type")
    if media is not None:
        media = _string(media, f"{path}.media_type")
    return ArtifactRef(_artifact_path(obj["path"], f"{path}.path"), digest, size, media)


def _attempt(value: Any, snapshot_root: str, path: str) -> CommandAttempt:
    obj = _object(value, path)
    allowed = {"check_id", "argv", "cwd", "status", "exit_code", "duration_ms", "stdout_artifact", "stderr_artifact", "sandboxed"}
    _keys(obj, allowed, path)
    _required(obj, {"check_id", "argv", "cwd", "status", "sandboxed"}, path)
    exit_code = None if obj.get("exit_code") is None else _integer(obj["exit_code"], f"{path}.exit_code")
    duration = None if obj.get("duration_ms") is None else _number(obj["duration_ms"], f"{path}.duration_ms", minimum=0)
    return CommandAttempt(
        _string(obj["check_id"], f"{path}.check_id"), _argv(obj["argv"], f"{path}.argv"),
        _cwd(obj["cwd"], snapshot_root, f"{path}.cwd"), _enum(obj["status"], AttemptStatus, f"{path}.status"),
        exit_code, duration,
        _artifact(obj["stdout_artifact"], f"{path}.stdout_artifact") if obj.get("stdout_artifact") is not None else None,
        _artifact(obj["stderr_artifact"], f"{path}.stderr_artifact") if obj.get("stderr_artifact") is not None else None,
        _bool(obj["sandboxed"], f"{path}.sandboxed"),
    )


def _check_record(value: Any, snapshot_root: str, path: str) -> CheckRecord:
    obj = _object(value, path)
    _keys(obj, {"check_id", "status", "attempts", "finding_ids", "required"}, path)
    _required(obj, {"check_id", "status"}, path)
    check_id = _string(obj["check_id"], f"{path}.check_id")
    attempts = tuple(_attempt(v, snapshot_root, f"{path}.attempts[{i}]") for i, v in enumerate(_list(obj.get("attempts", []), f"{path}.attempts")))
    for i, attempt in enumerate(attempts):
        if attempt.check_id != check_id:
            raise SchemaError(f"{path}.attempts[{i}].check_id does not match check_id")
    findings = tuple(_string(v, f"{path}.finding_ids[{i}]") for i, v in enumerate(_list(obj.get("finding_ids", []), f"{path}.finding_ids")))
    return CheckRecord(check_id, _enum(obj["status"], CheckStatus, f"{path}.status"), attempts, findings, _bool(obj.get("required", True), f"{path}.required"))


def _finding(value: Any, path: str) -> Finding:
    obj = _object(value, path)
    allowed = {"id", "title", "source", "evidence_refs", "severity", "impact", "confidence", "recommended_action", "counterargument", "path", "line", "column"}
    _keys(obj, allowed, path)
    _required(obj, {"id", "title", "source", "evidence_refs", "severity", "impact", "confidence", "recommended_action", "counterargument"}, path)
    refs = tuple(_artifact_path(v, f"{path}.evidence_refs[{i}]") for i, v in enumerate(_list(obj["evidence_refs"], f"{path}.evidence_refs")))
    line = None if obj.get("line") is None else _integer(obj["line"], f"{path}.line", minimum=1)
    column = None if obj.get("column") is None else _integer(obj["column"], f"{path}.column", minimum=1)
    return Finding(
        _string(obj["id"], f"{path}.id"), _string(obj["title"], f"{path}.title"), _string(obj["source"], f"{path}.source"), refs,
        _enum(obj["severity"], FindingSeverity, f"{path}.severity"), _string(obj["impact"], f"{path}.impact"),
        _number(obj["confidence"], f"{path}.confidence", minimum=0, maximum=1), _string(obj["recommended_action"], f"{path}.recommended_action"),
        _string(obj["counterargument"], f"{path}.counterargument"),
        _string(obj["path"], f"{path}.path") if obj.get("path") is not None else None, line, column,
    )


def load_findings(value: Any) -> tuple[Finding, ...]:
    raw = _decode(value, "findings")
    return tuple(_finding(item, f"findings[{i}]") for i, item in enumerate(_list(raw, "findings")))


def _discovery(value: Any) -> DiscoveryInfo:
    obj = _object(value, "run_manifest.discovery")
    _keys(obj, {"git_root", "head", "branch", "dirty", "candidates"}, "run_manifest.discovery")
    _required(obj, {"git_root", "head", "branch", "dirty"}, "run_manifest.discovery")
    return DiscoveryInfo(_absolute_path(obj["git_root"], "discovery.git_root"), _string(obj["head"], "discovery.head"), _string(obj["branch"], "discovery.branch"), _bool(obj["dirty"], "discovery.dirty"), tuple(_string(v, "discovery.candidates[]") for v in _list(obj.get("candidates", []), "discovery.candidates")))


def load_run_manifest(value: Any) -> RunManifest:
    obj = _object(_decode(value, "run_manifest"), "run_manifest")
    allowed = {"run_id", "mode", "repo_path", "snapshot_root", "status", "checks", "findings", "artifacts", "discovery", "stop_reason"}
    _keys(obj, allowed, "run_manifest")
    _required(obj, {"run_id", "mode", "repo_path", "snapshot_root", "status"}, "run_manifest")
    repo = _absolute_path(obj["repo_path"], "run_manifest.repo_path")
    snapshot = _absolute_path(obj["snapshot_root"], "run_manifest.snapshot_root")
    checks = tuple(_check_record(v, snapshot, f"run_manifest.checks[{i}]") for i, v in enumerate(_list(obj.get("checks", []), "run_manifest.checks")))
    if len({c.check_id for c in checks}) != len(checks):
        raise SchemaError("run_manifest.checks contains duplicate check IDs")
    findings = tuple(_finding(v, f"run_manifest.findings[{i}]") for i, v in enumerate(_list(obj.get("findings", []), "run_manifest.findings")))
    if len({f.id for f in findings}) != len(findings):
        raise SchemaError("run_manifest.findings contains duplicate finding IDs")
    artifacts = tuple(_artifact(v, f"run_manifest.artifacts[{i}]") for i, v in enumerate(_list(obj.get("artifacts", []), "run_manifest.artifacts")))
    if len({a.path for a in artifacts}) != len(artifacts):
        raise SchemaError("run_manifest.artifacts contains duplicate paths")
    manifest = RunManifest(_string(obj["run_id"], "run_manifest.run_id"), _enum(obj["mode"], RunMode, "run_manifest.mode"), repo, snapshot, _enum(obj["status"], ManifestStatus, "run_manifest.status"), checks, findings, artifacts, _discovery(obj["discovery"]) if obj.get("discovery") is not None else None, _string(obj["stop_reason"], "run_manifest.stop_reason") if obj.get("stop_reason") is not None else None)
    if manifest.mode is not RunMode.DIAGNOSE:
        by_path = {artifact.path: artifact for artifact in artifacts}
        required_artifacts = {'write/evidence.json'}
        if manifest.status is ManifestStatus.PASSED:
            required_artifacts.add('write/final.patch')
        if any(path not in by_path or by_path[path].sha256 is None or by_path[path].size_bytes is None for path in required_artifacts):
            raise SchemaError('write manifests require hashed change evidence and a hashed patch for a pass')
    from .manifest import derive_manifest_status
    derived = derive_manifest_status(manifest.checks, stop_reason=manifest.stop_reason, artifact_paths={a.path for a in artifacts})
    if manifest.status is not derived:
        raise SchemaError("run_manifest.status is asserted or inconsistent; status is derived")
    return manifest


def load_artifact_ref(value: Any) -> ArtifactRef:
    return _artifact(_decode(value, "artifact_ref"), "artifact_ref")


def load_check_spec(value: Any, snapshot_root: str) -> CheckSpec:
    root = _absolute_path(snapshot_root, "snapshot_root")
    return _check_spec(_decode(value, "check_spec"), root, "check_spec")


def load_command_attempt(value: Any, snapshot_root: str) -> CommandAttempt:
    root = _absolute_path(snapshot_root, "snapshot_root")
    return _attempt(_decode(value, "command_attempt"), root, "command_attempt")


def load_check_record(value: Any, snapshot_root: str) -> CheckRecord:
    root = _absolute_path(snapshot_root, "snapshot_root")
    return _check_record(_decode(value, "check_record"), root, "check_record")


def load_finding(value: Any) -> Finding:
    raw = _decode(value, "finding")
    return _finding(raw, "finding")


parse_run_spec = load_run_spec
parse_run_manifest = load_run_manifest
