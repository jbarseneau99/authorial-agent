"""Provider-neutral construction orchestration. Model output is an untrusted proposal."""
import json, uuid
from typing import Protocol
from model import Kind
from construction import Construction

class Reasoner(Protocol):
    def propose(self, context: dict) -> dict: ...

class Research(Protocol):
    def search(self, question: str) -> list[dict]: ...

class Faculty:
    def __init__(self, graph, reasoner: Reasoner, research: Research, baseline_digest=None, rule_ids=None):
        self.g=graph; self.c=Construction(graph); self.reasoner=reasoner; self.research=research
        self.baseline_digest=baseline_digest
        self.rule_ids=None if rule_ids is None else list(rule_ids)
        if self.rule_ids is not None and (any(not isinstance(i,str) for i in self.rule_ids) or len(set(self.rule_ids))!=len(self.rule_ids)):
            raise ValueError('Unique explicit rule IDs required')
        graph.db.execute('CREATE TABLE IF NOT EXISTS construction_plan(id TEXT PRIMARY KEY, intent TEXT, acts TEXT, context TEXT, state TEXT)')
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
        return [{'id':ident,'payload':available[ident],'authority':'advisory_only'} for ident in selected]
    def build(self, text):
        if not text.strip(): raise ValueError('Intent required')
        # Research is supplied by a trusted adapter; retrieval is not verification.
        sources=self.research.search(text)
        evidence={'intent':{'text':text,'origin':'author_input'}}
        for n,s in enumerate(sources):
            if not s.get('text') or not s.get('source'): raise ValueError('Research provenance required')
            evidence[f'source{n}']={'text':s['text'],'source':s['source'],'origin':'retrieved_unverified','metadata':s.get('metadata',{})}
        voice=self.c.voice_context(self._rules(),self.baseline_digest)
        context={'intent':text,'evidence':evidence,**voice,'instruction':'Return claims with local key, text, origin and evidence keys; ordered acts with purpose and claim keys. No prose. Agent hypotheses are not established facts. Voice rules remain advisory; authentic spoken exemplars retain their recorded written-validation status.'}
        proposal=self.reasoner.propose(json.loads(json.dumps(context)))
        if self.c._encoded(self.c.voice_context(voice['voice_candidates'],self.baseline_digest))!=self.c._encoded(voice):
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
        # Existing graph methods commit individually. Stage in an isolated in-memory graph,
        # then copy validated nodes and edges in one transaction to the persistent graph.
        from model import Graph
        stage=Graph(); sc=Construction(stage)
        try:
            i=sc.intent(text); ev={k:stage.add(Kind.EVIDENCE,v) for k,v in evidence.items()}
            ids={c['key']:sc.claim(c['text'],[ev[r] for r in c['evidence']],c['origin']) for c in claims}
            ordered=[sc.act(i,a['purpose'],[ids[k] for k in a['claims']]) for a in acts]
            errors=sc.check(i,ordered)
            if errors: raise ValueError('; '.join(errors))
            plan=str(uuid.uuid4())
            with self.g.db:
                for table,cols in [('node',5),('history',3),('edge',3)]:
                    self.g.db.executemany(f'INSERT INTO {table} VALUES('+','.join(['?']*cols)+')',stage.db.execute(f'SELECT * FROM {table}').fetchall())
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
        findings=reviewer.assess_construction(json.loads(json.dumps(snapshot)))
        return self.c.record_review(plan,snapshot,findings)
    def inspect_review(self, review_id):
        return self.c.inspect_review(review_id)
    def close(self, plan, review_id, actor):
        return self.c.close(plan,review_id,actor)
