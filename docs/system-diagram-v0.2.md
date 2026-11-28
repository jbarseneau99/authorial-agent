# Authorial Agent system diagram v0.2

This diagram documents the implemented prompt/data flow and the separately verified provider connections. It updates the earlier four-layer diagram under the author's request to show the rule corpus, exemplar corpus, raw answers, LLM calls and Pangram after each paragraph. It makes no change to writing procedures, voice rules, runtime gates or provider prompts.

## Reproduce the deliverables

Run from the repository root, placing artifacts outside the source checkout:

```sh
python3 docs/render_procedure_diagram.py \
  --output /path/to/artifacts/Authorial_Agent_Four_Layer_Procedure.png \
  --svg /path/to/artifacts/Authorial_Agent_Four_Layer_Procedure.svg
```

The SVG contains editable text; the PNG is a 3000 × 3975 pixel rendering of the same diagram. Neither contains credential values.

## What the visual distinguishes

- Original source records remain intact. A prepared ledger links sources, rule records and exemplar passages before graph import. Importing a candidate does not approve it.
- Rules and exemplars are separate corpora. The frozen context expands selected rules and their authentic source-linked passages for construction, construction review, expression and checking. Current source matching includes only original spoken excerpts; per-act relevance selection and approved learning integration remain incomplete.
- Conceptual and epistemic work, plus rhetorical act planning, precede prose. A current construction review and explicit author closure are required before expression.
- The paragraph loop generates only its current scope. Four-layer checks precede the scan of that exact paragraph. Only current passing checks and detector evidence permit the next paragraph.
- Linguistic repair receives the previous paragraph and its diagnosed findings. Other intellectual defects pause or reopen the required work. Detector flags do not automatically trigger rewriting.
- OpenAI and Pangram are external services with different roles. Only credential environment-variable names appear in the visual. The controlled paragraph trial still requires its exact committed run configuration and explicit construction closure. Service connectivity is distinct from a successful integrated writing trial and authorial validation.
- Final assembly preserves exact accepted text. Whole-chapter semantic checking remains pending even if an authorized host records the author's approval.

## Evidence and scope

The runtime mapping was reviewed against source commit `b037978ea7ba1aad553c9a6cb71a001289550b89`, especially `src/faculty.py`, `src/construction.py`, `src/expression.py`, `src/checking.py`, `src/editing.py`, `src/paragraph_loop.py`, `src/pangram_check.py`, `src/providers.py` and `src/run_binding.py`.

The connection status is tied to [the provider readiness verification](../verification/provider-readiness-2026-11-28.json). The successful OpenAI synthetic probe returned `gpt-6.2-astra`, one claim and one act; the earlier account-credit failure is not the current observed result. Pangram's recorded live check is [the existing paragraph API probe](../verification/pangram-api-probe-v0.1.json), which returned version 4.1 for unchanged historical prose. The diagram displays the Toronto date, 27 November 2026; the later OpenAI verification timestamp is 28 November UTC.

Relevant requirements and decisions: BR/DS-05.01–05.02 (structure and expression), BR/DS-08.02 (preserved execution evidence), DS-09.01 (existing loop integration), DS-10.02 (checking and repair), CE-02–03 (loop ownership and inspectable execution), and the [paragraph/Pangram addendum](../procedures/addenda/paragraph-pangram-v0.1.json).

The rendering is a human-readable system map, not an executable or completeness-certified representation of the entire declared procedure. Limitations are shown explicitly in the visual and [running instructions](../src/RUNNING.md).
