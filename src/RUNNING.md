# Running and inspecting the code-only increment

Python 3.10+ and `openpyxl` are required. Diagram rendering additionally uses `matplotlib`. Run fixture verification from `src`:

```sh
python3 -m unittest discover -v
```

This increment does not yet implement per-act relevance selection, full epistemic objects, paragraph/chapter iteration, intellectual repair, or the platform canonical-loop interface. It must not be presented as a proven historical writing procedure. See `docs/code-execution-v0.1.md` for coverage and limits.

## Prepare a declared run

Use a real Git checkout with committed code, procedure and run configuration. Live start rejects a different runtime checkout, changed tracked files, an undeclared provider, a changed bound input, or a prompt-template mismatch. Supply prepared UTF-8 `.txt` or `.md` source artifacts; PDF extraction is a separate preparation step. Keep actual model credentials in the named environment variable.

Obtain this runtime's prompt-template digest from the repository root:

```sh
python3 -c 'import sys; sys.path.insert(0,"src"); from providers import JSONModel; print(JSONModel.templates_digest())'
```

Example configuration shape below uses placeholders and is not a runnable baseline. Use the procedure revision actually selected for the experiment. Existing procedure files retain their declared reconstruction/validation status.

```json
{
  "mode": "live",
  "intent": "The exact author intent for this run",
  "procedure": "procedures/v0.2.json",
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
  "max_attempts": 3
}
```

Optional `selected_rule_ids` is a list of imported graph rule IDs from the chosen ledger. Omission currently selects all candidate rules in that ledger; it does not perform relevance selection or approve those candidates. Optional `research` must supply both `support` and `challenge` query strings. Retrieval completion is not evidence sufficiency.

The configuration contains the intent and exact paths. Commit that configuration before starting. The runtime records the actual containing Git commit separately, avoiding a self-referential commit field. Ledger and source bytes are hashed; private source artifacts need not be published to the repository. The live binding's paths must continue to resolve to those exact bytes on resume.

## Start, inspect, close, resume

From the repository root, with a prepared and committed configuration:

```sh
python3 src/run_agent.py start --live --config path/to/run-config.json --database /path/to/run.sqlite --output /path/to/start-report.json
```

Start constructs and reviews the intellectual structure. It returns an execution ID and stops before prose at `awaiting_construction_closure` when checks pass. Failed findings remain unresolved. A model pass never supplies author authority.

Inspect stored evidence without creating providers or making model calls:

```sh
python3 src/run_agent.py inspect --database /path/to/run.sqlite --execution EXECUTION_ID --output /path/to/inspection-v1.json
```

Inspection includes the active loop and owner, versioned state, bound files and templates, construction, review, closure, draft and exact provider invocations. Output files are created with exclusive creation; choose a new filename for each report.

An authorized host may record the author's construction closure:

```sh
python3 src/run_agent.py close-construction --database /path/to/run.sqlite --execution EXECUTION_ID --actor author
```

This command only moves the run to `ready`; it does not call the writer. `--actor author` is a trusted-host assertion, not identity authentication. It must reflect actual authority; the model must not grant itself this identity.

Then invoke expression and checking through code:

```sh
python3 src/run_agent.py resume --live --database /path/to/run.sqlite --execution EXECUTION_ID --output /path/to/expression-v1.json
```

A current linguistic failure can be retried through the editing owner, with explicit author authorization:

```sh
python3 src/run_agent.py resume --live --database /path/to/run.sqlite --execution EXECUTION_ID --actor author --output /path/to/repair-v1.json
```

The repair receives the previous exact draft, exact findings and affected sentence/act IDs. Construction and conceptual/uncertain routes remain explicitly unresolved; they cannot be bypassed with a linguistic retry. The configured attempt budget limits expression attempts and does not confer closure.

Final author approval is separate:

```sh
python3 src/run_agent.py approve --database /path/to/run.sqlite --execution EXECUTION_ID --actor author --output /path/to/approval-v1.json
```

This requires current passing four-layer checks and current construction closure. Detector observations are not author approval and are not injected into generation prompts.

## Evidence and evaluation

Requests are recorded before network invocation. Full responses, exact prompts and input references remain bound to the run; parse failures and truncation remain visible. Changed inputs or provider configuration block execution. Credential headers and values are excluded; echoed credential responses are rejected rather than retained.

`evaluate.py` prepares separate evaluation folders and review records. `--live` additionally requires `--config-directory` containing one committed configuration per case, and preflights all cases before any live subprocess. Its live action starts construction only; closure and author evaluation remain separate.

The code was verified using fixtures and mocked transports. No live manuscript or voice-validation result is implied by those tests. Do not publish run databases or prompt reports as routine source-code changes; they can contain private manuscripts and authorial evidence.
