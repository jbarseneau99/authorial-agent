# Authorial Agent execution instructions

Read `GOVERNANCE.md`, the requested procedure revision, and the current loop map before work on manuscript generation.

## Author instruction — 2026-11-27

The author requires code-only execution of the writing procedure and one owning source file for each loop. The authority and scope are recorded in `decisions/code-only-loop-execution-v0.1.json`.

- Run construction, expression, checking and repair through repository code. Model reasoning and prose generation may be invoked by providers called from repository code and declared in the run configuration. Do not manually produce a chapter or its intellectual structure in chat and backfill execution records.
- Identify each loop's owning file and reuse the common canonical lifecycle. Keep shared helpers separate from loop ownership. Follow DS-09.01's requirement to adapt the existing canonical-loop interface; do not silently invent a parallel lifecycle engine.
- Before a manuscript run, bind the procedure revision, repository commit, ledger identity and hash, source revisions, provider configuration and prompt templates. Before each provider invocation, preserve its exact resolved prompt and input references. Keep the active loop, state, input/output references, findings, repair route and closure authority inspectable.
- Complete conceptual and epistemic construction before expression. Establish rhetorical act purpose and order during construction, then realize the acts rhetorically and linguistically. Check all four layers. Paragraph placement is separate from epistemic dependency.
- If required construction, evidence, inputs or closure are missing, expose the unresolved state. Do not substitute manual generation for missing implementation.
- Preserve prior runs, rules, ledgers and assessments. Treat fixture tests, live execution, author validation and detector observations as distinct evidence.

## Current implementation baseline

The historical audit is preserved in `audits/2026-11-27-code-structure/repository-map.md` and `loops/inventory-v0.1.json`. The current owner and capability map is `loops/inventory-v0.5.json`; read `docs/procedure-fidelity-v0.1.md` and `docs/voice-binding-repair-v0.1.md` for the worked-example and binding-repair increments. Verification records under `verification/` distinguish synthetic tests from separately retained live execution evidence. General intellectual repair and external canonical-loop integration remain incomplete; no passing fixture suite establishes authorial quality or final approval.
