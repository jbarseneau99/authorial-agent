# Pangram response fractions

## Finding and contract

The detector adapter assumed that each aggregate authorship fraction must equal
the share of characters covered by windows carrying that label. This rejected
otherwise valid mixed classifications as malformed responses.

Pangram documents aggregate authorship fractions and segment classifications as
separate response fields. Window offsets identify characters in the returned
text; the documented contract does not equate category fractions with those
character shares. The adapter now preserves the reported fractions and validates
them independently of window lengths.

References: [AI detection API](https://docs.pangram.com/api-reference/ai-detection)
and [REST API quickstart](https://docs.pangram.com/quickstart-rest).

## Unchanged acceptance policy

The paragraph gate still requires finite fractions in the range zero to one,
their sum within the existing numerical tolerance, the expected detector
version, exact returned text, contiguous complete window coverage, matching
window text, recognized labels and confidence values, and segment counts that
agree with the windows.

Passing still requires zero AI and AI-assisted fractions within the existing
machine-precision tolerance, a wholly human fraction, zero AI and AI-assisted
segments, and every window classified Human Written. Any AI or AI-assisted
window flags the paragraph even if the aggregate fractions claim wholly human
text. This changes response parsing, not the `all-human-v1` gate, authorial
assessment, or closure authority.

## Verification

Synthetic adapter tests cover mixed classifications whose fractions differ from
window character shares, misleading wholly human fractions with AI or
AI-assisted windows, and invalid numerical fractions. Existing tests continue
to exercise exact text, version, window coverage, counts, stale evidence,
request resumption, and credential omission. No live text or provider request is
part of these fixtures.
