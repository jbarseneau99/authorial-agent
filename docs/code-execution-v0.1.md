# Code execution increment v0.1

Status: implementation and fixture verification. Not a successful live writing experiment or a recovered historical prompt sequence.

This increment implements the author's code-only direction recorded in `decisions/code-only-loop-execution-v0.1.json`. It preserves the existing procedure files, voice ledgers, historical runs and four-layer architecture. `Execution` remains the coordinator; no second lifecycle engine was introduced. The external platform's canonical interface remains unrecovered and unintegrated.

## What changed

| Requirement or finding | Change | Owning file |
| --- | --- | --- |
| BR/DS-05.01: construction precedes expression | Expression rejects unclosed, stale or unwitnessed construction. Reviews bind conceptual, epistemic and rhetorical-plan findings to the exact construction revision. | `src/construction.py`, orchestrated by `src/faculty.py` |
| BR/DS-07.02: authentic exemplar evidence | Selected rule grounding is expanded to actual exemplar and original-source passages. Original spoken excerpts must match the linked source. Construction, expression and checking receive the same frozen selection. | `src/construction.py` |
| BR/DS-08.02 and CE-03: exact execution evidence | Bind procedure, ledger, sources, code, provider configuration and prompt templates. Record each resolved request before invocation, the response, outcome and binding identity. | `src/run_binding.py`, `src/providers.py` |
| BR/DS-09.01: distinguish checks, closure and authority | A model's passing review does not close construction. Explicit trusted-host author closure is required by this increment. Passing expression checks remains separate from final author approval. | `src/execution.py`, `src/construction.py` |
| DS-10.02 and CE-02: targeted repair | Linguistic repair receives the exact prior draft and findings, affected sentence/act identities, and the existing frozen construction and voice context. | `src/editing.py` |
| BR/DS-12.02: preserve versions | Append execution checkpoints and provider events; preserve old drafts, assessments and repair inputs. Budgets and errors leave explicit unresolved states. | `src/execution.py`, `src/run_binding.py`, `src/editing.py` |

## Rules and exemplars in the prompts

The corpus holds conceptual, epistemic, rhetorical and linguistic rules, with their recorded status and grounding. The caller selects a ledger and, optionally, an explicit rule set. Source-linked spoken exemplars are expanded into the model input. Candidate rules remain advisory; importing or selecting them does not constitute author approval.

1. **Construction:** the prompt receives author intent, supplied or retrieved evidence, selected rules, authentic excerpts and source lineage. It returns claims and ordered intellectual acts. Rhetorical planning occurs here.
2. **Construction review:** the reviewer receives that structure and the same frozen voice evidence. It returns conceptual, epistemic and rhetorical-plan findings. Code verifies review shape, revision freshness and closure authority.
3. **Expression:** the prompt receives closed construction, acts, selected rules and actual exemplar passages. It returns prose with sentence-to-act references, or a request to reopen construction.
4. **Checking:** the reviewer receives prose, the construction snapshot and the same voice evidence. It returns one finding for each of the four layers. Code routes failures.
5. **Editing:** the expression prompt also receives the previous exact draft and actual findings. The subsequent result is checked again. Previous drafts remain intact.

Per-act relevance selection is **not implemented**. The input explicitly marks this gap. Supplying the full selected rule set is not evidence that the most appropriate rule or exemplar has been selected for each act.

`docs/render_procedure_diagram.py` renders the prompt/data-flow diagram from source. The diagram describes the target flow; the limitations below describe actual runtime coverage.

## Loop ownership

| Loop | Owner | Current coverage |
| --- | --- | --- |
| Execution and final validation | `src/execution.py` | Versioned checkpoints, binding checks, closure gate, budget, explicit approval; one coordinator |
| Construction | `src/faculty.py` | Research input, grounded voice context, proposal persistence, review and closure calls |
| Expression | `src/expression.py` | Closed-plan gate, rule/exemplar input, sentence-to-act mapping, reopening request |
| Four-layer checking | `src/checking.py` | Revision-bound findings and repair tickets |
| Editing | `src/editing.py` | Feedback-bound linguistic repair and preserved attempts |
| Research | `src/research_loop.py` | Supplied evidence and operator-directed bilateral retrieval; no claim of evidence sufficiency |
| Learning | `src/learning.py` | Existing elected sessions and proposals; approved learning snapshots are not integrated into generation |
| Composition and paragraph iteration | Unimplemented | Flat act ordering remains in construction; no autonomous chapter/paragraph loop is claimed |

`src/construction.py` and `src/run_binding.py` are shared checks and persistence helpers. They do not own competing schedulers.

## States and authority

A normal start persists a construction and its review, then reports `awaiting_construction_closure`. A failed review reports `construction_review_required`. Neither state calls the writer. Explicit closure moves the run to `ready`; `resume` performs expression and four-layer checking. Passing checks lead to `awaiting_approval`. Only explicit author approval yields `closed`.

Linguistic failures can enter the editing owner with explicit author authorization. Epistemic/rhetorical failures remain routed to construction; conceptual or uncertain findings remain routed to author review. Those routes are recorded, but autonomous intellectual repair is not implemented. Exhausted budgets do not become approval or closure.

The literal `actor="author"` parameter is a trusted-host assertion, not an authentication system. The platform's canonical closure authority and identity interface still need integration. No model is authorized to supply that identity for itself. This increment does not claim that its closure behavior is an exact reproduction of a historical successful manual run.

## Remaining implementation work

- Full typed conceptual and epistemic objects, including warrants, objections, qualifications and sufficiency judgments. Current claims still carry `verified: false`; schema-valid evidence links do not prove truth.
- Per-act applicability and exemplar selection, with explicit gaps and selection evidence.
- Separate composition placement and paragraph/chapter orchestration.
- Research and construction repair driven by diagnosed findings.
- Actual platform canonical-loop and authenticated authority integration.
- Approved learning snapshot selection and additional ledger formats.
- Live end-to-end evaluation, author voice assessment and separately recorded detector observations.

The unchanged historical procedure files retain their recorded `reconstructed_unvalidated`, `unvalidated reconstruction`, or `proposed; untested` status. Recording a procedure hash does not establish that every requirement in that procedure has been implemented. This increment must not be described as a proven chapter-writing baseline.

## Verification

Run `python3 -m unittest discover -v` from `src`. Tests use deterministic fixtures and mocked provider transports. The committed verification record states the command, actual result and evidence category. It is not a live-model or authorial-voice result.

Run data can contain manuscript and voice evidence. Keep it separate from source-code publication; committing the implementation does not publish a run database or its prompt contents. Credentials are supplied through named environment variables and are excluded from provider evidence.
