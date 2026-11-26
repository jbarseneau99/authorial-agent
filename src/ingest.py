"""Import a frozen workbook without silently activating candidate rules."""
import hashlib, json, uuid
from pathlib import Path
from openpyxl import load_workbook
from model import Graph

def ingest(graph, path):
    digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    w=load_workbook(path, read_only=True)
    rows={}
    for s in w:
        s.reset_dimensions(); data=list(s.values); rows[s.title]=[dict(zip(data[0],r)) for r in data[1:] if any(v is not None for v in r)]
    w.close()
    db=graph.db
    db.executescript('CREATE TABLE IF NOT EXISTS imported_baseline(digest TEXT PRIMARY KEY, manifest TEXT NOT NULL); CREATE TABLE IF NOT EXISTS imported_record(digest TEXT, sheet TEXT, record_key TEXT, node_id TEXT REFERENCES node(id), PRIMARY KEY(digest,sheet,record_key));')
    old=db.execute('SELECT manifest FROM imported_baseline WHERE digest=?',(digest,)).fetchone()
    if old: return json.loads(old[0])
    ids={}; unresolved=[]
    def node(sheet,key,kind,payload):
        ident=str(uuid.uuid5(uuid.NAMESPACE_URL,digest+":"+sheet+":"+key)); data=json.dumps(payload,default=str)
        db.execute('INSERT INTO node VALUES(?,?,1,?,?)',(ident,kind,'imported',data)); db.execute('INSERT INTO history VALUES(?,1,?)',(ident,data)); db.execute('INSERT INTO imported_record VALUES(?,?,?,?)',(digest,sheet,key,ident)); ids[(sheet,key)]=ident; return ident
    def edge(src,rel,sheet,key):
        dst=ids.get((sheet,key))
        if dst: db.execute('INSERT OR IGNORE INTO edge VALUES(?,?,?)',(src,rel,dst))
        else: unresolved.append([src,rel,sheet,key])
    with db:
        for r in rows['Source evidence']:
            key=r['Source ID']; ep=node('episodes',key,'episode',{'source':key,'date':r['Date'],'time':r['SRT time']}); ev=node('Source evidence',key,'evidence',r); db.execute('INSERT INTO edge VALUES(?,?,?)',(ev,'context',ep))
        for r in rows['Exemplars']: node('Exemplars',r['Exemplar ID'],'evidence',r)
        for r in rows['Experiments']: node('Experiments',r['Prototype'],'evidence',r)
        for r in rows['Exemplars']:
            src=ids['Exemplars',r['Exemplar ID']]; edge(src,'derived_from','Source evidence',r['Source ID']);
            if r['Parent exemplar ID']: edge(src,'derived_from','Exemplars',r['Parent exemplar ID'])
        for r in rows['Candidate rules']:
            src=node('Candidate rules',r['Rule ID'],'rule',dict(r,activation='candidate_only'))
            for ref in r['Evidence IDs'].split(';'):
                ref=ref.strip()
                if ref.startswith('Prototype '):
                    for p in ref.removeprefix('Prototype ').split('/'): edge(src,'grounded_in','Experiments',p)
                elif ref: edge(src,'grounded_in','Exemplars',ref)
        for sheet in ('Guide','Coverage','Prototype structure'):
            for i,r in enumerate(rows[sheet],1): node(sheet,str(i),'evidence',r)
        manifest={'sha256':digest,'counts':{k:len(v) for k,v in rows.items()},'unresolved':unresolved,'active_rules':0}
        db.execute('INSERT INTO imported_baseline VALUES(?,?)',(digest,json.dumps(manifest)))
    return manifest

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(); p.add_argument('workbook'); p.add_argument('database'); a=p.parse_args(); print(json.dumps(ingest(Graph(a.database),a.workbook),indent=2))
