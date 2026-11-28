# Authorial Agent system diagram v0.3

This version shows the resolved execution profile and the author's explicit
instruction to include exemplars as worked examples and ask for prose structured
like them. It documents the changes in
[procedure-fidelity-v0.1.md](procedure-fidelity-v0.1.md) and
[the current loop map](../loops/inventory-v0.5.json).

Construction review sees the complete available bound catalog to assess relevant
omissions. Expression receives selected authentic example text paired with the
corresponding act, rule, structure to model and criterion. The approved generated
written passage remains separately labeled at passage-only authority. The writer
is explicitly asked to realize the new subject through those demonstrated
structures. Checking assesses both meaning and that authorial realization.

Reviewed binding or criterion defects can return to a separately budgeted voice
resolution call within the construction owner. That call preserves claims and
act purposes/order and requires a fresh review. See
[voice-binding-repair-v0.1.md](voice-binding-repair-v0.1.md).

The repair path now follows the diagnosed defect in the resolved profile. A
definite expression defect found in any of the four layers may receive a scoped
repair against unchanged construction. Construction defects, evidence gaps and
uncertainty remain gated. This does not change the legacy profile or turn a
detector score into a repair instruction.

Render outside the source checkout:

```sh
python3 docs/render_procedure_diagram.py \
  --output /path/to/artifacts/Authorial_Agent_Four_Layer_Procedure.png \
  --svg /path/to/artifacts/Authorial_Agent_Four_Layer_Procedure.svg
```

The connection statements refer to recorded provider observations. They do not
claim that the latest paragraph passed or that the author approved it. Live
outcomes are reported in their separate immutable experiment records. The exact
historical successful prompt trace remains unrecovered; this is a map of the
current implementation, not a claim of exact historical replay.

Earlier diagram documentation remains unchanged at
[system-diagram-v0.2.md](system-diagram-v0.2.md).
