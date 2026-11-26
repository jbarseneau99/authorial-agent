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
    def __init__(self, graph, reasoner: Reasoner, research: Research):
        self.g=graph; self.c=Construction(graph); self.reasoner=reasoner; self.research=research
        graph.db.execute('CREATE TABLE IF NOT EXISTS construction_plan(id TEXT PRIMARY KEY, intent TEXT, acts TEXT, context TEXT, state TEXT)')
    def build(self, text):
        if not text.strip(): raise ValueError('Intent required')
        # Research is supplied by a trusted adapter; retrieval is not verification.
        sources=self.research.search(text)
        evidence={'intent':{'text':text,'origin':'author_input'}}
        for n,s in enumerate(sources):
            if not s.get('text') or not s.get('source'): raise ValueError('Research provenance required')
            evidence[f'source{n}']={'text':s['text'],'source':s['source'],'origin':'retrieved_unverified','metadata':s.get('metadata',{})}
        rules=[]
        for ident,payload in self.g.db.execute("SELECT id,payload FROM node WHERE kind='rule' AND status!='stale'"):
            rules.append({'id':ident,'payload':json.loads(payload),'authority':'advisory_only'})
        context={'intent':text,'evidence':evidence,'voice_candidates':rules,'instruction':'Return claims with local key, text, origin and evidence keys; ordered acts with purpose and claim keys. No prose. Agent hypotheses are not established facts.'}
        proposal=self.reasoner.propose(context)
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
        return {'intent':self.g.get(i),'acts':[{'act':self.g.get(a),'claims':[self.g.get(d) for r,d in self.g.prerequisites(a) if r=='asserts']} for a in acts],'state':state,'structural_errors':self.c.check(i,acts)}
