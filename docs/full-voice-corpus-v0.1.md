# Complete recorded voice corpus in provider inputs

The author requested that all authentic exemplars be available during creation.
The prior resolved profile traversed only selected rule-grounding edges: the
v0.4 ledger's 84 original spoken exemplars became 47 available to construction,
then only the act-selected subset reached expression. This increment changes
availability through the existing construction and expression owners.

## Explicit scope

Set `voice_context_scope` to `full_corpus_v1` in the committed run configuration,
with `execution_profile` set to `resolved-voice-v1`. Omission preserves the prior
rule-grounded construction catalog and selected-only expression projection.
The scope is checked against the execution binding and frozen in construction.

Full scope collects all original spoken exemplar rows and all Source evidence
rows from the bound imported ledger. In v0.4 this is 84 exemplars and 35 source
records, including S007, which has no derived exemplar. Exact excerpts, full
recorded source text, identities, revisions, source metadata and authority reach
construction, construction review, expression, checking and local repair.
Sources explicitly recorded as excerpts retain their gaps and modality; the
projection does not reconstruct missing speech.

Construction still selects grounded rule/example applications across the four
layers. Expression retains those selected worked examples and additionally
receives the complete corpus. `grounded_rule_ids` and `selected_for_acts` keep
availability, recorded grounding and current selection distinguishable. No
new grounding edges are created. An unlinked exemplar is available as authentic
context but cannot be falsely returned as a rule's grounding. Candidate status,
written-validation scope, closed claims and checking criteria are unchanged.

The complete corpus participates in revision checks: changing an unlinked
exemplar or a context-only source invalidates the frozen construction. Historical
detector notes remain excluded from provider projections, while full originals
remain in the graph and audit snapshots.

## Rule-layer clarity

Catalog rules expose `allowed_layers`, computed from the unchanged canonical
`Layer` field. R016 remains epistemic. Its observed use as a linguistic binding
was an invalid provider response; it is still rejected. The added field makes
the existing contract explicit without reclassifying the rule or automatically
rewriting a returned binding.

## Owners and verification

`Faculty` still owns construction; `Construction` collects and freezes evidence;
the existing voice projection helpers form provider packets. `Expression`,
`Checking`, `Editing` and `Execution` retain their existing lifecycle and gates.
Only configuration propagation and a binding comparison were added to the CLI
and coordinator. No detector policy, author-approval gate or sentence-placement
restriction changes.

`src/test_full_voice_corpus.py` uses the actual v0.4 workbook with synthetic
provider responses. Journaled-request checks compare all 84 excerpts and all
35 source records against their imported originals through construction,
expression, checking and repair. Further cases cover preserved grounding,
rejection of R016 in the wrong layer, stale unlinked evidence, legacy scope and
configuration binding. Fixture success establishes data flow and boundaries;
live writing quality, detector observations and author judgment remain separate.
