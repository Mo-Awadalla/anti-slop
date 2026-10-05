# Anti-Slop Diagnose Report

- Run: `skill-evaluation-unavailable`
- Check status: **blocked**
- Repository: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/anti-slop-skill-evaluation/unavailable/source`
- Snapshot: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/anti-slop-skill-evaluation/unavailable/snapshot`

## Discovery

- Git root: `/var/home/mohamed/Documents/Codex/2026-10-04/u-w/work/anti-slop-skill-evaluation/unavailable/source`
- HEAD: `1eaf2e0a9d7eac0cbf83fbd24b0760f05233cc88`
- Branch: `master`
- Dirty at discovery: **False**
- Command candidates discovered (not executed): 0

## Adapter capabilities

```json
{
  "can_generate_findings": false,
  "can_mutate": false,
  "can_run_checks": true,
  "ecosystem": "python",
  "note": "generic tokenized checks; no language-specific findings",
  "supported": true
}
```

## Checks

| Check | Required | Derived status | Attempts |
|---|---:|---|---:|
| `selected-check` | True | **unavailable** | 1 |

## Command attempts

- `selected-check` attempt 1: argv `["python3", "-B", "check.py"]`
  - cwd `.`; exit `None`; status `unavailable`; sandboxed `False`; duration `0.0` ms
  - [stdout](checks/bdb49cea1f395a1a/attempt-1.stdout) SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; 0 bytes
  - [stderr](checks/bdb49cea1f395a1a/attempt-1.stderr) SHA-256 `a4069072e78ccfdc8267242f9928540b3107506b0cc4aec778592203f79837ce`; 42 bytes

## Findings

No findings were supplied. This is not evidence of correctness unless every required check passed.

## Decision

No-edit correctness is **not established**. Resolve the check/finding gaps above before treating the run as clean.

## Evidence integrity

Declared artifacts: 2. Each artifact must be independently hash- and size-verified before trusting a pass.
