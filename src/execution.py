"""Bounded orchestration with persistent checkpoints; trusted caller authorization."""
import json, uuid
class Execution:
    def __init__(self,g,faculty,expression,checking):
        self.g=g; self.f=faculty; self.e=expression; self.c=checking
        g.db.execute('CREATE TABLE IF NOT EXISTS execution(id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    def save(self,x):
        with self.g.db: self.g.db.execute('INSERT OR REPLACE INTO execution VALUES(?,?)',(x['id'],json.dumps(x)))
    def inspect(self,i):
        r=self.g.db.execute('SELECT data FROM execution WHERE id=?',(i,)).fetchone()
        if not r: raise KeyError(i)
        x=json.loads(r[0]); a=x.get('assessment')
        if a and self.c.inspect(a)['state']=='stale': x['state']='stale'
        return x
    def start(self,intent,max_attempts=3):
        if not intent.strip() or type(max_attempts)!=int or max_attempts<1: raise ValueError('Invalid entry')
        x=dict(id=str(uuid.uuid4()),intent=intent,max_attempts=max_attempts,attempts=0,state='ready',history=[])
        self.save(x); return self.advance(x['id'])
    def advance(self,i,actor=None):
        x=self.inspect(i)
        if x['state'] not in {'ready','suspended_reopen'}: raise ValueError('Not runnable')
        if x['state']=='suspended_reopen':
            if actor!='author': raise PermissionError('Author required')
            if x['route']!='expression': raise ValueError('Intellectual revision requires explicit new construction; not automated')
            for t in self.c.inspect(x['assessment'])['tickets']: 
                if t['state']=='proposed': self.c.authorize(t['id'],actor)
        if x['attempts']>=x['max_attempts']:
            x['state']='budget_exhausted'; self.save(x); return x
        x['attempts']+=1; x['state']='running'; x.pop('assessment',None); self.save(x)
        try:
            if not x.get('plan'): x['plan']=self.f.build(x['intent']); self.save(x)
            x['run']=self.e.run(x['plan']); self.save(x)
            draft=self.e.inspect(x['run'])
            if draft['state']=='reopen_requested': x.update(state='suspended_reopen',route='construction')
            else:
                x['assessment']=self.c.assess(x['run']); result=self.c.inspect(x['assessment'])
                routes={t['route'] for t in result['tickets']}
                x.update(state='awaiting_approval' if not routes else 'suspended_reopen',route='author_review' if 'author_review' in routes else 'construction' if 'construction' in routes else 'expression' if routes else None)
        except Exception as exc:
            x.update(state='suspended_error',error=type(exc).__name__+': '+str(exc))
        x['history'].append({k:x.get(k) for k in ('attempts','plan','run','assessment','state','route')}); self.save(x); return x
    def approve(self,i,actor):
        if actor!='author': raise PermissionError('Author required')
        x=self.inspect(i)
        if x['state']!='awaiting_approval' or self.c.inspect(x['assessment'])['state']!='checks_passed': raise ValueError('Current passing assessment required')
        x.update(state='closed',approved_by=actor); self.save(x); return x
