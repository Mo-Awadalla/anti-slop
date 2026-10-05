"""Content-addressed-enough artifact storage for a single diagnose run."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional

from .models import ArtifactRef


class ArtifactError(ValueError):
    pass


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ArtifactStore:
    def __init__(self, run_id: str, hermes_home: Optional[str] = None):
        if not _RUN_ID.fullmatch(run_id):
            raise ArtifactError("unsafe run_id")
        home = Path(hermes_home or os.environ.get("HERMES_HOME", "~/.hermes")).expanduser().resolve()
        self.root = home / "cache" / "anti-slop" / "runs" / run_id
        self.run_id = run_id

    def create(self) -> Path:
        self.root.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.root.mkdir()
        except FileExistsError as exc:
            raise ArtifactError(f"run already exists: {self.run_id}") from exc
        return self.root

    def _safe_path(self, relative: str) -> Path:
        if not isinstance(relative, str) or not relative or os.path.isabs(relative) or "\\" in relative:
            raise ArtifactError("artifact path must be relative")
        parts = relative.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ArtifactError("artifact path contains traversal")
        candidate = (self.root / relative).resolve(strict=False)
        try:
            inside = os.path.commonpath((str(self.root.resolve()), str(candidate))) == str(self.root.resolve())
        except ValueError:
            inside = False
        if not inside:
            raise ArtifactError("artifact path escapes run directory")
        return candidate

    def put_bytes(self, relative: str, data: bytes, media_type: Optional[str] = None) -> ArtifactRef:
        if not isinstance(data, bytes):
            raise TypeError("artifact data must be bytes")
        target = self._safe_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(data).hexdigest()
        try:
            with target.open("xb") as handle:
                handle.write(data)
        except FileExistsError as exc:
            raise ArtifactError(f"artifact already exists: {relative}") from exc
        return ArtifactRef(relative, digest, len(data), media_type)

    def verify(self, ref: ArtifactRef) -> bool:
        try:
            target = self._safe_path(ref.path)
            if not target.is_file() or target.is_symlink():
                return False
            data = target.read_bytes()
        except (OSError, ArtifactError):
            return False
        if ref.size_bytes is not None and len(data) != ref.size_bytes:
            return False
        if ref.sha256 is not None and hashlib.sha256(data).hexdigest() != ref.sha256:
            return False
        return True

    def read(self, ref: ArtifactRef) -> bytes:
        if not self.verify(ref):
            raise ArtifactError(f"artifact verification failed: {ref.path}")
        return self._safe_path(ref.path).read_bytes()
