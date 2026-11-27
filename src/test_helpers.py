"""Explicit construction closure for deterministic tests only.

These fixture judgments are not author validation, live model output or evidence
that an actual manuscript passes the writing procedure.
"""


class FixtureConstructionReviewer:
    def assess_construction(self, context):
        return [
            {'layer': layer, 'status': 'pass', 'reason': 'Deterministic fixture judgment'}
            for layer in ('conceptual', 'epistemic', 'rhetorical_plan')
        ]


def close_fixture_plan(faculty, plan):
    review = faculty.review(plan, FixtureConstructionReviewer())
    return faculty.close(plan, review, actor='author')
