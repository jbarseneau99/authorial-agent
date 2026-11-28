# Authorial Agent system diagram v0.5

This revision shows the complete recorded voice corpus available during creation,
followed by separate review and detector measurement. It retains the existing
loop owners, construction closure, repair routing and paragraph progression gates.

| Stage | Inputs and responsibility |
| --- | --- |
| Voice preparation | Preserve the frozen v0.4 ledger: 18 rules, 84 authentic spoken exemplars and 35 recorded source contexts. Retain exact text, provenance, recorded gaps and candidate authority. Keep the complete approved P006 passage separately labeled as generated, author-approved writing at passage scope. |
| Conceptual and epistemic construction | Make the full exemplar corpus available while forming concepts, distinctions, relationships, evidence commitments and qualifications. Select applicable grounded rule/example operations, and plan rhetorical purposes and act order. |
| Construction review and closure | Review the encoded work against its evidence and relevant examples, with complete recorded source context. Closure remains explicit and revision-bound. |
| Rhetorical and linguistic expression | Make all 84 exact excerpts, selected worked examples and the full P006 passage available to realize the closed construction. Preserve claims, scope and sentence-to-act mappings. |
| Four-layer review after creation | Review the exact paragraph conceptually, epistemically, rhetorically and linguistically. Record specific findings and repair targets. Reviewers retain complete recorded voice source context and the original subject evidence. |
| Pangram measurement | Record the detector's observation of exact text, including its hash, task and response. This measurement is separate from writing-review findings and the author's judgment. |
| Author validation | Record the author's judgment of voice and intellectual substance against the exact unchanged passage and its evidence. |

## Input presentation

The diagram describes `voice_context_scope: full_corpus_v1`. Full-corpus scope
supplies all 84 exemplars and all 35 recorded source contexts during construction
and expression. Selected worked examples remain explicit. An available exemplar
does not acquire a new rule-grounding link, and candidate rules retain their
recorded authority. Some source records are explicitly excerpts; the system
preserves their gaps rather than reconstructing missing speech.

An optional committed `voice_context_presentation: historical_compact_v1` uses
all 18 rules, all 84 exact excerpts, selected worked examples and the full P006
passage in compact generation inputs. It omits the full transcript table from
construction, binding-repair and expression prompts. Full recorded provenance
remains frozen, and construction review and paragraph checking still receive all
35 recorded source contexts. This presentation option changes no authorial rule,
criterion, approval gate or detector policy.

See [full corpus availability](full-voice-corpus-v0.1.md),
[compact presentation](historical-compact-presentation-v0.1.md), and
[construction conditioning](construction-voice-conditioning-v0.1.md).

## Measurement is separate from completion

The canonical paragraph loop requires current passing four-layer review before
its detector gate, and both gates before paragraph progression. Separately
authorized measurements can record a detector result for exact text while a
writing finding remains open; such observations do not close that finding or
advance the canonical loop. A human-classified detector result therefore does
not by itself mean that every writing check passed or that the author approved
the passage. No result is guaranteed for another paragraph or another run.

The diagram describes implemented responsibilities and data availability. It
does not report all checks complete for the recovery trials. Exact outcomes,
unresolved findings and author judgments remain in their experiment records.

Render with `docs/render_procedure_diagram.py`. The delivery filenames remain
`Authorial_Agent_Four_Layer_Procedure.png` and
`Authorial_Agent_Four_Layer_Procedure.svg`. Earlier explanations are preserved in
[v0.4](system-diagram-v0.4.md), [v0.3](system-diagram-v0.3.md), and
[v0.2](system-diagram-v0.2.md).
