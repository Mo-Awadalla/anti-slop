"""Adapter boundary: generic execution only, no fabricated ecosystem support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AdapterInfo:
    name: str
    capabilities: tuple[str, ...]
    reduced: bool


@dataclass(frozen=True)
class AdapterCapabilities:
    ecosystem: str
    supported: bool
    can_run_checks: bool
    can_generate_findings: bool
    can_mutate: bool
    note: str


class GenericAdapter:
    name = "generic"

    def __init__(self, snapshot_root: str | Path | None = None):
        self.snapshot_root = Path(snapshot_root) if snapshot_root is not None else None
        self.capabilities = self._detect() if self.snapshot_root else AdapterCapabilities("unknown", False, True, False, False, "generic checks only")

    def _detect(self) -> AdapterCapabilities:
        names = {p.name.lower() for p in self.snapshot_root.iterdir()} if self.snapshot_root and self.snapshot_root.is_dir() else set()
        if "pyproject.toml" in names or any(name.endswith(".py") for name in names):
            return AdapterCapabilities("python", True, True, False, False, "generic tokenized checks; no language-specific findings")
        if "package.json" in names:
            return AdapterCapabilities("javascript", False, True, False, False, "generic checks only; ecosystem adapter unavailable")
        if "cargo.toml" in names:
            return AdapterCapabilities("rust", False, True, False, False, "generic checks only; ecosystem adapter unavailable")
        return AdapterCapabilities("unknown", False, True, False, False, "unsupported ecosystem; generic checks only")

    def discover(self, repo: str | Path) -> AdapterInfo:
        return AdapterInfo(self.name, ("git", "repository-map", "explicit-checks"), True)

    def availability(self) -> str:
        return "present"

    def summary(self) -> dict:
        return {"ecosystem": self.capabilities.ecosystem, "supported": self.capabilities.supported, "can_run_checks": self.capabilities.can_run_checks, "can_generate_findings": self.capabilities.can_generate_findings, "can_mutate": self.capabilities.can_mutate, "note": self.capabilities.note}


def select_adapter(snapshot_root: str | Path) -> GenericAdapter:
    return GenericAdapter(snapshot_root)
