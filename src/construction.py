"""Graph checks and revision-bound construction closure evidence.

Faculty owns construction orchestration. These helpers extend the existing
construction gate; they neither create a second lifecycle nor certify truth.
"""
import json
import uuid
from model import Kind

CONSTRUCTION_LAYERS = {'conceptual', 'epistemic', 'rhetorical_plan'}


class Construction:
    def __init__(self, graph):
        self.g = graph
        graph.db.execute('''CREATE TABLE IF NOT EXISTS construction_review(
            id TEXT PRIMARY KEY, plan TEXT NOT NULL, snapshot TEXT NOT NULL,
            findings TEXT NOT NULL, state TEXT NOT NULL)''')
        graph.db.execute('''CREATE TABLE IF NOT EXISTS construction_closure(
            id TEXT PRIMARY KEY, plan TEXT NOT NULL, review TEXT NOT NULL,
            snapshot TEXT NOT NULL, actor TEXT NOT NULL, authority TEXT NOT NULL)''')

    def intent(self, text):
        if not text.strip():
            raise ValueError('Empty intent')
        return self.g.add(Kind.INTENT, {'text': text})

    def claim(self, text, provenance, origin):
        if not text.strip() or not provenance or origin not in {'author', 'external', 'agent_hypothesis'}:
            raise ValueError('Claim provenance and origin required')
        for p in provenance:
            if self.g.get(p)['kind'] != 'evidence':
                raise ValueError('Expected evidence')
        claim = self.g.add(Kind.CLAIM, {'text': text, 'origin': origin, 'verified': False})
        for p in set(provenance):
            self.g.link(claim, 'supports', p)
        return claim

    def act(self, intent, purpose, claims):
        if self.g.get(intent)['kind'] != 'intent' or not purpose.strip() or not claims:
            raise ValueError('Intent, purpose and claims required')
        for claim in claims:
            if self.g.get(claim)['kind'] != 'claim':
                raise ValueError('Expected claim')
        act = self.g.add(Kind.ACT, {'purpose': purpose})
        self.g.link(act, 'addresses', intent)
        for claim in set(claims):
            self.g.link(act, 'asserts', claim)
        return act

    def check(self, intent, acts):
        errors, seen, active = [], set(), set()

        def visit(ident):
            if ident in active:
                errors.append('Cyclic prerequisite: ' + ident)
                return
            if ident in seen:
                return
            active.add(ident)
            obj, edges = self.g.get(ident), self.g.prerequisites(ident)
            if obj['status'] == 'stale':
                errors.append('Stale object: ' + ident)
            if obj['kind'] == 'act':
                if not obj['payload'].get('purpose') or ('addresses', intent) not in edges or not any(r == 'asserts' for r, _ in edges):
                    errors.append('Incomplete act: ' + ident)
            if obj['kind'] == 'claim':
                if obj['payload'].get('origin') not in {'author', 'external', 'agent_hypothesis'} or not any(r == 'supports' and self.g.get(d)['kind'] == 'evidence' for r, d in edges):
                    errors.append('Missing provenance: ' + ident)
            for rel, dest in edges:
                if rel in {'addresses', 'asserts', 'supports', 'depends'}:
                    visit(dest)
            active.remove(ident)
            seen.add(ident)

        obj = self.g.get(intent)
        if obj['kind'] != 'intent' or not acts or len(set(acts)) != len(acts):
            errors.append('Invalid plan')
        if obj['status'] == 'stale':
            errors.append('Stale intent: ' + intent)
        for act in acts:
            if self.g.get(act)['kind'] != 'act':
                errors.append('Expected act')
            visit(act)
        return errors

    def sentence(self, intent, plan, acts, text):
        if not text.strip() or not acts or not set(acts) <= set(plan):
            raise ValueError('Sentence requires planned acts')
        errors = self.check(intent, plan)
        if errors:
            raise ValueError('; '.join(errors))
        sentence = self.g.add(Kind.SENTENCE, {'text': text})
        for act in set(acts):
            self.g.link(sentence, 'realizes', act)
        return sentence

    def _collect(self, roots):
        nodes = {}

        def collect(ident):
            if ident in nodes:
                return
            obj = self.g.get(ident)
            if obj['status'] == 'stale':
                raise ValueError('Stale construction input: ' + ident)
            nodes[ident] = {'node': obj, 'edges': sorted(self.g.prerequisites(ident))}
            for _, target in nodes[ident]['edges']:
                collect(target)

        for root in roots:
            collect(root)
        return nodes

    def voice_context(self, rules, baseline_digest=None):
        """Resolve selected grounding without activating candidate rules.

        Original spoken excerpts must match their source transcript. Experimental
        results remain evidence records, never newly authenticated exemplars.
        Selection is explicit; this helper does not invent per-act relevance.
        """
        for selected in rules:
            ident = selected['id']
            obj = self.g.get(ident)
            if obj['kind'] != 'rule' or obj['payload'] != selected['payload']:
                raise ValueError('Selected voice rule changed; rebuild construction: ' + ident)
            if baseline_digest is not None:
                row = self.g.db.execute('SELECT 1 FROM imported_record WHERE digest=? AND sheet=? AND node_id=?',
                                        (baseline_digest, 'Candidate rules', ident)).fetchone()
                if not row:
                    raise ValueError('Selected rule does not belong to bound ledger')
        nodes = self._collect([rule['id'] for rule in rules])
        exemplars = []
        for ident, record in sorted(nodes.items()):
            obj = record['node']
            payload = obj['payload']
            if obj['kind'] != 'evidence' or payload.get('Exemplar type') != 'Original spoken':
                continue
            excerpt = payload.get('Exact excerpt')
            if not isinstance(excerpt, str) or not excerpt.strip():
                raise ValueError('Spoken exemplar is missing its exact source excerpt: ' + ident)
            sources = []
            for rel, target in record['edges']:
                source = nodes[target]['node']
                transcript = source['payload'].get('User transcript (segments joined)', '')
                if (rel == 'derived_from' and source['kind'] == 'evidence'
                        and source['payload'].get('Source ID') == payload.get('Source ID')
                        and isinstance(transcript, str) and excerpt in transcript):
                    sources.append(source)
            if not sources:
                raise ValueError('Spoken exemplar does not match its recorded source: ' + ident)
            exemplars.append({'id': ident, 'node': obj, 'sources': sources,
                              'authority': 'original_spoken; written validation remains as recorded'})
        return {'baseline_digest': baseline_digest, 'voice_candidates': rules,
                'voice_evidence': nodes, 'authentic_exemplars': exemplars,
                'selection_status': 'explicit_rule_set; per_act_relevance_not_assessed'}

    def snapshot(self, plan):
        """Capture exact construction, placement and selected voice evidence."""
        row = self.g.db.execute('SELECT intent,acts,context FROM construction_plan WHERE id=?', (plan,)).fetchone()
        if not row:
            raise KeyError(plan)
        intent, raw_acts, raw_context = row
        acts, context = json.loads(raw_acts), json.loads(raw_context)
        errors = self.check(intent, acts)
        if errors:
            raise ValueError('; '.join(errors))
        voice = self.voice_context(context.get('voice_candidates', []), context.get('baseline_digest'))
        # Legacy plans lacking frozen exemplar context cannot bypass new closure.
        if 'voice_evidence' not in context or self._encoded(voice) != self._encoded({key: context[key] for key in voice}):
            raise ValueError('Voice inputs changed or were not frozen; rebuild construction')
        nodes = self._collect([intent] + acts)
        nodes.update(voice['voice_evidence'])
        return {'plan': plan, 'intent': intent, 'acts': acts, 'context': context,
                'nodes': nodes, **voice}

    @staticmethod
    def _encoded(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'))

    def record_review(self, plan, snapshot, findings):
        if (not isinstance(findings, list) or len(findings) != 3
                or any(not isinstance(f, dict) for f in findings)
                or {f.get('layer') for f in findings} != CONSTRUCTION_LAYERS):
            raise ValueError('Exactly one construction finding per required layer')
        for finding in findings:
            if (finding.get('status') not in {'pass', 'fail', 'uncertain'}
                    or not isinstance(finding.get('reason'), str) or not finding['reason'].strip()):
                raise ValueError('Invalid construction finding')
        ident = str(uuid.uuid4())
        state = 'checks_passed' if all(f['status'] == 'pass' for f in findings) else 'review_required'
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            if self._encoded(self.snapshot(plan)) != self._encoded(snapshot):
                raise ValueError('Construction changed during review')
            self.g.db.execute('INSERT INTO construction_review VALUES(?,?,?,?,?)',
                              (ident, plan, self._encoded(snapshot), self._encoded(findings), state))
            if state == 'review_required':
                self.g.db.execute("UPDATE construction_plan SET state='reopen_required' WHERE id=? AND state='closed'", (plan,))
        return ident

    def inspect_review(self, ident):
        row = self.g.db.execute('SELECT plan,snapshot,findings,state FROM construction_review WHERE id=?', (ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        plan, snapshot, findings, state = row
        try:
            current = self._encoded(self.snapshot(plan)) == snapshot
        except (KeyError, ValueError):
            current = False
        return {'id': ident, 'plan': plan, 'state': state if current else 'stale',
                'findings': json.loads(findings), 'snapshot': json.loads(snapshot)}

    def close(self, plan, review_id, actor):
        """Authority is supplied by the trusted host, not the reasoning model."""
        if actor != 'author':
            raise PermissionError('Author construction closure required')
        ident = str(uuid.uuid4())
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            review = self.inspect_review(review_id)
            if review['plan'] != plan or review['state'] != 'checks_passed':
                raise ValueError('Current passing construction review required')
            state = self.g.db.execute('SELECT state FROM construction_plan WHERE id=?', (plan,)).fetchone()
            if not state or state[0] != 'proposed_unvalidated':
                raise ValueError('Current unclosed construction required')
            self.g.db.execute('INSERT INTO construction_closure VALUES(?,?,?,?,?,?)',
                              (ident, plan, review_id, self._encoded(review['snapshot']), actor,
                               'explicit_author_closure; trusted_host_identity'))
            self.g.db.execute("UPDATE construction_plan SET state='closed' WHERE id=?", (plan,))
        return ident

    def require_closed(self, plan):
        row = self.g.db.execute('SELECT state FROM construction_plan WHERE id=?', (plan,)).fetchone()
        if not row:
            raise KeyError(plan)
        if row[0] != 'closed':
            raise ValueError('Construction is not closed')
        witnesses = self.g.db.execute('SELECT id,review,snapshot,actor,authority FROM construction_closure WHERE plan=? ORDER BY rowid DESC', (plan,)).fetchall()
        current = self._encoded(self.snapshot(plan))
        for ident, review_id, snapshot, actor, authority in witnesses:
            if actor == 'author' and snapshot == current and self.inspect_review(review_id)['state'] == 'checks_passed':
                return {'id': ident, 'plan': plan, 'review': review_id, 'actor': actor, 'authority': authority}
        raise ValueError('Construction closure is missing or stale')
