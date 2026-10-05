# Anti-Slop Diagnose Report

- Run: `pilot-upstream-d987d2d-v2`
- Check status: **passed**
- Repository: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/pilot-source`
- Snapshot: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/pilot-snapshot-v2`

## Discovery

- Git root: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/pilot-source`
- HEAD: `d987d2d69ec5be5eb3f559266dbc1528b72d1ef5`
- Branch: `main`
- Dirty at discovery: **False**
- Command candidates discovered (not executed): 2

## Checks

| Check | Required | Derived status | Attempts |
|---|---:|---|---:|
| `core-suite` | True | **passed** | 1 |
| `trust-repro` | True | **passed** | 1 |

## Command attempts

- `core-suite` attempt 1: argv `["python3", "-m", "unittest", "tests.test_schema", "tests.test_artifacts_manifest", "tests.test_findings_report_checkpoint", "tests.test_cli", "-v"]`
  - cwd `scripts`; exit `0`; status `passed`; sandboxed `True`; duration `87.83763999963412` ms
  - [stdout](checks/0dc56990a7268b8b/attempt-1.stdout) SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; 0 bytes
  - [stderr](checks/0dc56990a7268b8b/attempt-1.stderr) SHA-256 `ca801c6471af31326e6ac2e4009e0660356d8cf6d838591734a0e9acd496af14`; 3947 bytes
- `trust-repro` attempt 1: argv `["python3", "-c", "exec(\"import json,tempfile\\nfrom anti_slop_core.artifacts import ArtifactStore\\nfrom anti_slop_core.manifest import derive_check_status\\nfrom anti_slop_core.findings import is_no_edit_correct\\nfrom anti_slop_core.models import *\\nwith tempfile.TemporaryDirectory() as home:\\n s=ArtifactStore('proof',home)\\n s.create()\\n out=s.put_bytes('out',b'')\\n err=s.put_bytes('err',b'')\\n a=CommandAttempt('unit',('/bin/true',),'.',AttemptStatus.PASSED,0,1,out,err,False)\\n c=CheckRecord('unit',CheckStatus.PASSED,(a,))\\n m=RunManifest('proof',RunMode.DIAGNOSE,'/repo','/snapshot',ManifestStatus.PASSED,(),(),())\\n print(json.dumps({'unsandboxed_pass':derive_check_status(c).value,'missing_hash_accepted':s.verify(ArtifactRef('out')),'asserted_no_edit':is_no_edit_correct(m,())},sort_keys=True))\")"]`
  - cwd `scripts`; exit `0`; status `passed`; sandboxed `True`; duration `46.166469997842796` ms
  - [stdout](checks/996978304d49c7bb/attempt-1.stdout) SHA-256 `ccb4f03e4a8cd170dfef2f4aa52d8d639c1e35371e8d9de40185f9b7e06698dc`; 88 bytes
  - [stderr](checks/996978304d49c7bb/attempt-1.stderr) SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; 0 bytes

## Findings

### trust-1: Unsandboxed zero-exit attempt counts as passed

- Source: `trust-repro`
- Severity: **high**
- Impact: A caller can claim sandboxed verification without isolation; the original status derivation ignores the sandboxed flag.
- Confidence: 1.00
- Recommended action: Reject passed attempts with sandboxed=false and verify the regression with a zero-exit unsandboxed attempt.
- Counterargument: The original CLI normally constructs sandboxed attempts; the vulnerability matters when importing or constructing manifests.
- Evidence: `checks/996978304d49c7bb/attempt-1.stdout`

### trust-2: Artifact verification accepts absent integrity metadata

- Source: `trust-repro`
- Severity: **high**
- Impact: A manifest can omit hashes and sizes, so changed output can be treated as verified evidence.
- Confidence: 1.00
- Recommended action: Require SHA-256 and size metadata for verification and test missing metadata and post-capture tampering.
- Counterargument: Normal capture populates metadata; existing validators admit externally supplied incomplete artifacts.
- Evidence: `checks/996978304d49c7bb/attempt-1.stdout`

### trust-3: No-edit decision trusts an asserted pass without checks

- Source: `trust-repro`
- Severity: **medium**
- Impact: Reports can endorse a no-edit decision without recorded required attempts if constructed models bypass the JSON loader.
- Confidence: 1.00
- Recommended action: Derive the decision from required attempts and clean discovery, then test an asserted pass with no attempts.
- Counterargument: Strict JSON loading rejects inconsistent manifest status, reducing exposure through the existing validate-findings CLI.
- Evidence: `checks/996978304d49c7bb/attempt-1.stdout`

## Decision

No-edit correctness is **not established**. Resolve the check/finding gaps above before treating the run as clean.

## Evidence integrity

Declared artifacts: 4. Each artifact must be independently hash- and size-verified before trusting a pass.
