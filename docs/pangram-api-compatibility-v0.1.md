# Pangram API compatibility check v0.1

This is a live service and adapter check of unchanged, already saved prose. It is not a new manuscript-generation run or a four-layer authorial assessment.

After the initial paragraph-gate implementation was committed at `6eac6dae288168cd0abb23fd2b71d8c0f3718e4d`, the author supplied a Pangram credential. The authenticated model-list endpoint returned HTTP 200 and the selectors `default`, `pangram-4` and `pangram-4.1`.

The check submitted the exact 56-word opening paragraph under “Approved expression” in `src/P006_reference.md`, using selector `pangram-4` and `public_dashboard_link: false`. No model rewrote or generated that paragraph. The response reported version `4.1`, the headline `Human Written`, one Human window and no AI or AI-assisted windows. Returned text matched the submitted paragraph byte-for-byte after UTF-8 decoding.

## Numerical compatibility finding

The response reported `fraction_human: 1.0`, `fraction_ai_assisted: 0.0`, and `fraction_ai: 6.557978722147641e-40`. The first adapter version treated the tiny positive AI value as a flag because its final comparison required literal floating-point zero. That original result and verdict are retained.

The correction recognizes numerical residue within `sys.float_info.epsilon` when comparing fractions with zero or one. It still requires every window to be `Human Written` and both AI/AI-assisted segment counts to be zero. A material nonzero fraction or any AI/AI-assisted segment cannot pass. Original numeric values remain intact in the recorded response.

This is an adapter arithmetic correction, supported by a real API response. It changes no manuscript, voice rule, prompt or authorial layer. The original procedure addendum and original test/probe records are preserved. The correction and its regression evidence are versioned separately.

See the [live probe record](../verification/pangram-api-probe-v0.1.json) and [corrected-code fixture verification](../verification/paragraph-pangram-v0.2.json). The probe record distinguishes the original verdict from re-evaluation of the same saved response by the corrected parser. Re-evaluation makes no new API request.

## Scope of the evidence

The live check establishes that the supplied key works, this account can submit and poll a Pangram task, the recorded response is version 4.1, and the adapter can parse the result for this paragraph. It does not establish that a future generation will receive the same classification, that a full chapter passes, or that the four-layer writing procedure has been reproduced end-to-end.

The detector's [API reference](https://docs.pangram.com/api-reference/ai-detection) permits model-series updates and normalized returned text. Exact version/text checks still pause progression when those values differ from the bound expectation. No normalization mapping was introduced by this correction.
