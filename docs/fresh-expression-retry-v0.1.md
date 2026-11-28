# Bounded fresh expression after a completed detector flag

The author requested continued code execution until the paragraph procedure
reaches a consistent result. The authorization and fixed-configuration
confirmation criterion are recorded in
`decisions/consistency-recovery-v0.1.json`. This increment supplies the missing
bounded iteration within a paragraph; it does not establish repeatability by
itself.

The separate [paragraph addendum v0.2](../procedures/addenda/paragraph-pangram-v0.2.json)
preserves all four writing checks, the existing `all-human-v1` detector policy,
exact text/version checks, and final author approval. The earlier v0.1 addendum
and its original stop behavior remain supported.

## Explicit configuration and delegation

An enabled configuration declares all three fields before execution:

```json
{
  "procedure_addenda": ["procedures/addenda/paragraph-pangram-v0.2.json"],
  "fresh_expression_retry": "author-authorized-v1",
  "max_fresh_retries": 3,
  "max_attempts": 12
}
```

`max_attempts` remains the existing total per-paragraph writer-attempt budget.
Initial expression, diagnosed local edits, fresh candidates and failed writer
calls all consume that same total. Each fresh writer attempt also consumes one
`max_fresh_retries` allowance. Neither counter resets. The fresh allowance must
be positive and smaller than the total; selecting v0.2 without the explicit
policy and allowance enables no retry.

An interactive host requests the action with explicit author authority:

```bash
python src/run_agent.py retry-fresh-expression \
  --database /absolute/path/to/run.sqlite \
  --execution EXECUTION_ID --actor author \
  --output /absolute/path/to/fresh-preparation.json

python src/run_agent.py resume \
  --database /absolute/path/to/run.sqlite \
  --execution EXECUTION_ID --actor author --live \
  --output /absolute/path/to/fresh-attempt.json
```

The first operation only prepares `ready_for_fresh_expression`; it makes no
model or detector call. The existing recovery driver may perform both operations
under the separately recorded delegation:

```json
{
  "recovery_authorization": {
    "construction_closure_and_local_repairs": true,
    "fresh_expression_after_detector_flag": true
  }
}
```

The driver requires both this delegation and the policy. Its operational step
ceiling now scales with the committed attempt budget, planned paragraph count
and voice-repair allowance, including approximately thirty asynchronous polls
per candidate. For one paragraph, twelve total attempts and four voice repairs,
the ceiling is 412 transitions/polls. If reached, the final report explicitly
records `driver_step_limit_reached` and the exact execution ID to resume in the
same database. This ceiling does not reset, change or replace either writing
budget. Environmental and generation errors still pause for explicit inspection
and resumption.

## Entry, generation and preservation

`Execution.retry_fresh_expression` delegates to the existing `ParagraphLoop`
owner. Entry requires a current closed construction, all four passing writing
findings, and a completed flagged detector result tied to the exact current
paragraph, expression, assessment, text hash and assessment snapshot. Pending,
error, unscorable, stale or mismatched observations cannot initiate this action.
A detector result never becomes a writing diagnosis for `Editing`.

The next normal paragraph advance calls `Expression.run` with the unchanged
closed plan and act scope. It supplies the rules, exemplars and approved written
example through the existing projection. It supplies no repair context, current
failed paragraph, detector score, scan reference or retry commentary. Accepted
earlier paragraphs may remain ordinary continuity context. The failed candidate
and its observation are preserved in execution evidence outside the prompt.

Every new candidate receives a fresh four-layer assessment. A new exact-text
scan is permitted only after that assessment passes. A writing defect continues
through the existing diagnosed local-edit route. The paragraph index cannot
advance until the current candidate passes both gates; final author validation
remains separate.

The queued action freezes its source witness. A blocked preflight consumes no
attempt, preserves that witness and requires author authority when resumed.
Failed writer calls consume both budgets and remain recorded. Source freshness
is checked before and after preflight, immediately before generation, and after
the provider returns. Output from an invalidated attempt is retained but cannot
reach checking or scanning. Expected-revision claims prevent stale callers from
queuing or generating a second fresh attempt from the same checkpoint.

## Verification and interpretation

`src/test_fresh_expression_retry.py` covers explicit opt-in and v0.1 compatibility,
authority, exact scan/assessment identity, both budget limits, blocked preflight,
generation errors, source changes before and during generation, stale checkpoint
claims, and paragraph progression. Its journaled fixture verifies that initial
and fresh writing inputs are identical, including all 84 exemplar records, while
the previous failed prose and detector metadata are absent. The former draft,
assessment and scan remain inspectable.

These tests use deterministic providers and detector responses. They validate
implementation, not writing quality or detector consistency. A confirmation
batch must keep its declared configuration fixed, retain every unsuccessful
candidate and disclose the internal attempt counts. The author's requested
same-source five-run criterion and any later cross-source evidence remain
separate experiment results.
