# Optional historical compact input presentation

The recovered RUN015 writer input contained all 84 exemplar excerpts, all 18
v0.4 rules and the full approved P006 passage, without the full source-transcript
table. This option tests those presentation characteristics through the existing
code. It is not a claim to reproduce every historical instruction or model state.

Configure both fields in a new committed run:

```json
{
  "voice_context_scope": "full_corpus_v1",
  "voice_context_presentation": "historical_compact_v1"
}
```

The resolved voice profile is required. Omitting the presentation field retains
the full-corpus behavior, including source transcripts in generation prompts.
The optional presentation requires the complete bound rule catalog; it rejects
a partial explicit rule selection instead of silently claiming complete coverage.

## Generation and review

Construction and bounded voice-binding repair receive compact catalog records:
rule identities, declared and allowed layers, rule text, recorded status,
authority, applicability, activation and existing grounding; exemplar identities,
exact text, layer, act, source IDs, recorded validation and existing grounding.
They omit the source-transcript table. Expression and local expression repair
receive every bound rule and exemplar, preserve selected worked examples and
the full approved written calibration, and omit full source contexts. The
original subject manuscript remains excluded from expression as before.

Construction review and paragraph checking still receive complete recorded voice
source context. The full corpus, provenance and source revisions remain frozen
in the graph and snapshots. Omitting source text from generation does not waive
exact-excerpt validation, freshness checks, rule grounding, criterion scope or
authorial authority. A context-only source change still invalidates construction.

Presentation is propagated through the existing owners and compared with the
committed execution configuration. No new loop, detector threshold, authorial
rule, approval transition or automatic response correction is introduced. Active
experiments continue using their frozen code and configuration.

## Verification

`src/test_historical_compact_presentation.py` uses the v0.4 workbook and synthetic
provider transports. Eight actual journaled requests cover construction, review,
binding repair, expression, checking and local expression repair. They verify
18 rules and 84 exact excerpts in generation, all 35 original source records in
review, unchanged calibration, preserved frozen evidence, stale omitted sources,
and configuration compatibility. Writing quality and detector results require
separate live evidence.
