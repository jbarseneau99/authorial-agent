"""Persistent learning workflow. Actor identity is supplied by trusted host."""
import json, uuid, hashlib
from datetime import datetime, timezone
from model import Kind

def now(): return datetime.now(timezone.utc).isoformat()
def uid(): return str(uuid.uuid4())

class Learning:
    def __init__(self, graph, author):
        self.g=graph; self.db=graph.db; self.author=author
        self.db.executescript('''CREATE TABLE IF NOT EXISTS teaching(id TEXT PRIMARY KEY, objective TEXT NOT NULL, state TEXT NOT NULL, episode TEXT, actor TEXT, opened TEXT, closed TEXT);
        CREATE TABLE IF NOT EXISTS learning_event(id TEXT PRIMARY KEY, mode TEXT NOT NULL, episode TEXT NOT NULL REFERENCES node(id), evidence TEXT NOT NULL REFERENCES node(id), session TEXT REFERENCES teaching(id), created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proposal(id TEXT PRIMARY KEY, rule_key TEXT NOT NULL, body TEXT NOT NULL, evidence TEXT NOT NULL, state TEXT NOT NULL, actor TEXT, decided TEXT);
        CREATE TABLE IF NOT EXISTS ledger_version(version INTEGER PRIMARY KEY, snapshot TEXT NOT NULL, digest TEXT NOT NULL, created TEXT NOT NULL);''')
    def _author(self,actor):
        if actor != self.author: raise PermissionError('Author approval required')
    def propose_session(self,objective):
        if not objective.strip(): raise ValueError('Objective required')
        i=uid()
        with self.db: self.db.execute('INSERT INTO teaching(id,objective,state) VALUES(?,?,?)',(i,objective,'proposed'))
        return i
    def elect(self,session,actor):
        self._author(actor)
        row=self.db.execute('SELECT objective,state FROM teaching WHERE id=?',(session,)).fetchone()
        if not row or row[1]!='proposed': raise ValueError('Session not proposed')
        ep=self.g.add(Kind.EPISODE,{'objective':row[0],'mode':'teaching','opened':now()})
        with self.db: self.db.execute('UPDATE teaching SET state=?,episode=?,actor=?,opened=? WHERE id=?',('open',ep,actor,now(),session))
        return ep
    def acquire(self,text,source,session=None):
        if not text.strip() or not source.strip(): raise ValueError('Evidence and provenance required')
        if session:
            row=self.db.execute('SELECT state,episode FROM teaching WHERE id=?',(session,)).fetchone()
            if not row or row[0]!='open': raise ValueError('Teaching session not elected or closed')
            ep=row[1]; mode='teaching'
        else:
            ep=self.g.add(Kind.EPISODE,{'mode':'feedback','opened':now()}); mode='feedback'
        ev=self.g.add(Kind.EVIDENCE,{'text':text,'source':source,'authorial_status':'unclassified'})
        self.g.link(ev,'context',ep)
        with self.db: self.db.execute('INSERT INTO learning_event VALUES(?,?,?,?,?,?)',(uid(),mode,ep,ev,session,now()))
        return ev
    def close(self,session,actor):
        self._author(actor)
        with self.db:
            c=self.db.execute("UPDATE teaching SET state='closed',closed=? WHERE id=? AND state='open'",(now(),session))
            if c.rowcount!=1: raise ValueError('Session not open')
    def propose_rule(self,key,body,evidence):
        if not key.strip() or not body.strip() or not evidence: raise ValueError('Rule and evidence required')
        for e in evidence:
            if not self.db.execute('SELECT 1 FROM learning_event WHERE evidence=?',(e,)).fetchone(): raise ValueError('Not acquired learning evidence')
        i=uid()
        with self.db: self.db.execute('INSERT INTO proposal(id,rule_key,body,evidence,state) VALUES(?,?,?,?,?)',(i,key,body,json.dumps(evidence),'proposed'))
        return i
    def snapshot(self):
        row=self.db.execute('SELECT version,snapshot FROM ledger_version ORDER BY version DESC LIMIT 1').fetchone()
        return (row[0],json.loads(row[1])) if row else (0,{})
    def decide(self,proposal,actor,approve):
        self._author(actor)
        with self.db:
            row=self.db.execute('SELECT rule_key,body,evidence,state FROM proposal WHERE id=?',(proposal,)).fetchone()
            if not row or row[3]!='proposed': raise ValueError('Proposal not pending')
            self.db.execute('UPDATE proposal SET state=?,actor=?,decided=? WHERE id=?',('approved' if approve else 'rejected',actor,now(),proposal))
            if approve:
                v,rules=self.snapshot(); rules[row[0]]={'body':row[1],'evidence':json.loads(row[2]),'proposal':proposal}
                data=json.dumps(rules,sort_keys=True); self.db.execute('INSERT INTO ledger_version VALUES(?,?,?,?)',(v+1,data,hashlib.sha256(data.encode()).hexdigest(),now()))
        return self.snapshot()[0]
