"""Constrained expression: structural checks, not semantic entailment certification."""
import json, uuid
from typing import Protocol
from construction import Construction

class Writer(Protocol):
    def realize(self, context: dict) -> dict: ...

class Expression:
    def __init__(self, graph, writer: Writer):
        self.g=graph; self.writer=writer; self.c=Construction(graph)
        graph.db.execute('CREATE TABLE IF NOT EXISTS expression_run(id TEXT PRIMARY KEY, plan TEXT, state TEXT, sentences TEXT, detail TEXT)')
    def context(self, plan):
        row=self.g.db.execute('SELECT intent,acts,context FROM construction_plan WHERE id=?',(plan,)).fetchone()
        if not row: raise KeyError(plan)
        intent,raw,ctx=row; acts=json.loads(raw)
        errors=self.c.check(intent,acts)
        if errors: raise ValueError('; '.join(errors))
        nodes={}
        def collect(n):
            if n in nodes: return
            nodes[n]={'node':self.g.get(n),'edges':sorted(self.g.prerequisites(n))}
            for _,d in nodes[n]['edges']: collect(d)
        for n in [intent]+acts: collect(n)
        rules=json.loads(ctx)['voice_candidates']
        return {'intent':intent,'acts':acts,'nodes':nodes,'voice_candidates':rules,'instruction':'Return sentences with text and act IDs in plan order, or a reopen request with layer, act IDs and reason. Preserve claims and uncertainty; no new claims.'}
    def run(self, plan):
        ctx=self.context(plan); result=self.writer.realize(json.loads(json.dumps(ctx)))
        run=str(uuid.uuid4()); acts=ctx['acts']; ids=[]
        if not isinstance(result,dict): raise ValueError('Expected structured response')
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            if self.context(plan)!=ctx: raise ValueError('Construction changed during expression')
            if result.get('status')=='reopen':
                refs=result.get('acts',[]); layer=result.get('layer'); reason=result.get('reason','')
                if layer not in {'epistemic','rhetorical'} or not isinstance(reason,str) or not reason.strip() or not refs or not set(refs)<=set(acts): raise ValueError('Invalid reopening request')
                state='reopen_requested'
            elif result.get('status')=='draft':
                sentences=result.get('sentences',[]); order=[]
                if not sentences: raise ValueError('Empty expression')
                for s in sentences:
                    refs=s.get('acts',[]); text=s.get('text','')
                    if not isinstance(text,str) or not text.strip() or not refs or len(set(refs))!=len(refs) or not set(refs)<=set(acts): raise ValueError('Invalid sentence or act references')
                    order.extend(acts.index(a) for a in refs)
                if set(order)!=set(range(len(acts))) or order!=sorted(order): raise ValueError('Missing or reordered acts')
                for s in sentences:
                    ident=str(uuid.uuid4()); payload=json.dumps({'text':s['text'],'semantic_status':'unverified'})
                    self.g.db.execute('INSERT INTO node VALUES(?,?,1,?,?)',(ident,'sentence','draft',payload))
                    self.g.db.execute('INSERT INTO history VALUES(?,1,?)',(ident,payload))
                    self.g.db.executemany('INSERT INTO edge VALUES(?,?,?)',[(ident,'realizes',a) for a in s['acts']]); ids.append(ident)
                state='draft_unvalidated'
            else: raise ValueError('Unknown expression status')
            self.g.db.execute('INSERT INTO expression_run VALUES(?,?,?,?,?)',(run,plan,state,json.dumps(ids),json.dumps(result)))
        return run
    def inspect(self, run):
        row=self.g.db.execute('SELECT plan,state,sentences,detail FROM expression_run WHERE id=?',(run,)).fetchone()
        if not row: raise KeyError(run)
        plan,state,ids,detail=row; sentences=[self.g.get(i) for i in json.loads(ids)]
        return {'plan':plan,'state':'stale' if any(s['status']=='stale' for s in sentences) else state,'sentences':sentences,'detail':json.loads(detail)}
