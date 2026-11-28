# Authorial Agent system diagram v0.6

[View the vector diagram](system-diagram-v0.6.svg).

The v0.6 overview adds the explicitly enabled fresh-candidate branch while
preserving construction, expression, four-layer review, detector measurement and
author validation as separate responsibilities. The full set of 84 authentic
exemplars and the complete approved P006 passage remain available during
creation; reviewers retain all 35 recorded source contexts.

The two routes back to expression have different inputs. A diagnosed writing
defect goes through targeted editing with the previous paragraph and its exact
findings. An optional fresh candidate requires current passing findings in all
four writing layers, an exact completed detector flag, author authorization and
room in both committed budgets. It uses the same closed construction and voice
examples, without sending the failed paragraph or detector measurements to the
writer. Both routes return to fresh four-layer review and exact-text scanning.

The fresh branch requires paragraph addendum v0.2 plus the explicit
`author-authorized-v1` policy and a positive `max_fresh_retries`. Earlier v0.1
runs retain their original stop behavior. Fresh calls consume the existing
total attempt budget as well as the fresh allowance; neither resets. Pending,
error, stale and unscorable detector states cannot trigger a fresh candidate.

This is an overview of the implemented procedure, not a report that a
confirmation batch has passed. Detector acceptance does not establish authorial
quality, final approval or general reliability. The current confirmation
configuration declares 12 total paragraph attempts, 3 fresh retries and 4 voice
binding repairs; those trial limits are separate from the generic diagram.

The [v0.5 explanation](system-diagram-v0.5.md) retains the full-corpus and optional
compact-presentation details. See the focused
[fresh-expression instructions](fresh-expression-retry-v0.1.md) and
[continuation instructions](expression-continuation-v0.1.md) for their distinct
entry conditions and commands.

The render source is [render_procedure_diagram_v06.py](render_procedure_diagram_v06.py).
The repository stores the versioned SVG; delivery exports retain the established
`Authorial_Agent_Four_Layer_Procedure` filenames and visual style. Earlier v0.5
artifacts are unchanged. Render from the repository root with:

```bash
python docs/render_procedure_diagram_v06.py \
  --output /absolute/output/Authorial_Agent_Four_Layer_Procedure.png \
  --svg /absolute/output/Authorial_Agent_Four_Layer_Procedure.svg
```
