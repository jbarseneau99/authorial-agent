# Procedure fidelity correction

This increment corrects identifiable departures from the recorded construction,
expression, checking and local-repair procedure. It does not claim recovery of
the exact historical prompts. `procedures/v0.1.json` and `v0.2.json` identify
themselves as reconstructions; `v0.3.json` identifies a proposed repair. The
approved P006 expression is preserved, but its original prompt and complete
execution trace were not recovered. Historical detector and author observations
remain distinct from current code execution.

## Existing requirements and corrections

| Requirement | Correction |
| --- | --- |
| P03-01: encode claims without source sentence skeletons | Construction instructions require semantic notes retaining relations, conditions and scope. Construction review explicitly checks this separation. |
| DS-07.01 and the resolve operation: applicable voice rules across four layers | Construction considers every materially applicable dimension. Criteria must test the selected authorial operation, not just repeat subject content. |
| Review the relevance of the resolved voice evidence | Construction review receives the complete already-bound candidate catalog once, allowing it to identify omissions. Expression still receives only the selected evidence. |
| DS-08.01: expression realizes the encoded structure | Claim notes establish meaning, not grammatical templates. The expression provider remains responsible for realizing and repairing prose. |
| Author instruction: include exemplars as examples and ask for prose structured like them | The actual expression request pairs each act's application with the selected authentic example text. The prompt explicitly asks the writer to follow the demonstrated structure. The complete approved passage remains a separately labeled worked written example. |
| DS-10.01: criterion, observation and deficiency | Checker feedback specifies an editing action, preserved content and acceptance condition. Any suggested wording remains local to the diagnosed span; it must not become a whole-paragraph substitute. |
| DS-10.02: route by deficiency type | In the resolved profile, a definite expression defect can reach local editing from any authorial layer. Uncertainty and evidence limitations require review; construction defects require construction reopening. |

The resolved repair gate checks the current assessment and every reopening
ticket. All nonpassing checks must be definite expression defects before local
editing can run. A mixed assessment cannot bypass a construction or evidence
gate. Legacy profiles retain their original routing. Unaffected sentences and
sentence-to-act mappings remain protected; a broader change requires reopening.

The same `Execution`, `Faculty`, `Expression`, `Checking`, `Editing` and
`ParagraphLoop` owners remain. No new scheduler, authorial rule, ledger promotion,
detector threshold or approval transition is introduced.

## Evidence and limitations

Synthetic regression cases cover the observed cross-layer repair failure and
stronger gates. A separate data-flow case verifies that construction review can
inspect an unselected candidate without adding it to expression inputs.

Prompt instructions are not mechanical proof of good abstraction, adequate voice
selection, meaningful criteria or faithful language. Live model findings and the
author's assessment remain necessary. Successful fixture tests do not demonstrate
writing quality or detector performance.

Automatic construction repair, author-review resolution, flexible sentence
boundaries during local editing, whole-chapter semantic checking and the external
canonical-loop interface remain incomplete. The current fixed sentence count is
a conservative implementation restriction, not a recovered historical voice rule.

Private source passages, actual model requests and live results remain in their
versioned experiment evidence rather than routine public source publication.

