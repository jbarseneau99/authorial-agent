# Authorial Agent procedure

The Authorial Agent constructs an intellectual argument before expressing it in the author's voice. Its four layers are conceptual, epistemic, rhetorical and linguistic. Rhetorical act purpose and order are established during construction; expression realizes those acts; checking examines all four layers.

## Current procedure: paragraph checks and bounded iteration

The author directed that Pangram run after each paragraph so a failed paragraph stops progression before the rest of the chapter is generated. The code now supports that sequence through the existing `Execution` coordinator:

1. Bind the selected procedure, its paragraph addendum, code, ledger, sources, providers and exact prompt templates.
2. Construct and review the argument; require current, explicit construction closure.
3. Generate one scoped paragraph and check all four authorial layers.
4. Submit that exact checked paragraph to Pangram and preserve the result against its text hash and assessment.
5. Generate the next paragraph only after the preceding paragraph has current passing four-layer and detector results.

A detector flag pauses the run unless an explicitly authorized fresh candidate
is requested under paragraph addendum v0.2 and its committed retry policy and
budgets. That route requires current passing four-layer findings and a completed
flag on the exact text. It expresses the same closed construction again without
sending the failed prose or detector scores to the writer, then repeats review
and measurement. Diagnosed writing defects use the separate targeted-editing
route. The v0.1 addendum retains its original stop behavior. Author validation
remains separate.

- [Paragraph gate: behavior, evidence and limitations](docs/paragraph-pangram-v0.1.md)
- [Commands and required configuration](src/RUNNING.md)
- [Current loop ownership](loops/inventory-v0.6.json)
- [Current system diagram](docs/system-diagram-v0.6.md)
- [Full voice corpus in creation and review](docs/full-voice-corpus-v0.1.md)
- [Fresh expression: authorization, budgets and commands](docs/fresh-expression-retry-v0.1.md)
- [Continue a diagnosed repair under a new binding](docs/expression-continuation-v0.1.md)
- [Original paragraph addendum v0.1](procedures/addenda/paragraph-pangram-v0.1.json)
- [Optional fresh-candidate addendum v0.2](procedures/addenda/paragraph-pangram-v0.2.json)
- [Verification record](verification/paragraph-pangram-v0.1.json)
- [Live API check and numerical compatibility correction](docs/pangram-api-compatibility-v0.1.md)
- [Verification after the numerical correction](verification/paragraph-pangram-v0.2.json)
- [Earlier code increment](docs/code-execution-v0.1.md)
- [Governance](GOVERNANCE.md)

Earlier procedure versions, loop maps, voice rules and ledgers remain preserved.
Each run binds its selected addendum and configuration before execution.

## Observed live paragraph outcomes

Retained execution, assessment and exact-text scan records confirm the following
later recovery outcomes under Pangram 4.1 and the unchanged `all-human-v1` policy:

| Trial | Paragraph attempts | Four-layer review | Exact-text detector gate |
| --- | ---: | --- | --- |
| RECOVERY_006 | 5 | All four pass | Passed; human fraction 1.0 |
| RECOVERY_007 | 5 | All four pass | Passed; human fraction 1.0 |
| RECOVERY_008 | 4, including 3 inherited | All four pass | Passed; human fraction 1.0 |

RECOVERY_006 and RECOVERY_007 were fresh executions. RECOVERY_008 continued the
diagnosed repair from RECOVERY_002 under a new binding; it was not a third
independent construction. All three remain `awaiting_approval`. These are
observed successes of the paragraph procedure, not an established success rate.
Fixed-configuration repeatability remains pending, and the whole-chapter
semantic check and final author judgment remain separate.

The [current loop map](loops/inventory-v0.6.json) records the exact execution,
assessment, scan and text-hash references without including private prose.
The [initial five-trial record](docs/recovery-experiments-v0.1.md) retains its
earlier results, including unsuccessful candidates and unresolved findings.

## Current limits

Fixture verification covers execution gates and persistence. The earlier API
compatibility check used the unchanged 56-word opening paragraph of Prototype
006 and returned Pangram 4.1 `Human Written`, one Human segment with High
confidence. That check exposed and corrected a floating-point zero comparison
in the adapter. Its original result and both parser verdicts remain preserved;
it is separate from the later generated-paragraph outcomes above.

Paragraphs shorter than the configured minimum of at least 50 words stop as unscorable. The code does not lengthen or combine them to obtain a score.

A separate whole-chapter semantic check is still pending. The assembled chapter preserves `chapter_semantic_check: pending`, including when an authorized host records final author approval. Detector passes and paragraph checks do not silently complete that missing check.

Per-act rule and exemplar selection is implemented but remains model-judged.
The full conceptual/epistemic schema, general intellectual repair, authenticated
authority integration and external platform canonical-loop interface remain
unfinished. The observed paragraph outcomes do not establish a validated
chapter-writing baseline.

## Version and evidence policy

Procedure versions remain independent of voice-ledger versions. Original successful prompts are not fully recovered. Historical procedure files retain their declared reconstruction or untested status. Recording their identity does not establish full implementation or reproduce the earlier successful runs.

Every run must preserve the code commit, ledger identity and hash, sources, exact prompts, model configuration, intermediate outputs, author assessment and detector observations. Keep completed runs and earlier versions. Author validation and detector observations are separate evidence. Never publish credentials or private manuscripts as part of a routine code update.
