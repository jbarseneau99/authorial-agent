from dataclasses import dataclass, field, asdict
from enum import Enum
import json, sqlite3, uuid

class Kind(str, Enum):
    INTENT='intent'; CLAIM='claim'; EVIDENCE='evidence'; ACT='act'; SENTENCE='sentence'; RULE='rule'; CHECK='check'; APPROVAL='approval'; EPISODE='episode'

# Edges point from dependent to prerequisite.
RELATIONS={'addresses':({Kind.ACT},{Kind.INTENT}), 'asserts':({Kind.ACT},{Kind.CLAIM}), 'supports':({Kind.CLAIM},{Kind.EVIDENCE,Kind.CLAIM}), 'rebuts':({Kind.CLAIM},{Kind.CLAIM}), 'realizes':({Kind.SENTENCE},{Kind.ACT}), 'applies':({Kind.SENTENCE,Kind.ACT},{Kind.RULE}), 'depends':({Kind.ACT,Kind.CLAIM},{Kind.ACT,Kind.CLAIM}), 'checks':({Kind.CHECK},{Kind.SENTENCE,Kind.ACT,Kind.CLAIM}), 'approves':({Kind.APPROVAL},{Kind.SENTENCE,Kind.ACT,Kind.CLAIM}), 'context':(set(Kind)-{Kind.EPISODE},{Kind.EPISODE})}
RELATIONS.update({'derived_from':({Kind.EVIDENCE},{Kind.EVIDENCE}), 'grounded_in':({Kind.RULE},{Kind.EVIDENCE})})
class Graph:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''CREATE TABLE IF NOT EXISTS node(id TEXT PRIMARY KEY,kind TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS history(id TEXT,revision INTEGER,payload TEXT,PRIMARY KEY(id,revision)); CREATE TABLE IF NOT EXISTS edge(src TEXT REFERENCES node(id),rel TEXT,dst TEXT REFERENCES node(id),PRIMARY KEY(src,rel,dst));''')
    def add(self,kind,payload):
        kind=Kind(kind); ident=str(uuid.uuid4()); data=json.dumps(payload)
        with self.db:
            self.db.execute('INSERT INTO node VALUES(?,?,1,?,?)',(ident,kind.value,'draft',data)); self.db.execute('INSERT INTO history VALUES(?,1,?)',(ident,data))
        return ident
    def get(self,ident):
        row=self.db.execute('SELECT kind,revision,status,payload FROM node WHERE id=?',(ident,)).fetchone()
        if row is None: raise KeyError(ident)
        return dict(id=ident,kind=row[0],revision=row[1],status=row[2],payload=json.loads(row[3]))
    def link(self,src,rel,dst):
        a,b=RELATIONS[rel]
        if Kind(self.get(src)['kind']) not in a or Kind(self.get(dst)['kind']) not in b: raise ValueError('Invalid edge types')
        with self.db: self.db.execute('INSERT INTO edge VALUES(?,?,?)',(src,rel,dst))
    def revise(self,ident,payload):
        old=self.get(ident); rev=old['revision']+1; data=json.dumps(payload)
        with self.db:
            self.db.execute('UPDATE node SET revision=?,payload=?,status=? WHERE id=?',(rev,data,'draft',ident)); self.db.execute('INSERT INTO history VALUES(?,?,?)',(ident,rev,data))
            # Conservative invalidation, including prior approvals; cycles terminate.
            self.db.execute('''WITH RECURSIVE affected(id) AS (SELECT src FROM edge WHERE dst=? UNION SELECT edge.src FROM edge JOIN affected ON edge.dst=affected.id) UPDATE node SET status='stale' WHERE id IN (SELECT id FROM affected) AND id<>?''',(ident,ident))
    def prerequisites(self,ident):
        return self.db.execute('SELECT rel,dst FROM edge WHERE src=?',(ident,)).fetchall()
    def validate_sentence(self,ident):
        if self.get(ident)['kind']!='sentence': raise ValueError('Not a sentence')
        return any(rel=='realizes' for rel,_ in self.prerequisites(ident))
