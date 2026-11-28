# Check targets and comparison context

A live run exposed a mismatch between the resolved checking instruction and its
validator. The instruction required at least one sentence within a criterion's
act scope, while the validator required every returned reference to be within
that scope. Comparative criteria legitimately asked the checker to inspect an
opening and a close, or two corresponding cases. The model cited both sides;
the validator rejected those passing checks because one reference belonged to a
contextual peer act.

The prompt now explicitly distinguishes scoped check targets from comparison
context. Each projected criterion supplies `target_sentence_ids`, derived from
the current sentence-to-act mapping and its existing `act_ids`. The checker
returns only targets from that list. It can inspect the full paragraph and
describe contextual relationships in its observation without turning peer
sentences into repair targets.

The canonical construction, criteria, act scope, output schema and validator
remain unchanged. The additional input field makes the existing boundary
explicit. Findings with out-of-scope references remain rejected; no historical
response is normalized or rewritten to pass validation.

This follows BR/DS-09 and BR/DS-10's requirements for inspectable checks and
deficiency-scoped repair. It introduces no authorial rule and expands no repair
authority. A recorded invalid response stays invalid. Any new live test must
bind this code and prompt revision before execution.
