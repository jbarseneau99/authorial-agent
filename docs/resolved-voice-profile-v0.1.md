# Resolved voice execution profile

`resolved-voice-v1` implements a bounded part of the already-declared authorial
procedure. Existing runs retain their frozen inputs and legacy behavior. The
profile is explicit configuration, included in the immutable run binding and
checked against the actual model request.

## Requirement and implementation

| Existing requirement | Implementation |
| --- | --- |
| Constituent intellectual acts before prose | Construction returns ordered acts; `all_acts_one_paragraph` groups them without collapsing the plan. |
| Procedure v0.1 resolve operation | Each act selects real rule/exemplar identifiers, describes their application, and declares an observable criterion. Unknown or ungrounded selections are rejected. |
| Source isolation and faithful expression | The writer receives constructed claims and references; original subject prose remains available only to construction and checking. |
| Context appropriate voice evidence | Requests project selected rules, authentic excerpts and source context once; the full graph remains retained for freshness and inspection. |
| Approved written comparison with honest provenance | Configuration may freeze a generated passage explicitly approved by the author. It remains passage-level calibration and is never relabeled as original author speech or a newly approved general rule. |
| DS-10.01 criterion-linked findings | Every declared criterion receives an observation, valid sentence references, status and specific diagnosis. Layer outcomes must agree with their component checks. |
| DS-10.02 local expression repair | Profile repairs preserve unaffected sentence text and act mappings; a broader change requires reopening. |

The profile preserves candidate rule status. Applying a candidate to a bounded
trial does not promote it to a generally approved rule. A limitation on the
evidence is distinct from an observed defect in the paragraph; real missing
evidence remains an uncertainty. Final author validation remains separate.

## Ownership and preservation

`Execution` remains the scheduler. `Faculty` owns construction; the existing
construction helpers validate evidence and closure. `Expression`, `Checking`
and `Editing` retain their respective operations. Projection helpers introduce
no second lifecycle. Exact requests and responses are journaled, and procedure,
code, configuration, source, ledger and prompt identities remain bound.

The Pangram policy is unchanged. Detector flags stop progression and do not
become rewrite instructions. This increment does not claim complete autonomous
construction repair, a new author-review resolution transition, or general
voice validation. Those remain explicit limitations rather than hidden passes.

## Verification

Synthetic tests cover constituent-act grouping, rule/exemplar resolution,
calibration identity and scope, source isolation, selected evidence projection,
criterion coverage and local preservation. Live observations must be recorded
separately; fixture results are not writing-quality evidence.
