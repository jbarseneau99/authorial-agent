# Authorial Agent procedure

The Authorial Agent constructs an intellectual argument before expressing it in the author's voice. Its four layers are conceptual, epistemic, rhetorical and linguistic. Rhetorical act purpose and order are established during construction; expression realizes those acts; checking examines all four layers.

## Current code increment

The code now binds declared inputs and prompts, gates expression on current construction closure, supplies grounded exemplar passages alongside selected rule records, preserves provider requests/responses and execution checkpoints, and routes linguistic repair with the actual prior draft and findings.

- [Implementation coverage and limitations](docs/code-execution-v0.1.md)
- [Commands and inspection](src/RUNNING.md)
- [Loop ownership](loops/inventory-v0.2.json)
- [Diagram renderer](docs/render_procedure_diagram.py)
- [Governance](GOVERNANCE.md)

The external platform's canonical-loop interface, full conceptual/epistemic schema, per-act relevance selection, paragraph/chapter orchestration and intellectual repair remain unfinished. This is a fixture-verified implementation increment, not a validated live chapter-writing baseline.

## Version and evidence policy

Procedure versions remain independent of voice-ledger versions. Original successful prompts are not fully recovered. The historical procedure files retain their declared reconstruction or untested status. Recording their identity does not establish full implementation or reproduce the earlier successful runs.

Every run must preserve the code commit, ledger identity and hash, sources, exact prompts, model configuration, intermediate outputs, author assessment and detector observations. Keep completed runs and earlier versions. Author validation and detector observations are separate evidence. Never publish credentials or private manuscripts as part of a routine code update.
