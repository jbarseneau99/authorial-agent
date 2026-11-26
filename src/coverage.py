"""Coverage inventory; counts are not measures of fidelity."""
import json
from collections import defaultdict
LAYERS=('Conceptual','Epistemic','Rhetorical','Linguistic')
def layers(value):
    return {x.strip().title() for x in (value or '').split(';')} & set(LAYERS)
def assess(graph,digest):
    db=graph.db
    if not db.execute('SELECT 1 FROM imported_baseline WHERE digest=?',(digest,)).fetchone(): raise ValueError('Unknown baseline')
    result={k:{'exemplars':0,'sources':set(),'acts':defaultdict(int),'written_validated':0,'candidate_rules':0,'active_rules':0} for k in LAYERS}
    rule_ids=set(); unclassified=0
    for sheet,raw in db.execute('SELECT sheet,payload FROM imported_record JOIN node ON node_id=id WHERE digest=?',(digest,)):
        p=json.loads(raw)
        if sheet=='Candidate rules': rule_ids.add(p['Rule ID'])
        for layer in layers(p.get('Layer')):
            r=result[layer]
            if sheet=='Exemplars':
                r['exemplars']+=1; r['sources'].add(p['Source ID']); r['acts'][p['Intellectual act']]+=1
                r['written_validated']+=int(p.get('Exemplar type')=='Author-validated written')
            elif sheet=='Candidate rules': r['candidate_rules']+=1
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'learning_event' in tables:
        for ep,raw in db.execute('SELECT episode,payload FROM learning_event JOIN node ON evidence=node.id'):
            p=json.loads(raw); ls=layers(p.get('Layer'))
            if not ls: unclassified+=1
            for layer in ls:
                r=result[layer]; r['exemplars']+=1; r['sources'].add(ep); r['acts'][p.get('Intellectual act','unspecified')]+=1
                r['written_validated']+=int(p.get('Exemplar type')=='Author-validated written')
    for r in result.values(): r['sources']=len(r['sources']); r['acts']=dict(r['acts'])
    return result

def objectives(report):
    return [{'layer':k,'objective':f'Acquire author-written or author-validated examples of {k.lower()} behavior through a focused exercise.', 'reason':'No classified author-validated written exemplars'} for k,r in report.items() if not r['written_validated']]
def propose_teaching(learning, objective): return learning.propose_session(objective['objective'])
if __name__=='__main__':
    import argparse
    from model import Graph
    p=argparse.ArgumentParser(); p.add_argument('database'); p.add_argument('digest'); a=p.parse_args(); r=assess(Graph(a.database),a.digest); print(json.dumps({'coverage':r,'objectives':objectives(r)},indent=2))
