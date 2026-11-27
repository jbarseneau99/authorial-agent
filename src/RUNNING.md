# Running the paragraph-gated code

Python 3.10+ and `openpyxl` are required. Diagram rendering additionally uses `matplotlib`. Run fixture verification from `src`:

```sh
python3 -m unittest discover -v
```

Current coverage is documented in [paragraph-pangram-v0.1.md](../docs/paragraph-pangram-v0.1.md). The earlier [code-execution-v0.1.md](../docs/code-execution-v0.1.md) remains a historical record of its increment. Whole-chapter semantic checking, the full epistemic schema, per-act relevance selection, intellectual repair and the external canonical-loop interface remain incomplete.

## Prepare the exact run configuration

Use the real Git checkout containing this runtime. Commit the code, selected base procedure, paragraph addendum and run configuration before a live start. The runtime binds their identities and the actual Git HEAD; changed tracked files, code, templates or declared inputs block progression.

Prepare source artifacts as UTF-8 `.txt` or `.md` files. PDF extraction is a separate step; the runner does not silently interpret binary sources. Keep private source files outside public source publication when appropriate; their exact paths and bytes are bound for the run. Model credentials and the Pangram API key belong in the named local environment variables, never in configuration JSON or Git.

Print the current prompt-template digest from the repository root:

```sh
python3 -c 'import sys; sys.path.insert(0,"src"); from providers import JSONModel; print(JSONModel.templates_digest())'
```

The following is a configuration **shape**, with deliberate placeholders. It is not a runnable experiment or a statement of model availability. Select the actual base procedure, providers, sources and detector version, then commit the completed configuration.

```json
{
  "mode": "live",
  "intent": "The exact author intent for this run",
  "procedure": "procedures/v0.2.json",
  "procedure_addenda": ["procedures/addenda/paragraph-pangram-v0.1.json"],
  "paragraph_mode": "pangram-gated-v1",
  "ledger": "src/Authorial_Voice_Ledger_v0.4.xlsx",
  "sources": ["/absolute/path/to/prepared-source.txt"],
  "providers": {
    "construction": {
      "model": "selected-model-id",
      "endpoint": "https://provider.example.invalid/v1/chat/completions",
      "key_env": "AGENT_API_KEY"
    },
    "expression": {
      "model": "selected-model-id",
      "endpoint": "https://provider.example.invalid/v1/chat/completions",
      "key_env": "AGENT_API_KEY"
    },
    "checking": {
      "model": "selected-model-id",
      "endpoint": "https://provider.example.invalid/v1/chat/completions",
      "key_env": "AGENT_API_KEY"
    }
  },
  "prompt_templates_sha256": "replace-with-the-printed-digest",
  "pangram": {
    "endpoint": "https://text.external-api.pangram.com",
    "model": "pangram-4",
    "expected_version": "replace-with-the-confirmed-version",
    "key_env": "PANGRAM_API_KEY",
    "public_dashboard_link": false,
    "policy": "all-human-v1",
    "minimum_words": 50
  },
  "max_attempts": 3
}
```

`expected_version` must be an exact numeric version string, such as the version confirmed for the intended service/account. The code does not assume `4.1` is available merely because `pangram-4` was selected. The official API quickstart currently uses `4.0` in its example response. An unexpected returned version pauses the run with an error. See the [official API documentation](https://docs.pangram.com/quickstart-rest).

The service can normalize returned text and update minor versions within a model series. The strict gate pauses if returned text differs from the original paragraph; normalization mapping is not implemented. See the [API reference](https://docs.pangram.com/api-reference/ai-detection).

`public_dashboard_link` must be false and the implemented gate policy is `all-human-v1`. That policy accepts only zero AI/AI-assisted fractions and wholly human-labeled windows with consistent coverage and counts. `minimum_words` must be at least 50, following the [model's published input minimum](https://www.pangram.com/research/model-card/pangram-4). A shorter paragraph stops as unscorable; it is not padded or combined with another paragraph.

Zero/one fraction comparisons allow only floating-point residue within `sys.float_info.epsilon`, with zero relative tolerance. Every window must still be Human and both AI/AI-assisted segment counts must still be zero. This [compatibility correction](../docs/pangram-api-compatibility-v0.1.md) was prompted by a live Human Written result containing an AI fraction of about `6.6e-40`; raw values are retained.

Optional configuration fields:

| Field | Meaning |
| --- | --- |
| `paragraph_groups` | Lists of zero-based closed-plan act indices. Groups must be nonempty and cover every act exactly once in order. Omission currently means one act per paragraph, explicitly labeled an unvalidated default. |
| `selected_rule_ids` | Imported graph rule IDs from the selected ledger. Omission selects all candidate rules in that ledger; this does not perform per-act relevance selection or approve candidates. |
| `research` | An object containing both `support` and `challenge` query strings. Retrieval remains distinct from evidence sufficiency. |
| `max_attempts` | Positive per-paragraph expression/repair budget; default 3. Detector polls do not consume another expression attempt. |

The committed configuration contains the exact intent; there is no separate mutable CLI intent override. The runtime freezes the entire configuration and hashes the base procedure, addendum, ledger and sources. The containing commit is recorded separately, avoiding a self-referential commit field. Paths must continue to resolve to the bound bytes on resume.

## Start construction and inspect it

From the repository root:

```sh
python3 src/run_agent.py start --live --config path/to/run-config.json --database /path/to/run.sqlite --output /path/to/start-report.json
```

Live start requires configured Pangram credentials and the declared paragraph gate. Its preflight is local: it checks binding, configuration and credential presence, not live API entitlement. It then constructs and reviews the argument. Passing construction checks leave the run at `awaiting_construction_closure`, before prose generation. Failed or uncertain findings remain unresolved. Model judgments do not grant closure authority.

Inspect evidence without creating providers or making network calls:

```sh
python3 src/run_agent.py inspect --database /path/to/run.sqlite --execution EXECUTION_ID --output /path/to/inspection-v1.json
```

The read-only report includes the stored execution state, current freshness state, active loop/owner, configuration and bindings, construction/review/closure, paragraph checkpoints, detector scans, and exact model-provider invocations. Reports use exclusive file creation; choose a new output filename for each version.

An authorized host may record the author's construction closure:

```sh
python3 src/run_agent.py close-construction --database /path/to/run.sqlite --execution EXECUTION_ID --actor author
```

This closes the current construction and records the paragraph grouping. It does not call the writer. `--actor author` is a trusted-host assertion, not identity authentication; it must reflect actual authority. A grouping inconsistent with the constructed acts remains unresolved.

## Generate, check and poll one paragraph

```sh
python3 src/run_agent.py resume --live --database /path/to/run.sqlite --execution EXECUTION_ID --output /path/to/paragraph-step-v1.json
```

A ready paragraph step checks detector availability locally, generates only the current paragraph, runs all four checks and submits that exact paragraph if those checks pass. Each detector advance makes at most one HTTP request. A resume of a pending detector task polls the existing task; it does not invoke the writer or submit the paragraph again.

| Execution state | Meaning and next action |
| --- | --- |
| `ready` / `ready_for_next_paragraph` | A resume may generate the current paragraph. All preceding paragraphs must still have passing evidence. |
| `suspended_detector_pending` | Resume polls the saved task. It cannot generate the next paragraph. An interrupted submission without a recorded response stays unresolved rather than being resubmitted. |
| `suspended_detector_flagged` | Review the preserved paragraph and result. Detector flags do not trigger automatic rewriting. |
| `suspended_detector_unscorable` | The paragraph is below the configured detector minimum. Progression stops; no padding or aggregation is performed. |
| `suspended_detector_blocked` / `suspended_detector_error` | Inspect credential/configuration/transport or result evidence. There is no automatic resubmission after an uncertain or failed request. |
| `suspended_reopen` | Inspect the diagnosed layer. Only the implemented linguistic repair route may resume as an expression repair. |
| `budget_exhausted` / `stale` | Stop; unresolved or changed evidence does not confer closure. |
| `awaiting_approval` | Every paragraph has current four-layer and detector passes and the exact text is assembled. Whole-chapter semantic checking remains pending. |

A detector pass changes the checkpoint to `ready_for_next_paragraph`; a later resume generates the next paragraph. This makes the progression visible and prevents a single unchecked draft of the remainder of the chapter.

## Repair and author validation

An explicitly authorized linguistic repair uses the existing editing owner:

```sh
python3 src/run_agent.py resume --live --database /path/to/run.sqlite --execution EXECUTION_ID --actor author --output /path/to/repair-v1.json
```

The repair receives the prior exact paragraph, its actual four-layer findings and affected sentence/act IDs, while preserving scope and valid earlier paragraphs. It receives no detector score as a writing instruction. It is rechecked and rescanned. Construction defects and conceptual/uncertain routes cannot be bypassed through linguistic editing. The per-paragraph attempt budget limits generation/repair attempts and does not grant closure.

Final author validation remains separate:

```sh
python3 src/run_agent.py approve --database /path/to/run.sqlite --execution EXECUTION_ID --actor author --output /path/to/approval-v1.json
```

This requires all paragraphs and their assessments/scans to remain current, plus unchanged construction closure and exact assembled text. The implementation can record author approval, but **it still records `chapter_semantic_check: pending`**. No whole-chapter semantic checker is implemented, and approval must not be described as a machine-verified chapter-level pass.

## Evidence and evaluation

Model requests and detector requests are saved before invocation. Responses, exact prompts, hashes, task IDs, returned detector versions and unresolved results remain connected to their run. Changed input or provider conditions block use of earlier evidence. Credential headers/values are excluded; echoed credentials cause response rejection.

`evaluate.py` prepares separate case folders and review records. `--live` also requires `--config-directory` containing one committed, paragraph-gated configuration per case and preflights every case before a subprocess starts. Its live action starts construction only; closure, paragraph steps and author validation remain separate.

The initial fixture verification remains in [verification/paragraph-pangram-v0.1.json](../verification/paragraph-pangram-v0.1.json); verification after the numerical correction is recorded separately in [verification/paragraph-pangram-v0.2.json](../verification/paragraph-pangram-v0.2.json). A subsequent [live API check](../verification/pangram-api-probe-v0.1.json) used one unchanged historical paragraph and confirmed credential access and result handling. It did not run construction, expression or authorial checking. Production manuscript-quality validation remains outstanding. Keep run databases and prompt reports separate from routine code publication because they may contain private manuscripts and authorial evidence.
