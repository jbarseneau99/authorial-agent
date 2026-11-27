# Authorial Agent procedure

The Authorial Agent constructs an intellectual argument before expressing it in the author's voice. Its four layers are conceptual, epistemic, rhetorical and linguistic. Rhetorical act purpose and order are established during construction; expression realizes those acts; checking examines all four layers.

## Current increment: one paragraph, then its checks

The author directed that Pangram run after each paragraph so a failed paragraph stops progression before the rest of the chapter is generated. The code now supports that sequence through the existing `Execution` coordinator:

1. Bind the selected procedure, its paragraph addendum, code, ledger, sources, providers and exact prompt templates.
2. Construct and review the argument; require current, explicit construction closure.
3. Generate one scoped paragraph and check all four authorial layers.
4. Submit that exact checked paragraph to Pangram and preserve the result against its text hash and assessment.
5. Generate the next paragraph only after the preceding paragraph has current passing four-layer and detector results.

A detector flag pauses the run. It does not automatically trigger paraphrasing or become a new writing instruction. Author validation remains separate.

- [Paragraph gate: behavior, evidence and limitations](docs/paragraph-pangram-v0.1.md)
- [Commands and required configuration](src/RUNNING.md)
- [Current loop ownership](loops/inventory-v0.3.json)
- [Author-directed procedure addendum](procedures/addenda/paragraph-pangram-v0.1.json)
- [Verification record](verification/paragraph-pangram-v0.1.json)
- [Live API check and numerical compatibility correction](docs/pangram-api-compatibility-v0.1.md)
- [Verification after the numerical correction](verification/paragraph-pangram-v0.2.json)
- [Earlier code increment](docs/code-execution-v0.1.md)
- [Governance](GOVERNANCE.md)

This increment extends baseline commit `68d26bda0effa4e17a33c6c3ac3aca6141c93be5`. Earlier procedure versions, loop maps, voice rules and ledgers remain preserved. The separately bound addendum records the authorized change to detector timing and paragraph progression.

## Current limits

Fixture verification covers execution gates and persistence. After the initial implementation, a live API check of the unchanged 56-word opening paragraph of Prototype 006 returned Pangram 4.1 `Human Written`, one Human segment with High confidence. That check exposed and corrected a floating-point zero comparison in the adapter. The original result and both parser verdicts are preserved separately. This was an API check of existing prose; no new prose was generated and no end-to-end manuscript-quality result is claimed.

Paragraphs shorter than the configured minimum of at least 50 words stop as unscorable. The code does not lengthen or combine them to obtain a score.

A separate whole-chapter semantic check is still pending. The assembled chapter preserves `chapter_semantic_check: pending`, including when an authorized host records final author approval. Detector passes and paragraph checks do not silently complete that missing check.

The full conceptual/epistemic schema, per-act rule/exemplar relevance selection, intellectual repair, authenticated authority integration and external platform canonical-loop interface also remain unfinished. This is an implementation increment with fixture evidence, not a validated live chapter-writing baseline.

## Version and evidence policy

Procedure versions remain independent of voice-ledger versions. Original successful prompts are not fully recovered. Historical procedure files retain their declared reconstruction or untested status. Recording their identity does not establish full implementation or reproduce the earlier successful runs.

Every run must preserve the code commit, ledger identity and hash, sources, exact prompts, model configuration, intermediate outputs, author assessment and detector observations. Keep completed runs and earlier versions. Author validation and detector observations are separate evidence. Never publish credentials or private manuscripts as part of a routine code update.
