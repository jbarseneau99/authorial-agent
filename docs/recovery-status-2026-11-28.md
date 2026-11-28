# Authorial Agent recovery checkpoint — 2026-11-28

## Identity and scope

- Original locally tested/documented source commit: `a976c2f909e71ad19c1ecdd3d05c519f1a630f9c` (unavailable here).
- Public recoverable baseline: `2855cd628499ef6bb4fd44c62acc11d3316d3ef2` on `main`.
- All reconstruction changes are confined to `experiment/nested-authorial-loops`.
- The source added on this branch is a **reconstruction**, not a byte-identical recovery of `a976c2f`.

## Recovered functional increment

1. Added opt-in `reported-over-99-human-v1` Pangram policy while retaining the existing `all-human-v1`.
2. The restored gate accepts a valid completed Pangram observation when its original `fraction_human > 0.99` (strict, with no rounding); detector-window and metadata validation still apply.
3. Added v0.4 procedure-addendum registration and compatible fresh-expression retry guard.
4. Added `test_over99_recovery.py` with deterministic boundaries, historic qualifying numbers and legacy compatibility checks. This test is **not** five new provider executions.
5. Added a reconstructed v0.4 declaration based on saved archival description. Its parent v0.3 and original content have not yet been recovered verbatim.

## Offline verification against retained raw observations

Read-only inspection of `Authorial_Agent_Batch011_Continuation_001.zip`, paths `retrospective-over99-reassessment/RECOVERY_0xx/Original_Pangram_Result.json`, confirmed for every saved result: version 4.1, recognized prediction, valid numeric fractions summing to one, correct contiguous window coverage and segment counts.

| Run | Raw fraction_human | Above 0.99 |
|---|---:|---|
| RECOVERY_064 | 1.0 | yes |
| RECOVERY_065 | 1.0 | yes |
| RECOVERY_066 | 0.9988307952880859 | yes |
| RECOVERY_067 | 1.0 | yes |
| RECOVERY_068 | 0.9999855160713196 | yes |

These are **retrospective saved observations**, not evidence that the reconstructed branch generated the prose or passes five new runs.

## Still required before calling this a restored working version

- Recover or reconstruct the source differences between public `2855cd6` and local `a976c2f` beyond the gate.
- Restore and reconcile the original v0.3 addendum and exact run configuration; preserve the 84-exemplar, 35-source-context corpus and P006 calibration without publishing private material.
- Execute the full Python test suite against a complete checkout, then five fresh authorized runs under fixed recorded configuration, and examine all four writing layers plus Pangram results.
- If the original local Git repository becomes available later, compare it directly against this branch; do not delete, overwrite or rewrite the original commit.

The prior `main` and backup remain unchanged by this recovery branch.
