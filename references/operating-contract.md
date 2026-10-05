# Anti-Slop P0 Operating Contract

## Purpose

Establish the smallest reviewable boundary for the user-local anti-slop skill. P0 permits read-only diagnosis and validation while forbidding source mutation and write-mode automation.

## Exposed surface

The P0 CLI exposes only:

- `diagnose --spec PATH`
- `validate-findings --manifest PATH --findings PATH`

The CLI must not expose:

- `refactor`
- `repair-slop`

## P0 behavior

A diagnose run:

- captures Git root, HEAD, branch, dirty state, and relevant repository candidates;
- stops before checks when the source repository is dirty;
- creates a detached clean snapshot;
- runs only explicit tokenized checks inside Bubblewrap with no network;
- captures stdout and stderr as hash- and size-recorded artifacts;
- derives manifest status from attempts and integrity conditions;
- renders a human-readable report;
- never edits the source repository.

Finding validation requires declared evidence references and rejects duplicate, unknown, unverifiable, vague, or unsupported findings. Subjective style preferences are not emitted as objective defects.

## Explicit P0 exclusions

P0 contains no implementation for:

- arbitrary shell execution;
- automatic finding generation;
- refactoring or repair actions;
- source-repository mutation;
- write-mode rollback of a user repository.

Adding any excluded capability requires a separate approved task with tests and a revised contract.

## Implementation constraints

- Use Python standard library only.
- Keep parser construction separate from command execution.
- Prefer public parser behavior in tests over private implementation details.
- Do not modify the Hermes core checkout while developing this skill.

## Verification contract

Run these commands from the skill's `scripts/` directory:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q run.py anti_slop_core tests
python3 run.py --help
```

A real smoke run must additionally verify the emitted manifest, report, artifact hashes, and source-repository immutability.
