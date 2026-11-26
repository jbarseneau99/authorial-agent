"""Claim-directed research. Retrieval direction is not evidence polarity."""
import hashlib

class BilateralResearch:
    def __init__(self, provider):
        self.provider = provider
    def investigate(self, claim, support_query, challenge_query):
        if not all(isinstance(x,str) and x.strip() for x in (claim,support_query,challenge_query)) or support_query.strip().casefold()==challenge_query.strip().casefold():
            raise ValueError('Distinct explicit queries required')
        records={}; attempts=[]
        for direction,query in [('support',support_query),('challenge',challenge_query)]:
            try:
                rows=self.provider.search(query)
                attempts.append({'direction':direction,'query':query,'status':'retrieved','count':len(rows)})
                for row in rows:
                    meta=row.get('metadata',{}); doi=meta.get('doi')
                    key=doi.strip().lower() if doi else row['source']
                    if key not in records:
                        records[key]={'id':key,'source':row['source'],'text':row['text'],'metadata':meta,'directions':[],'polarity':'unassessed'}
                    if direction not in records[key]['directions']: records[key]['directions'].append(direction)
            except Exception as exc:
                attempts.append({'direction':direction,'query':query,'status':'failed','error_type':type(exc).__name__})
        return {'claim':claim,'attempts':attempts,'records':list(records.values())}

def assess(report, judgments):
    """Judgments are supplied by a reviewer, not inferred from retrieval."""
    ids={r['id'] for r in report['records']}; seen=set(); groups={}; unknown=[]
    for j in judgments:
        ident=j['id']; polarity=j['polarity']; group=j.get('origin_group')
        if ident not in ids or ident in seen or polarity not in {'supports','challenges','irrelevant','uncertain'} or not j.get('rationale','').strip(): raise ValueError('Invalid judgment')
        seen.add(ident)
        if polarity in {'supports','challenges'}:
            if not group or not j.get('dependency_basis','').strip(): unknown.append(ident)
            else: groups.setdefault(group,set()).add(polarity)
    incomplete=any(a['status']!='retrieved' for a in report['attempts']) or seen!=ids
    return {'mass':len(ids),'reviewed':len(seen),'declared_origin_groups':{k:sorted(v) for k,v in groups.items()},'unknown_independence':unknown,'status':'research_incomplete' if incomplete else 'requires_sufficiency_judgment','sufficient':None}
