"""Provider-neutral construction orchestration. Model output is an untrusted proposal."""
import hashlib, json, uuid
from typing import Protocol
from model import Kind
from construction import Construction, CONSTRUCTION_LAYERS
from voice_resolution import (PROFILE, FULL_CORPUS_SCOPE, construction_packet, construction_review_packet,
                              resolve_voice_bindings, validate_written_calibration, validate_voice_presentation,
                              HISTORICAL_COMPACT_PRESENTATION)

class Reasoner(Protocol):
    def propose(self, context: dict) -> dict: ...
    def resolve_voice(self, context: dict) -> dict: ...

class Research(Protocol):
    def search(self, question: str) -> list[dict]: ...


class VoiceRepairReopen(ValueError):
    """A recorded voice repair requests work outside its permitted scope."""
    def __init__(self, attempt, layer, reason):
        self.attempt, self.layer, self.reason = attempt, layer, reason
        super().__init__(f'Voice repair requests {layer} reopening: {reason}')


class Faculty:
    def __init__(self, graph, reasoner: Reasoner, research: Research, baseline_digest=None, rule_ids=None,
                 execution_profile=None, written_calibration=None, voice_context_scope=None,
                 voice_context_presentation=None):
        self.g=graph; self.c=Construction(graph); self.reasoner=reasoner; self.research=research
        self.baseline_digest=baseline_digest
        if execution_profile not in {None, PROFILE}:
            raise ValueError('Unknown construction execution profile')
        self.execution_profile=execution_profile
        if voice_context_scope not in {None, FULL_CORPUS_SCOPE}:
            raise ValueError('Unsupported voice context scope')
        if voice_context_scope is not None and execution_profile != PROFILE:
            raise ValueError('Full voice corpus requires the resolved voice profile')
        self.voice_context_scope=voice_context_scope
        self.voice_context_presentation=validate_voice_presentation(voice_context_presentation, voice_context_scope)
        self.written_calibration=validate_written_calibration(written_calibration)
        if self.written_calibration and execution_profile != PROFILE:
            raise ValueError('Written calibration requires the resolved voice profile')
        self.rule_ids=None if rule_ids is None else list(rule_ids)
        if self.rule_ids is not None and (any(not isinstance(i,str) for i in self.rule_ids) or len(set(self.rule_ids))!=len(self.rule_ids)):
            raise ValueError('Unique explicit rule IDs required')
        graph.db.execute('CREATE TABLE IF NOT EXISTS construction_plan(id TEXT PRIMARY KEY, intent TEXT, acts TEXT, context TEXT, state TEXT)')
        graph.db.executescript('''
            CREATE TABLE IF NOT EXISTS voice_repair_attempt(
                id TEXT PRIMARY KEY,
                previous_plan TEXT NOT NULL REFERENCES construction_plan(id),
                review TEXT NOT NULL REFERENCES construction_review(id),
                snapshot TEXT NOT NULL,
                input TEXT NOT NULL,
                actor TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS voice_repair_result(
                attempt TEXT PRIMARY KEY REFERENCES voice_repair_attempt(id),
                new_plan TEXT REFERENCES construction_plan(id),
                response TEXT,
                lineage TEXT,
                state TEXT NOT NULL,
                error_type TEXT
            );
        ''')
    def _rules(self):
        if self.baseline_digest is None:
            records=self.g.db.execute("SELECT id,payload FROM node WHERE kind='rule' AND status!='stale' ORDER BY id").fetchall()
        else:
            baseline=self.g.db.execute('SELECT manifest FROM imported_baseline WHERE digest=?',(self.baseline_digest,)).fetchone()
            if not baseline: raise ValueError('Bound ledger has not been imported')
            records=self.g.db.execute("SELECT n.id,n.payload FROM node n JOIN imported_record r ON r.node_id=n.id WHERE r.digest=? AND r.sheet='Candidate rules' AND n.kind='rule' AND n.status!='stale' ORDER BY n.id",(self.baseline_digest,)).fetchall()
        available={ident:json.loads(payload) for ident,payload in records}
        selected=sorted(available) if self.rule_ids is None else self.rule_ids
        if not set(selected)<=set(available): raise ValueError('Selected voice rule missing, stale or outside bound ledger')
        if self.voice_context_presentation == HISTORICAL_COMPACT_PRESENTATION and set(selected) != set(available):
            raise ValueError('Historical compact presentation requires the complete bound rule catalog')
        return [{'id':ident,'payload':available[ident],'authority':'advisory_only'} for ident in selected]
    def build(self, text):
        if not text.strip(): raise ValueError('Intent required')
        # Research is supplied by a trusted adapter; retrieval is not verification.
        sources=self.research.search(text)
        evidence={'intent':{'text':text,'origin':'author_input'}}
        for n,s in enumerate(sources):
            if not s.get('text') or not s.get('source'): raise ValueError('Research provenance required')
            evidence[f'source{n}']={'text':s['text'],'source':s['source'],'origin':'retrieved_unverified','metadata':s.get('metadata',{})}
        voice=self.c.voice_context(self._rules(),self.baseline_digest,self.voice_context_scope,self.voice_context_presentation)
        context={'intent':text,'evidence':evidence,**voice,'instruction':'Return claims with local key, text, origin and evidence keys; ordered acts with purpose and claim keys. No prose. Agent hypotheses are not established facts. Voice rules remain advisory; authentic spoken exemplars retain their recorded written-validation status.'}
        packet=context
        if self.execution_profile == PROFILE:
            context.update(execution_profile=PROFILE, written_calibration=validate_written_calibration(self.written_calibration))
            context['instruction'] += (' Use the conceptual and epistemic rules together with their '
                'actual exemplars to form the concepts, distinctions, relationships and epistemic '
                'commitments of this construction. For each selected binding in those layers, '
                'record the demonstrated operation, the specific encoded decision it shapes, and '
                'a criterion by which that decision can be checked in the claims or acts. '
                'Resolve rhetorical and linguistic bindings for the later expression of those acts. '
                'Resolve each act separately and return its voice_bindings: '
                'rule_id and exemplar_ids from this catalog, one declared layer, an explicit '
                'application to this act, and an observable check criterion. Select relevant '
                'grounded evidence; do not treat paragraph count as intellectual-act count. '
                'Preserve epistemic qualifications without automatically turning every limit '
                'into a separate explanatory claim.')
            packet=construction_packet(context)
        proposal=self.reasoner.propose(json.loads(json.dumps(packet)))
        if self.c._encoded(self.c.voice_context(voice['voice_candidates'],self.baseline_digest,self.voice_context_scope,self.voice_context_presentation))!=self.c._encoded(voice):
            raise ValueError('Voice inputs changed during construction')
        claims=proposal['claims']; acts=proposal['acts']; keys=set()
        if not claims or not acts: raise ValueError('Empty construction')
        for c in claims:
            if not isinstance(c['key'],str) or c['key'] in keys or not c['text'].strip(): raise ValueError('Invalid claim')
            keys.add(c['key']); refs=c['evidence']; origin=c['origin']
            if not refs or not set(refs)<=evidence.keys() or origin not in {'author','external','agent_hypothesis'}: raise ValueError('Invalid provenance')
            if origin=='author' and set(refs)!={'intent'}: raise ValueError('Author attribution requires intent')
            if origin=='external' and not any(r!='intent' for r in refs): raise ValueError('External claim requires retrieved source')
        used=set()
        for a in acts:
            if not a['purpose'].strip() or not a['claims'] or not set(a['claims'])<=keys: raise ValueError('Invalid act')
            used.update(a['claims'])
        if used!=keys: raise ValueError('Unrealized claims')
        if self.execution_profile == PROFILE:
            acts=resolve_voice_bindings(acts,voice)
        # Existing graph methods commit individually. Stage in an isolated in-memory graph,
        # then copy validated nodes and edges in one transaction to the persistent graph.
        from model import Graph
        stage=Graph(); sc=Construction(stage)
        try:
            i=sc.intent(text); ev={k:stage.add(Kind.EVIDENCE,v) for k,v in evidence.items()}
            ids={c['key']:sc.claim(c['text'],[ev[r] for r in c['evidence']],c['origin']) for c in claims}
            ordered=[sc.act(i,a['purpose'],[ids[k] for k in a['claims']],
                            voice_bindings=a.get('voice_bindings') if self.execution_profile == PROFILE else None)
                     for a in acts]
            errors=sc.check(i,ordered)
            if errors: raise ValueError('; '.join(errors))
            plan=str(uuid.uuid4())
            with self.g.db:
                for table,cols in [('node',5),('history',3),('edge',3)]:
                    self.g.db.executemany(f'INSERT INTO {table} VALUES('+','.join(['?']*cols)+')',stage.db.execute(f'SELECT * FROM {table}').fetchall())
                if self.execution_profile == PROFILE:
                    self.g.db.executemany('INSERT INTO edge VALUES(?,?,?)',
                        [(ident,'applies',rule) for ident,act in zip(ordered,acts)
                         for rule in sorted({binding['rule_id'] for binding in act['voice_bindings']})])
                self.g.db.execute('INSERT INTO construction_plan VALUES(?,?,?,?,?)',(plan,i,json.dumps(ordered),json.dumps(context),'proposed_unvalidated'))
            return plan
        finally: stage.db.close()
    def inspect(self, plan):
        row=self.g.db.execute('SELECT intent,acts,state FROM construction_plan WHERE id=?',(plan,)).fetchone()
        if not row: raise KeyError(plan)
        i,acts,state=row; acts=json.loads(acts)
        errors=self.c.check(i,acts); closure=None
        if state=='closed':
            try: closure=self.c.require_closed(plan)
            except (KeyError,ValueError): state='stale'
        return {'intent':self.g.get(i),'acts':[{'act':self.g.get(a),'claims':[self.g.get(d) for r,d in self.g.prerequisites(a) if r=='asserts']} for a in acts],'state':state,'structural_errors':errors,'closure':closure}
    def review(self, plan, reviewer):
        snapshot=self.c.snapshot(plan)
        packet=construction_review_packet(snapshot) if snapshot.get('execution_profile') == PROFILE else snapshot
        findings=reviewer.assess_construction(json.loads(json.dumps(packet)))
        return self.c.record_review(plan,snapshot,findings)
    def inspect_review(self, review_id):
        return self.c.inspect_review(review_id)
    def close(self, plan, review_id, actor):
        return self.c.close(plan,review_id,actor)

    def _voice_repair_review(self, plan, review_id):
        state = self.g.db.execute('SELECT state FROM construction_plan WHERE id=?', (plan,)).fetchone()
        if not state or state[0] not in {'proposed_unvalidated', 'reopen_required'}:
            raise ValueError('Voice repair requires a current unclosed construction plan')
        review = self.c.inspect_review(review_id)
        if review['plan'] != plan or review['state'] != 'review_required':
            raise ValueError('Voice repair requires the current failed review of this plan')
        if review['snapshot'].get('execution_profile') != PROFILE:
            raise ValueError('Voice repair requires the resolved voice profile')
        findings = review['findings']
        if (not isinstance(findings, list) or len(findings) != 3
                or any(not isinstance(finding, dict) for finding in findings)
                or {finding.get('layer') for finding in findings} != CONSTRUCTION_LAYERS
                or any(not isinstance(finding.get('reason'), str) or not finding['reason'].strip()
                       for finding in findings)
                or {finding['layer']: finding.get('status') for finding in findings}
                    != {'conceptual': 'pass', 'epistemic': 'pass', 'rhetorical_plan': 'fail'}):
            raise ValueError('Voice repair requires conceptual and epistemic passes and a definite rhetorical-plan failure')
        return review

    def _voice_repair_proposal(self, response, snapshot):
        if not isinstance(response, dict):
            raise ValueError('Voice repair must return bindings or an explicit reopening request')
        if response.get('status') == 'reopen':
            if (set(response) != {'status', 'layer', 'reason'}
                    or response['layer'] not in CONSTRUCTION_LAYERS
                    or not isinstance(response['reason'], str) or not response['reason'].strip()):
                raise ValueError('Voice reopening requires a construction layer and explicit reason')
            return None
        acts = response.get('acts')
        if (set(response) != {'status', 'acts'} or response['status'] != 'bindings'
                or not isinstance(acts, list)
                or any(not isinstance(act, dict) or set(act) != {'id', 'voice_bindings'} for act in acts)
                or [act['id'] for act in acts] != snapshot['acts']):
            raise ValueError('Voice repair must preserve exact ordered act IDs and return only voice bindings')
        resolved = resolve_voice_bindings(acts, snapshot)
        if all(act['voice_bindings'] == snapshot['nodes'][act['id']]['node']['payload']['voice_bindings']
               for act in resolved):
            raise ValueError('Voice repair returned no binding changes; unresolved work requires reopening')
        return resolved

    def repair_voice(self, plan, review_id, actor=None):
        """Repair only reviewed voice bindings; preserve the reviewed argument.

        DS-08.01 and DS-10.02 allow a deficiency to return to its owning faculty.
        This operation creates an unclosed plan version. It grants no authorial
        validation and cannot revise claims, intent, act purpose or act order.
        """
        if actor != 'author':
            raise PermissionError('Author operational authorization required for voice repair')
        attempt = str(uuid.uuid4())
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            review = self._voice_repair_review(plan, review_id)
            snapshot = review['snapshot']
            encoded_snapshot = self.c._encoded(snapshot)
            request = construction_review_packet(snapshot, for_generation=True)
            request['repair'] = {
                'attempt': attempt, 'previous_plan': plan,
                'review': {key: review[key] for key in ('id', 'plan', 'state', 'findings')},
                'instruction': (
                    'Repair only the voice bindings, applications and criteria diagnosed by this '
                    'rhetorical-plan review. Return every existing act ID exactly once in its '
                    'existing order, with only voice_bindings. Preserve intent, claims, evidence, '
                    'act purposes and claim references exactly. Use grounded catalog rules and '
                    'exemplars. If the repair needs any substantive construction change or missing '
                    'evidence, return an explicit reopening request. The repaired plan requires '
                    'a new independent construction review and closure; this operation grants neither.'
                ),
            }
            request['instruction'] = 'Perform the bounded repair in repair.instruction against the exact repair.review.'
            request['repair']['review']['snapshot_sha256'] = hashlib.sha256(encoded_snapshot.encode('utf-8')).hexdigest()
            self.g.db.execute('INSERT INTO voice_repair_attempt VALUES(?,?,?,?,?,?)',
                              (attempt, plan, review_id, encoded_snapshot, self.c._encoded(request), actor))

        response_json, new_plan = None, None
        try:
            response = self.reasoner.resolve_voice(json.loads(self.c._encoded(request)))
            response_json = self.c._encoded(response)
            response = json.loads(response_json)
            resolved = self._voice_repair_proposal(response, snapshot)
            with self.g.db:
                self.g.db.execute('BEGIN IMMEDIATE')
                if self.c._encoded(self._voice_repair_review(plan, review_id)) != self.c._encoded(review):
                    raise ValueError('Construction review changed during voice repair')
                if response['status'] == 'reopen':
                    self.g.db.execute('INSERT INTO voice_repair_result VALUES(?,NULL,?,NULL,?,NULL)',
                                      (attempt, response_json, 'reopen_requested'))
                else:
                    ordered, versions = [], []
                    for act in resolved:
                        previous = act['id']
                        record = snapshot['nodes'][previous]
                        payload = json.loads(self.c._encoded(record['node']['payload']))
                        changed = payload['voice_bindings'] != act['voice_bindings']
                        current = str(uuid.uuid4()) if changed else previous
                        if changed:
                            payload['voice_bindings'] = act['voice_bindings']
                            encoded = self.c._encoded(payload)
                            self.g.db.execute('INSERT INTO node VALUES(?,?,1,?,?)',
                                              (current, Kind.ACT.value, 'draft', encoded))
                            self.g.db.execute('INSERT INTO history VALUES(?,1,?)', (current, encoded))
                            edges = [(current, relation, target) for relation, target in record['edges']
                                     if relation != 'applies']
                            edges.extend((current, 'applies', rule) for rule in
                                         sorted({binding['rule_id'] for binding in act['voice_bindings']}))
                            self.g.db.executemany('INSERT INTO edge VALUES(?,?,?)', edges)
                        ordered.append(current)
                        versions.append({'previous': previous, 'current': current, 'changed': changed})
                    lineage = {'previous_plan': plan, 'review': review_id, 'act_versions': versions}
                    context = json.loads(self.c._encoded(snapshot['context']))
                    context['voice_repair'] = {'attempt': attempt, **lineage}
                    new_plan = str(uuid.uuid4())
                    self.g.db.execute('INSERT INTO construction_plan VALUES(?,?,?,?,?)',
                                      (new_plan, snapshot['intent'], self.c._encoded(ordered),
                                       self.c._encoded(context), 'proposed_unvalidated'))
                    self.c.snapshot(new_plan)
                    self.g.db.execute('INSERT INTO voice_repair_result VALUES(?,?,?,?,?,NULL)',
                                      (attempt, new_plan, response_json, self.c._encoded(lineage), 'plan_proposed'))
        except Exception as exc:
            with self.g.db:
                self.g.db.execute('INSERT INTO voice_repair_result VALUES(?,NULL,?,NULL,?,?)',
                                  (attempt, response_json, 'unresolved', type(exc).__name__))
            raise
        if response['status'] == 'reopen':
            raise VoiceRepairReopen(attempt, response['layer'], response['reason'])
        return new_plan

    def inspect_voice_repair(self, attempt):
        row = self.g.db.execute('SELECT previous_plan,review,snapshot,input,actor FROM voice_repair_attempt WHERE id=?',
                                (attempt,)).fetchone()
        if row is None:
            raise KeyError(attempt)
        previous_plan, review, snapshot, request, actor = row
        result = self.g.db.execute('SELECT new_plan,response,lineage,state,error_type FROM voice_repair_result WHERE attempt=?',
                                   (attempt,)).fetchone()
        return {'id': attempt, 'previous_plan': previous_plan, 'review': review,
                'snapshot': json.loads(snapshot),
                'snapshot_sha256': hashlib.sha256(snapshot.encode('utf-8')).hexdigest(),
                'input': json.loads(request), 'actor': actor,
                'new_plan': result[0] if result else None,
                'response': json.loads(result[1]) if result and result[1] is not None else None,
                'lineage': json.loads(result[2]) if result and result[2] is not None else None,
                'state': result[3] if result else 'invocation_pending',
                'error_type': result[4] if result else None}
