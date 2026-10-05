"""Frozen contracts for deterministic diagnosis and bounded write runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple


class RunMode(str, Enum):
    DIAGNOSE = "diagnose"
    REFACTOR = "refactor"
    REPAIR_SLOP = "repair-slop"


class AttemptStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    NOT_RUN = "not-run"


class CheckStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FLAKY = "flaky"
    NOT_RUN = "not-run"


class FindingSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ManifestStatus(str, Enum):
    PASSED = "passed"
    STOPPED = "stopped"
    BLOCKED = "blocked"
    FAILED = "failed"
    FLAKY = "flaky"
    ROLLED_BACK = "rolled_back"


@dataclass(frozen=True)
class CheckSpec:
    id: str
    argv: Tuple[str, ...]
    cwd: str = "."
    shell: bool = False
    timeout_seconds: Optional[float] = None
    required: bool = True
    rerun: bool = False


@dataclass(frozen=True)
class DiffLimits:
    max_files: int
    max_changed_lines: int
    max_steps: int


@dataclass(frozen=True)
class PatchChange:
    path: str
    before_sha256: Optional[str]
    content: Optional[str]


@dataclass(frozen=True)
class PatchStep:
    id: str
    description: str
    changes: Tuple[PatchChange, ...]


@dataclass(frozen=True)
class RunSpec:
    repo_path: str
    snapshot_root: str
    mode: RunMode = RunMode.DIAGNOSE
    checks: Tuple[CheckSpec, ...] = field(default_factory=tuple)
    objective: Optional[str] = None
    behavior_budget: Optional[str] = None
    allowed_paths: Tuple[str, ...] = field(default_factory=tuple)
    oracle_checks: Tuple[str, ...] = field(default_factory=tuple)
    oracle_paths: Tuple[str, ...] = field(default_factory=tuple)
    protected_paths: Tuple[str, ...] = field(default_factory=tuple)
    limits: Optional[DiffLimits] = None
    steps: Tuple[PatchStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ArtifactRef:
    path: str
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    media_type: Optional[str] = None


@dataclass(frozen=True)
class CommandAttempt:
    check_id: str
    argv: Tuple[str, ...]
    cwd: str
    status: AttemptStatus
    exit_code: Optional[int] = None
    duration_ms: Optional[float] = None
    stdout_artifact: Optional[ArtifactRef] = None
    stderr_artifact: Optional[ArtifactRef] = None
    sandboxed: bool = True


@dataclass(frozen=True)
class CheckRecord:
    check_id: str
    status: CheckStatus
    attempts: Tuple[CommandAttempt, ...] = field(default_factory=tuple)
    finding_ids: Tuple[str, ...] = field(default_factory=tuple)
    required: bool = True


@dataclass(frozen=True)
class Finding:
    """Nine semantic fields, plus optional source location metadata."""

    id: str
    title: str
    source: str
    evidence_refs: Tuple[str, ...]
    severity: FindingSeverity
    impact: str
    confidence: float
    recommended_action: str
    counterargument: str
    path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    @property
    def check_id(self) -> str:
        return self.source

    @property
    def evidence(self) -> Tuple[str, ...]:
        return self.evidence_refs

    @property
    def message(self) -> str:
        return self.title


@dataclass(frozen=True)
class DiscoveryInfo:
    git_root: str
    head: str
    branch: str
    dirty: bool
    candidates: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    mode: RunMode
    repo_path: str
    snapshot_root: str
    status: ManifestStatus
    checks: Tuple[CheckRecord, ...] = field(default_factory=tuple)
    findings: Tuple[Finding, ...] = field(default_factory=tuple)
    artifacts: Tuple[ArtifactRef, ...] = field(default_factory=tuple)
    discovery: Optional[DiscoveryInfo] = None
    stop_reason: Optional[str] = None
