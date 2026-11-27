"""Revision-bound checking and reopening tickets; semantic judgments are provider supplied."""
import hashlib, json, uuid
from typing import Protocol
from expression import Expression

LAYERS={'epistemic','rhetorical','linguistic','conceptual'}
ROUTES={'epistemic':'construction','rhetorical':'construction','linguistic':'expression','conceptual':'author_review'}
class Reviewer(Protocol):
    def assess(self, context: dict) -> list: ...

class Checking:
    def __init__(self, graph, reviewer: Reviewer):
        self.g=graph; self.reviewer=reviewer; self.e=Expression(graph,None)
        graph.db.executescript('''CREATE TABLE IF NOT EXISTS assessment(id TEXT PRIMARY KEY, run TEXT, snapshot TEXT, findings TEXT, state TEXT); CREATE TABLE IF NOT EXISTS reopen_ticket(id TEXT PRIMARY KEY, assessment TEXT REFERENCES assessment(id), layer TEXT, route TEXT, state TEXT, actor TEXT);''')
    def snapshot(self,run):
        draft=self.e.inspect(run)
        if draft['state']!='draft_unvalidated': raise ValueError('Current draft required')
        return {'draft':draft,'construction':self.e.context(draft['plan'])}
    def assess(self,run):
        ctx=self.snapshot(run); findings=self.reviewer.assess(json.loads(json.dumps(ctx)))
        if not isinstance(findings,list) or len(findings)!=4 or any(not isinstance(f,dict) for f in findings) or {f.get('layer') for f in findings}!=LAYERS: raise ValueError('Exactly one finding per layer required')
        ids={s['id'] for s in ctx['draft']['sentences']}
        for f in findings:
            if f.get('status') not in {'pass','fail','uncertain'} or not isinstance(f.get('reason'),str) or not f['reason'].strip() or not isinstance(f.get('sentences'),list) or not set(f['sentences'])<=ids or (f['status']!='pass' and not f['sentences']): raise ValueError('Invalid finding')
        ident=str(uuid.uuid4()); state='review_required' if any(f['status']!='pass' for f in findings) else 'checks_passed'
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            if self.snapshot(run)!=ctx: raise ValueError('Draft changed during review')
            self.g.db.execute('INSERT INTO assessment VALUES(?,?,?,?,?)',(ident,run,json.dumps(ctx,sort_keys=True),json.dumps(findings),state))
            for f in findings:
                if f['status']!='pass': self.g.db.execute('INSERT INTO reopen_ticket VALUES(?,?,?,?,?,NULL)',(str(uuid.uuid4()),ident,f['layer'],ROUTES[f['layer']] if f['status']=='fail' else 'author_review','proposed'))
        return ident
    def inspect(self,ident):
        row=self.g.db.execute('SELECT run,snapshot,findings,state FROM assessment WHERE id=?',(ident,)).fetchone()
        if not row: raise KeyError(ident)
        run,snapshot,findings,state=row
        try: current=json.dumps(self.snapshot(run),sort_keys=True)==snapshot
        except (ValueError, KeyError): current=False
        tickets=[dict(zip(('id','layer','route','state','actor'),r)) for r in self.g.db.execute('SELECT id,layer,route,state,actor FROM reopen_ticket WHERE assessment=?',(ident,))]
        return {'id':ident,'run':run,'snapshot_sha256':hashlib.sha256(snapshot.encode('utf-8')).hexdigest(),'state':state if current else 'stale','findings':json.loads(findings),'tickets':tickets}
    def authorize(self,ticket,actor):
        if actor!='author': raise PermissionError('Author authorization required')
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            row=self.g.db.execute('SELECT assessment,state FROM reopen_ticket WHERE id=?',(ticket,)).fetchone()
            if not row or row[1]!='proposed' or self.inspect(row[0])['state']=='stale': raise ValueError('Current proposed ticket required')
            self.g.db.execute("UPDATE reopen_ticket SET state='authorized',actor=? WHERE id=?",(actor,ticket))
