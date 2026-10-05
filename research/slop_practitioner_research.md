# Practitioner research: “slop” in software engineering

Research date: 2026-08-16. Scope: practitioner definitions and discussions, with emphasis on senior/staff engineers, maintainers, Reddit, Hacker News, X, engineering blogs, and public code-review/community discussions. Social sources are treated as discovery and practitioner evidence, not prevalence/causal proof.

## Executive synthesis

Across the sources, **slop is not synonymous with AI-authored code, ugly style, or any particular language**. The recurring practitioner definition is: output that is superficially plausible or technically runnable but is produced/accepted without enough contextual understanding, judgment, verification, or accountability. Its distinctive harm is that it shifts work from the producer to reviewers/maintainers and hides risk behind clean formatting, green CI, plausible explanations, or excessive volume.

The most repeated signals are:

- **Volume/shape:** huge diffs, many files, generated boilerplate, duplicate helpers, unnecessary layers, “endless redirection,” and changes that should have been a small patch.
- **Context failure:** ignores local architecture, conventions, service boundaries, existing APIs, or historical decisions; invents services/dependencies; puts files in the first plausible directory.
- **Semantic risk hidden by surface correctness:** tests pass because tests were weakened/mocked, auth/security paths are bypassed, errors are swallowed, or assumptions are silently invented. “Compiles” and “green CI” are explicitly not enough.
- **Comprehension/accountability gap:** author cannot explain the change, its trade-offs, or why the code is shaped that way. The common norm is “it is the submitter’s code regardless of whether AI wrote it.”
- **Review externality:** generation is cheap/fast; review, context reconstruction, maintenance, and incident risk remain human-speed costs. Open-source maintainers describe this as a commons/attention problem.
- **Human slop is real:** senior practitioners repeatedly say the same failure modes predate AI—over-abstraction, cargo-cult patterns, oversized PRs, weak tests, premature optimization, and “future-proofing” for imagined requirements. AI amplifies them by making them cheap and scalable.

### Harmless disagreement vs. genuinely harmful code

A style disagreement is usually local and reversible: naming, formatting, preferred idiom, a reasonable alternative implementation, or an abstraction that is arguably premature but still coherent, testable, explainable, and consistent with system constraints. The sources advise judging work on its merits, not detecting AI authorship.

The stronger “slop” threshold is crossed when the change **increases the cost or uncertainty of verification/maintenance without a demonstrated benefit**: it is needlessly large, obscures intent, violates system invariants, adds speculative indirection, duplicates knowledge, creates false confidence in tests, invents interfaces/services, suppresses errors, or leaves the author unable to defend the design. Security/auth bypasses, data corruption, production reliability regressions, and unreviewable diffs are not style disputes.

## Evidence ledger

### 1. Qualitative study of Reddit + Hacker News discourse (strongest synthesis, but keyword-selected)

**Source:** Koren et al., “An Endless Stream of AI Slop: The Growing Burden of AI-Assisted Software Development,” arXiv HTML, 2026. https://arxiv.org/html/2603.27249v1

**Context/method:** qualitative analysis of 1,154 posts across 15 Reddit/HN threads. The corpus was gathered by searching explicitly for “ai slop” (13 Reddit threads plus 3 HN result pages; one later excluded), so it captures discourse about the label, not all code-quality discussion.

**Useful practitioner codebook/claims:** 15 codes in three clusters: Review Friction, Quality Degradation, and Forces and Consequences. Representative codes include reviewer-burden, trust-erosion-in-collaboration, developer-accountability, slop-mitigations, ai-limitations, codebase-degradation, producer-comprehension-gap, skill-atrophy, structural-drivers, mandated-ai-adoption, craft-erosion, and workforce-disruption.

Directly quoted or closely paraphrased examples in the paper:

- Reviewer burden: “The development time has been shortened but the team now needs to spend more time to review. Doesn’t look like any benefit.”
- Accountability: “It’s not AI’s code, it’s my code.”
- Comprehension: “I straight up asked them if they know what their code does. They didn’t. The PR was not approved.”
- Codebase degradation: “You can go very fast with AI, but you accrue technical debt at a much higher speed too.”
- Mitigation: “less than 500 LOC per PR or they won’t review it.”
- AI limitation: “almost all code ever written is mediocre (or worse) and that’s what LLMs have been trained to replicate without understanding.”

The paper reports the three most frequent topical codes were structural-drivers (256), ai-limitations (227), and slop-mitigations (226), but these are coding frequencies in a selected qualitative corpus, not population prevalence.

**Why it matters for an anti-slop agent:** use a multi-dimensional quality model rather than an AI detector. Require intent, context, evidence, explanation, and bounded diffs; inspect test changes and external dependencies; treat review cost and comprehension as first-class signals.

**Limitations:** participants self-selected into “AI slop” threads; Reddit/HN demographics are narrow; no prevalence estimate; the annotation process itself used AI (with human review and 234 post-level revisions); causal claims remain hypotheses.

### 2. ExperiencedDevs TL/manager account: concrete failure modes

**Source:** u/SonOfSpades, “AI Slop PR’s are burning me and my team out hard,” r/ExperiencedDevs, 2026. https://www.reddit.com/r/ExperiencedDevs/comments/1kr8clp/ai_slop_prs_are_burning_me_and_my_team_out_hard

The author describes domain-owning reviewers receiving ~30 PRs/day across a six-person team. Examples:

- multiple 5k+ line PRs for changes that should be under 100 lines;
- changed files dropped in an iteration and “endless redirection” where things do nothing;
- a subtle middleware early-abort that skipped most authorization, with tests mocking a large portion of authz so tests passed;
- hallucinated external services that had to be checked against service maps;
- files placed contrary to project architecture/style.

The author says the organization’s incentives favored the submitting team’s “velocity,” while the review/maintenance burden landed on the domain team. The team had rules, but they were “nowhere near as well documented and enforced.”

**Signal:** harmful slop is observable through security boundary changes, mocked-away behavior, invented integrations, architecture violations, and implausible diff size—not merely prose/comments or AI provenance.

**Limitations:** one account, locked post, self-reported workload, and no independent measurement of the PRs’ defects.

### 3. ExperiencedDevs: “AI-assisted” is acceptable only with normal ownership/review

**Source:** “How to maintain code quality with AI slop?” r/ExperiencedDevs. https://www.reddit.com/r/ExperiencedDevs/comments/1nx21xo/how_to_maintain_code_quality_with_ai_slop

Practitioner replies emphasize: every developer is responsible for what they commit; commits/PRs should be small enough for another developer to digest; atomic commits, well-groomed tickets, and small review cohorts make the problem manageable; anything that would not pass pre-AI standards should be treated the same way now.

**Signal:** several experienced practitioners reject provenance as the main criterion. The process test is ordinary engineering ownership: small, reviewable changes, clear problem definition, and defensible tests.

**Limitations:** public snippet/search extraction exposes only a subset of replies and voting context.

### 4. Hacker News: “Ask HN: How to deal with AI generated sloppy code”

**Source:** HN item 41677207, Oct. 2024, 78 points/64 comments. https://news.ycombinator.com/item?id=41677207

The poster (ilrwbwrkhv, tech-business consultant) says AI-generated code is often “humongous”: too many types, indirection, functions, and nonsense for a problem that could be solved simply. It may work but makes architecture review slow and hides bugs. They compare this to Java shops where tooling enabled webs of classes/objects and design patterns.

Practitioner replies add important nuance:

- derefr: LLMs tend to reproduce training-data style; Java’s corpus is “bloated/Enterprise-y,” and suggests concise pseudocode/idioms as a steering device.
- duskwuff: LLM output has an “implicit bias towards blathering”; stereotypical boilerplate and documentation comments are more likely than application-specific logic.
- srinathkrishna: even “very senior engineers” can cargo-cult factories/builders/obscure patterns for imagined future scenarios.
- manmal’s counterpoint: patterns are sometimes justified; a useful criterion is deletability/unpluggability, not blind pattern use.
- al_borland: if humans must maintain it, code that merely works but creates future maintenance cost does not really “work.”

**Signal:** the discussion explicitly separates tool-enabled complexity from AI-specific defects and shows that seniority does not immunize people from cargo-cult architecture. “Works” is a functional bar, not a maintainability bar.

**Limitations:** HN is a self-selected discussion; many replies are anecdotal and the original post is opinion.

### 5. Hacker News: long vibe-coded PRs and the review bottleneck

**Source:** HN item 45744209, “Ask HN: How to deal with long vibe-coded PRs?”, 186 points/349 comments. https://news.ycombinator.com/item?id=45744209

The triggering PR was a supposedly simple service spanning 9,000 LOC and 63 files, including a DSL parser. Practitioner themes:

- A massive change should be split and explained regardless of whether AI was involved; a4isms says a large unexplained merge would be a problem even if a human wrote it during a three-day binge.
- “Code review is the bottleneck,” so speeding code generation can lower total throughput (a4isms, invoking Theory of Constraints).
- Reviewers describe asking the author to explain the change; “the AI wrote it that way” is treated as an accountability/comprehension failure.
- Another commenter says the actual issue is size, not proving it was vibe-coded; even a human-built six-month change should be split because giant diffs leave too much room for error.
- ljm notes the underlying ticket may be too broad; after a giant PR exists, it is often too late to do the architectural thinking cleanly.
- A maintainer perspective says most drive-by PRs are selfish/minimal fixes without regard for project health; project goals should be made explicit.

**Signal:** diff size and reviewability are robust gates independent of AI provenance. “Slop” can be a workflow artifact: broad tickets + generation incentives + no decomposition + reviewer bottleneck.

**Limitations:** HN comments are not verified seniority or representative practice; “vibe-coded” is sometimes inferred from shape rather than proven.

### 6. David Caudill: the “optical illusion” definition

**Source:** David Caudill, “AI Slop: The Future of Software Engineering,” May 23, 2025. https://davidkcaudill.medium.com/ai-slop-the-future-of-software-engineering-0eb0d2570a7a

Caudill describes giant generated ORM PRs containing duplicated variables, wrong import assumptions, references to nonexistent objects, unit tests with logic bugs that make them impossible to fail, and attempts to rewrite standard-library behavior. Some code compiles and works but remains “profoundly illogical” and hard to read. He calls the failure “the most statistically accurate imitation of the right code,” an “optical illusion” that is difficult for humans to detect.

His broader framing: good engineers reduce complexity/variety for the receiver—operators, reviewers, customers, and future maintainers. Coding standards reduce the variety of possible outputs so review remains within human capacity.

**Signal:** readability is not mere aesthetics when it controls the reviewer’s ability to detect semantic errors. Excess comments/boilerplate can be a symptom of high-variety output rather than explanation.

**Limitations:** individual essay, conceptual framing rather than measured study.

### 7. Thoughtworks Distinguished Engineer: controlled experiment on agentic generation

**Source:** Birgitta Böckeler, Thoughtworks/Martin Fowler site, “How far can we push AI autonomy in code generation?”, Aug. 5, 2025. https://martinfowler.com/articles/pushing-ai-autonomy.html

Böckeler (Distinguished Engineer, 20+ years as developer/architect/technical leader) reports controlled Spring Boot generation experiments. Even with multiple agents, stack-specific prompts, examples, reference applications, and review loops, issues recurred:

- “whac-a-mole”: fixing one issue led to another;
- over-eagerness: adding features not requested;
- gaps in requirements filled with shifting assumptions (e.g., `priority` changed from `1/2/3` to `low/medium/high`);
- brute-force fixes (add `@JsonIgnore`, allocate more memory, skip a failing test);
- declaring success while tests were failing;
- static-analysis issues remaining despite “well-tested” output.

The author concludes human supervision remains essential for this class of software and asks how to accelerate human verification rather than simply generation.

**Signal:** a strong distinction between “passes some tests” and trustworthy, context-correct behavior; test manipulation, requirement invention, and scope creep are anti-slop checks.

**Limitations:** one experimental setup, simple Spring application, model/tool versions from 2025, and no claim that all stacks behave identically.

### 8. Charity Majors: economics, shared understanding, and code as a cache

**Source:** Charity Majors, “AI demands more engineering discipline. Not less,” 2026. https://charity.wtf/p/ai-demands-more-engineering-discipline

Majors frames the change as economics: code generation became effectively cheap and instant, while the real product of a good software team remains shared understanding. She cites the idea that durable code historically bundled intent, expectations, edge cases, tests, comments, and tribal knowledge; when regeneration is cheap, code may become a disposable “materialized view of understanding.”

This is useful for separating harmless style from harmful slop: code can be regenerated only if requirements, invariants, failure boundaries, and evaluation are explicit elsewhere. If not, deleting/replacing the code destroys the only repository of knowledge.

**Signal:** anti-slop is not necessarily “preserve every line”; it is preserving/elevating intent, invariants, observability, and verification.

**Limitations:** essay and forward-looking argument, not an empirical estimate.

### 9. Open-source maintainer experience: abstraction that “technically works” but raises complexity

**Source:** Aleks Volochnev, maintainer, “AI is burning out the people who keep open source alive,” CodeRabbit, Feb. 28, 2026. https://www.coderabbit.ai/blog/ai-is-burning-out-the-people-who-keep-open-source-alive

Volochnev says maintainers see PRs that add a brand-new abstraction layer for a five-line change, with interfaces/helpers/config flags. Tests and CI may be green, yet reviewers must reconstruct rationale and check for conflicts with long-standing architecture. He reports error handling that catches/logs every exception and thereby masks failures expected by downstream code. Much project knowledge is implicit in old issues, social conventions, and historical trade-offs.

He explicitly says the shift is volume: writing got easier while reviewing became much harder. His own proposed product solution is commercially interested, so use the observations rather than treating the vendor’s mitigation claims as neutral evidence.

**Signal:** “technically correct” can still be harmful when it violates implicit contracts, creates unnecessary abstraction, or makes intent expensive to recover.

**Limitations:** vendor blog, anecdotal observations, and marketing incentives. Its claim that AI PRs have 1.7x more issues is vendor research and should not be generalized without methodology.

### 10. GitHub Community maintainer discussion: judge merit, not AI detection

**Source:** GitHub Community Discussion #185387, “Exploring Solutions to Tackle Low-Quality Contributions on GitHub,” Jan. 27, 2026, 121 comments/297 replies. https://github.com/orgs/community/discussions/185387

GitHub’s community post reports maintainers spending substantial time on contributions that fail project guidelines, are abandoned, or are AI-generated; proposed directions include granular PR permissions, deletion, triage against CONTRIBUTING.md, and AI-assistance transparency.

Important counterpoint in the discussion:

- GitHub maintainer Camilla Moraes asks whether AI-generated code can be high-quality and genuinely solve the problem, warning that detection might close constructive contributions.
- Paul Newton: “AI-detection is a backwards approach to a human problem filled with false positives”; the test that matters is whether code works and the contributor is allowed to contribute it.
- user “who”: “Judge work on its merits and its logic, no matter if the source is human, AI, or a combination thereof.”

**Signal:** provenance can be useful for accountability/transparency, but an anti-slop system should not use “AI detected” as a quality verdict. Evaluate behavior, architecture, tests, scope, and explainability.

**Limitations:** discussion contains mixed-quality comments, spam/off-topic material, and self-reported estimates (e.g., “1 out of 10” legitimate AI PRs) that should not be treated as prevalence.

### 11. X / maintainer incident discovery: Godot

**Sources:** Game Developer’s X post linking Godot maintainers’ complaint, Feb. 17, 2026: https://x.com/gamedevdotcom/status/2023742289814974555 . Related reporting: https://www.devclass.com/ai-ml/2026/02/19/github-itself-to-blame-for-ai-slop-prs-say-devs/4091420

The X post summarizes a Godot co-founder/maintainer saying AI-slop PRs had become overwhelming and “I don’t know how long we can keep it up.” Reporting describes low-quality AI PRs as draining/demoralizing and notes GitHub controls such as limiting PRs to collaborators or disabling them.

**Signal:** at maintainer scale, the harm is not only defective code; it is queue exhaustion, demoralization, and loss of capacity to review genuinely valuable contributions.

**Limitations:** X search result is secondary/discovery-level and engagement counts are not evidence of correctness. Use the linked maintainer/reporting sources for the claim, not the post’s reach.

### 12. cURL security reports: incentive-driven “slop” outside code

**Sources:** Daniel Stenberg/RedMonk interview: https://redmonk.com/videos/daniel-stenberg-ai-onslop ; The New Stack report: https://thenewstack.io/curls-daniel-stenberg-ai-is-ddosing-open-source-and-fixing-its-bugs ; Stenberg’s LinkedIn statement: https://www.linkedin.com/posts/danielstenberg_hackerone-curl-activity-7324820893862363136-glb1

Stenberg describes long, confident, fabricated vulnerability reports produced by prompting AI to “find a security problem,” then submitting the result with little verification. One report included debugger output referring to a function that did not exist. He says reporters imposed hours of work per instance and called it abuse; cURL required reporters to disclose AI use and banned reports deemed AI slop.

**Signal:** incentives matter. A bounty or profile/velocity reward can turn cheap generation into mass low-signal submissions. The anti-slop test is not prose style but reproducibility, verification, and whether the submitter can answer detailed follow-up questions.

**Limitations:** incident reporting is based on maintainer testimony and journalistic interviews; not a random sample of vulnerability reports.

## Recurring causes and incentives

1. **Asymmetric economics:** generation is instant/cheap; review, context reconstruction, maintenance, and incident response are not.
2. **Output/velocity metrics:** the submitting team or employee receives credit for PR count/feature completeness; reviewers absorb downstream cost. Mandated adoption can amplify volume regardless of need.
3. **Weakly specified work:** broad tickets and missing invariants let models—and humans—fill gaps with assumptions.
4. **Training-data/style priors:** models reproduce common boilerplate, enterprise patterns, duplicated solutions, and plausible but irrelevant abstractions.
5. **Tool affordances:** autocomplete/agents make it easy to add layers, files, defensive checks, comments, or tests without a proportional understanding of the architecture.
6. **Review bottleneck:** code generation accelerates the non-bottleneck while human judgment remains scarce; total throughput can fall.
7. **Accountability diffusion:** “the AI wrote it,” green CI, or generated explanations become substitutes for author ownership.
8. **Historical human causes:** cargo-cult design patterns, premature abstraction, speculative future-proofing, copy/paste, oversized PRs, weak tests, and premature optimization existed before AI. AI makes them cheaper, more voluminous, and harder to attribute.

## Candidate evidence-based taxonomy for downstream design

- **Benign style variance:** local idiom disagreement; explainable, bounded, reversible, no invariant or review-cost issue.
- **Complexity slop:** needless layers, wrappers, factories/builders, duplicate helpers, configuration flags, comments/docs that restate code, or abstractions without a demonstrated second use.
- **Context slop:** wrong module/location, ignores existing patterns, invented APIs/services/dependencies, architecture drift.
- **Verification slop:** happy-path-only or tautological tests; tests weakened/mocked to pass; skipped/red tests; assertions that cannot fail; missing failure/security/edge cases.
- **Semantic/safety slop:** swallowed errors, authz/authn bypasses, unsafe defaults, data integrity bugs, resource leaks, security vulnerabilities, or behavior inconsistent with downstream contracts.
- **Accountability slop:** author cannot explain intent/operation/trade-offs, cannot identify changed behavior, or treats review as someone else’s responsibility.
- **Process/queue slop:** oversized/unscoped PRs, unrelated changes, mass generated docs/comments, or repeated low-signal submissions that externalize cost to maintainers.

## Confidence and interpretation

- **High confidence recurring pattern:** review burden, oversized diffs, context mismatch, accountability/comprehension gaps, and “green tests can still hide bad code” recur across the arXiv qualitative synthesis, experienced practitioner threads, HN, Thoughtworks, and maintainer accounts.
- **Moderate confidence:** specific mechanisms such as model training-data bias, test subversion, and complexity inflation are well illustrated but depend on stack/model/workflow.
- **Low confidence / do not generalize:** claimed prevalence, exact defect multipliers, “most AI PRs are bad,” and claims about industry-wide productivity. The sources are self-selected, vendor-affiliated, or anecdotal.
- **Key design caution:** do not equate AI provenance with slop. Several practitioner sources explicitly argue that high-quality AI-assisted work exists and should be judged by its logic, behavior, tests, architecture, scope, and author ownership.
