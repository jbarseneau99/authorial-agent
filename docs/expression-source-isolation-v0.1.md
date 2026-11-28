# Subject-source isolation for expression v0.1

Procedure `procedures/v0.2.json` excludes original target prose as a rewrite
prompt. Previously, construction's graph traversal carried the complete subject
source body into `Expression.context`, so it also reached the writer through
`nodes`, including nested prior-draft inputs during linguistic repair.

`Expression.writer_context` now creates a separate writer view immediately before
each expression provider call. Subject evidence with `origin: retrieved_unverified`
keeps its graph identity, revision, edges, source reference and metadata; its raw
`text` is replaced with a SHA-256 reference and an explicit visibility marker.
The same projection applies to repeated source nodes in repair history. Constructed
claims and acts remain available, and selected voice evidence, authentic spoken
excerpts, provenance and recorded rule authority remain unchanged.

The original graph, construction review, closure witness, stored expression
context and editing evidence are not altered. `Checking` continues to receive
original subject evidence for fidelity assessment. Freshness checks still compare
the complete source-bound construction. A source revision therefore invalidates
closure even though the writer received only its reference. `ProviderJournal`
records the exact projected request; the full stored `expression_input` remains
the review/freshness context, not a claim that the raw source was sent to the writer.

This changes expression input visibility only. It does not change voice rules,
model selection, the ontology, closure authority, paragraph gates or repair routes.
It is not a word-overlap filter: legitimate constructed claims, exact authorial
exemplars and prior generated expression are retained. It does not establish voice
quality, source truth or successful live generation.

Targeted regression coverage in `src/test_expression_source_isolation.py` checks
serialized initial and repair inputs, retention of exact voice evidence and
constructed content, preservation of original evidence for the independent
four-layer checker, and invalidation when the withheld source changes. These tests
use synthetic fixtures and make no external calls.
