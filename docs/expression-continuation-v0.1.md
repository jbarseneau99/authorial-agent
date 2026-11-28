# A new bound continuation of diagnosed expression repair

RECOVERY_002 retained a current closed construction and an exact paragraph with
a diagnosed linguistic expression defect when its committed three-attempt budget
was exhausted. Changing that run's budget would invalidate its binding. The
author subsequently authorized continued code execution. This increment permits
a new registered run to continue the existing repair without rewriting the old
run, regenerating its construction, or manually changing its prose.

## Ownership and limits

`src/execution.py` remains the coordinator. Its `continue_expression` entry checks
the new committed binding and imports one exhausted paragraph. The existing
`src/paragraph_loop.py` owner prepares the next ordinary editing attempt;
`src/editing.py`, `src/checking.py` and `src/pangram_check.py` perform their existing
operations on subsequent advances. `src/continuation.py` is an input-preservation
helper, not a scheduler or an alternative writing procedure.

The entry accepts only one closed paragraph with a current failed assessment
whose complete diagnoses permit local expression repair. It rejects stale work,
construction/evidence failures, pending reviews, detector-only failures and
unchanged or smaller budgets. The source paragraph's identity, exact text,
sentence-to-act mappings, construction, closure witness and all previous attempts
are retained. A total budget of six following three exhausted attempts permits
attempts four through six; it does not reset the counter.

The source SQLite database is opened read-only and copied through SQLite's backup
API into a new, non-existing destination. The registration binds the original
database hash, execution revision, binding, closed construction, paragraph
checkpoint, assessment and exact-text hash. A new append-only snapshot witness
records that import. A changed source or an existing destination is rejected.
Use a settled source database without an uncheckpointed WAL.

The new binding may change its code commit and total attempt budget. Configuration
changes are limited to that budget, its typed `continuation` reference, and
registration/authorization metadata (`id`, `version`, `authorization`,
`recovery_authorization`, `comparison`, `registration`). Author intent, model and
provider settings, prompt templates, source contents, procedure/addendum contents,
ledger, examples, presentation and paragraph grouping must remain the same. The
new execution records the author delegation; final passage approval remains
pending.

The source database and its original execution/checkpoints are never edited.
Within the copied database, normal editing may authorize the imported reopening
ticket before producing a new expression and assessment. It does not overwrite
the old draft, construction, binding, execution or historical attempt records.
Imported detector observations do not become repair instructions or substitute
for a current four-layer check and a new exact-text scan.

## Registration and execution

First inspect the source without invoking providers:

```bash
python src/run_agent.py continuation-reference \
  --database /absolute/path/to/parent/run.sqlite \
  --execution PARENT_EXECUTION_ID \
  --output /absolute/path/to/continuation-reference.json
```

Copy the parent's configuration, preserve its writing inputs, set the new run
identity and authorization metadata, increase `max_attempts`, and place that
reference object under `continuation`. Commit the implementation and the new
configuration before initializing a live continuation.

```bash
python src/run_agent.py continue-expression \
  --config experiments/NEW_RUN/configuration-v0.1.json \
  --source-database /absolute/path/to/parent/run.sqlite \
  --database /absolute/path/to/new/run.sqlite \
  --actor author --live \
  --output /absolute/path/to/new/prepared.json
```

This command prepares the new execution without calling a model or detector.
Read its new `execution.id` from the saved report. Advance that exact execution
with the existing `resume` command, or use the recovery driver under its recorded
delegation:

```bash
python verification/run_recovery_trial.py \
  --config experiments/NEW_RUN/configuration-v0.1.json \
  --output /absolute/path/to/new \
  --execution NEW_EXECUTION_ID
```

The driver requires an explicit execution ID when a database retains a parent
execution. It does not choose the newest row implicitly. An ordinary `start`
cannot silently ignore a registered continuation.

## Verification and interpretation

`src/test_expression_continuation.py` uses deterministic provider transports to
verify the exact prior paragraph and diagnosis reach the journaled repair under
the new binding, all four layers are checked again, unaffected text is preserved,
the parent database remains byte-identical, inherited attempts count toward the
new limit, and unauthorized or incompatible continuations are rejected. These
are implementation tests; they do not establish writing quality, author approval,
detector performance or repeatability. Exact before/after live observations must
be retained separately against their paragraph hashes.
