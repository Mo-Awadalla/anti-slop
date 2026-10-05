# Anti-Slop: Remaining Work

This replaces the stale P1–P3 sequence. The current implementation already has the read-only diagnosis runner, explicit-check execution, evidence artifacts, manifest handling, and sandboxing. Do not rebuild those as the next milestone.

## Next: refocus the agent workflow

The runner is supporting infrastructure. Rework `SKILL.md` so the main product is an agent workflow for contextual code-quality judgment during implementation and review:

- inspect project intent and local conventions before judging;
- distinguish style preference from demonstrated maintenance, verification, behavior, or security cost;
- connect each finding to evidence, impact, confidence, and a counterargument;
- give concise, concrete prevention and remediation guidance without asserting that every cleanup is worthwhile;
- preserve the user's requested behavior and project constraints.

Keep the workflow useful even when the runner is unavailable or unnecessary. Do not add more machinery before this refocus is clear.

## Then: pilot and reduce friction

Run the read-only workflow on a small number of real repositories with the user's selected checks. Evaluate whether findings are useful, false positives are controlled, and the process takes an acceptable amount of time. Update the workflow from observed results.

Consider a fast path or reusable repository check profiles only if the pilot demonstrates that they save user effort without weakening evidence or scope control.

## Later: code-changing modes

There is no `refactor` or `repair-slop` implementation. Treat behavior-preserving refactoring and authorized repair as separate future designs. Before exposing a write mode, define its scope, explicit authorization, recovery/checkpoint behavior, verification oracle, stop conditions, and end-to-end acceptance cases. Keep “no edit” as a valid outcome.

Do not add a command placeholder for a future mode. Do not make diagnosis automatically mutate the target repository.
