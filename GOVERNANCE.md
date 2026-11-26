# Repository governance

Approved by the author on 2026-11-26.

GitHub is the authoritative repository for requirements, design, code, procedures, voice ledgers and experiments. The agent has delegated authority to create and modify files, run tests, commit changes and verify commits within approved requirements and architecture, without repeated author approval. Platform permission prompts remain applicable.

Changes to approved requirements, architectural boundaries or authorial rules require explicit author approval before adoption. Uncertain authorization must be escalated. Preserve historical versions and evidence; do not force-push or delete history. Never commit credentials.

Every change must identify its requirement, design decision or experimental finding, affected artifacts, verification evidence and unresolved limitations. Commit the procedure and configuration before starting an experiment; record exact inputs, prompts, intermediate outputs, model, ledger revision, author judgment and detector observations against that commit. Do not treat detector results as author approval.

At the start of each work session, inspect repository state and relevant approved artifacts. Before declaring completion, verify the remote commit and report tests actually run, failures and outstanding gaps. Never claim an unverified transfer or execution. Keep original binary artifacts and machine-readable representations where possible; text exports alone are not byte-identical archives.

Repository is currently public by author decision. Do not broaden access or publish credentials. Original binary migration remains open until remote presence and checksums are verified.
