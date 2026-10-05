# Upstream repository pilot

On October 4, 2026, the expanded workflow diagnosed the original anti-slop
repository at commit `d987d2d69ec5be5eb3f559266dbc1528b72d1ef5`, the main revision
pulled for this task. A separate clean local clone was used. The source checkout
remained clean, on the same revision and branch, with matching content
fingerprints before and after execution.

## Recorded checks and useful findings

The original complete 35-test baseline passed on this host outside the outer
execution restriction. The read-only pilot then ran 25 existing core tests
inside actual Bubblewrap, followed by an explicit Python witness of three
trust decisions. Both selected checks exited zero. The witness printed:

```json
{"asserted_no_edit": true, "missing_hash_accepted": true, "unsandboxed_pass": "passed"}
```

That is successful reproduction of defects, not proof that the repository was
healthy. The pilot report includes three actionable findings and therefore
does not endorse a clean/no-edit conclusion:

| Finding | Consequence | Counterargument and scope |
| --- | --- | --- |
| Unsandboxed attempt accepted as passed | A recorded zero-exit attempt could count as sandbox verification without isolation | Normal CLI capture uses the sandbox; imported or constructed evidence still needs enforcement |
| Missing artifact hash/size accepted | A declared artifact could be treated as verified without checking content integrity | Normal capture populates metadata; external incomplete evidence was accepted |
| Asserted pass endorsed without checks | Constructed models could receive a no-edit decision without required attempts | The JSON loader already rejects inconsistent status, reducing the CLI exposure |

The relevant source locations, confidence, actions, counterarguments, and
same-check artifact references are in [findings.json](pilot-evidence/findings.json).
A fresh loader parsed the manifest, independently verified every recorded
artifact hash and byte count, and validated the findings' capture provenance.
Semantic correctness was reviewed from the original implementation and the
witness; the finding validator alone cannot establish it.

All three defects are fixed in the completed implementation. Acceptance tests
now reject unsandboxed passes, absent hash/size metadata, and no-edit endorsement
from empty attempts. Additional audit regressions cover artifact aliases,
foreign-check evidence, inconsistent write audit records, and protected
verification inputs.

## Artifacts and reproduction

- [Exact run specification](pilot-evidence/run-spec.json)
- [Manifest with findings](pilot-evidence/cache/anti-slop/runs/pilot-upstream-d987d2d-v2/manifest.json)
- [Report with captured command and output links](pilot-evidence/cache/anti-slop/runs/pilot-upstream-d987d2d-v2/report.md)

For reproduction, clone the upstream revision above, substitute its absolute
path and a fresh external snapshot destination in the spec, choose a writable
external `HERMES_HOME`, and invoke the completed runner's `diagnose` command.
Use the separate findings file with `validate-findings`. The recorded paths
identify this task's actual run, not portable preconfigured directories. New
runs create new manifest/artifact references; findings must reference those
captures, not the earlier run's files.

The test-module selection excluded sandbox/orchestration tests to avoid
claiming that nesting a second Bubblewrap boundary verified the host boundary.
The complete finished suite's real host-boundary and write-mode checks were
run separately: 81 passed, zero skipped. See [acceptance results](acceptance-results.md).

## Observed friction and design decision

The optional runner took an explicit spec, a clean clone, an external writable
artifact directory, and a host where Bubblewrap could start. The outer
execution restriction initially prevented its network namespace. Running the
same isolation under the permitted host execution resolved that limitation;
no unsandboxed runner fallback was used.

The witness initially required a correction to its authoring indentation; that
failed development attempt was not treated as defect evidence. Its corrected
exact argv and real output are retained. The conservative shell-syntax filter
also requires deliberate packaging of multiline Python arguments. These are
reproducibility costs, so ordinary contextual inspection remains the skill's
main path and the runner is optional support. This pilot did not justify a new
profile registry or command-discovery automation.

This is one non-blinded pilot of the project's own upstream repository. It
shows reproducible, relevant trust findings with explicit counterarguments and
source preservation. It does not establish model effectiveness, population
false-positive rates, general review-time savings, or a cross-project
maintainability improvement.
