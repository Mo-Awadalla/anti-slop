"""Unsigned in-toto/SLSA provenance describing recorded local execution only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from .artifacts import ArtifactStore
from .manifest import check_to_dict, validate_manifest_artifacts
from .models import RunManifest, RunSpec
from .schema import SchemaError


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def build_provenance(manifest: RunManifest, manifest_path: Path, spec: RunSpec, *, spec_bytes: bytes,
                     started_on: str, finished_on: str) -> dict:
    """Call with the actual spec passed to the runner, not a later supplied spec."""
    store = ArtifactStore(manifest.run_id)
    store.root = manifest_path.parent
    validate_manifest_artifacts(manifest, store)
    if manifest.repo_path != spec.repo_path or manifest.snapshot_root != spec.snapshot_root or manifest.mode != spec.mode:
        raise SchemaError('provenance spec disagrees with completed run')
    manifest_bytes = manifest_path.read_bytes()
    subjects = [{'name': 'manifest.json', 'digest': {'sha256': hashlib.sha256(manifest_bytes).hexdigest()}}]
    dependencies = []
    if manifest.discovery is not None:
        dependencies.append({'uri': Path(manifest.discovery.git_root).resolve().as_uri(),
                             'digest': {'gitCommit': manifest.discovery.head},
                             'annotations': {'dirtyAtDiscovery': manifest.discovery.dirty}})
    byproducts = []
    for ref in manifest.artifacts:
        resource = {'name': ref.path, 'digest': {'sha256': ref.sha256},
                    'annotations': {'sizeBytes': ref.size_bytes}}
        if ref.media_type is not None:
            resource['mediaType'] = ref.media_type
        byproducts.append(resource)
        if ref.path == 'write/final.patch':
            subjects.append({'name': ref.path, 'digest': {'sha256': ref.sha256}})
    return {
        '_type': 'https://in-toto.io/Statement/v1',
        'subject': subjects,
        'predicateType': 'https://slsa.dev/provenance/v1',
        'predicate': {
            'buildDefinition': {
                'buildType': 'urn:anti-slop:recorded-run:v1',
                'externalParameters': {'spec': _json_value(asdict(spec)),
                                       'specInputSha256': hashlib.sha256(spec_bytes).hexdigest()},
                'internalParameters': {'mode': manifest.mode.value, 'status': manifest.status.value,
                                       'stopReason': manifest.stop_reason,
                                       'checks': [check_to_dict(record) for record in manifest.checks],
                                       'attestation': 'unsigned local execution record; no SLSA level or isolation guarantee'},
                'resolvedDependencies': dependencies,
            },
            'runDetails': {
                'builder': {'id': 'urn:anti-slop:stdlib-runner'},
                'metadata': {'invocationId': manifest.run_id, 'startedOn': started_on, 'finishedOn': finished_on},
                'byproducts': byproducts,
            },
        },
    }


def write_provenance(manifest: RunManifest, manifest_path: Path, spec: RunSpec, *, spec_bytes: bytes,
                     started_on: str, finished_on: str) -> Path:
    document = build_provenance(manifest, manifest_path, spec, spec_bytes=spec_bytes,
                                started_on=started_on, finished_on=finished_on)
    target = manifest_path.parent / 'provenance.json'
    # Never add this file to (or rewrite) the manifest: that would make its
    # subject hash self-referential and invalidate existing artifact checks.
    with target.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(document, indent=2, sort_keys=True) + '\n')
    return target
