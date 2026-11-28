"""Revision-bound checking and reopening tickets; semantic judgments are provider supplied."""
import hashlib, json, uuid
from typing import Protocol
from expression import Expression

LAYERS={'epistemic','rhetorical','linguistic','conceptual'}
ROUTES={'epistemic':'construction','rhetorical':'construction','linguistic':'expression','conceptual':'author_review'}
RESOLVED_PROFILE='resolved-voice-v1'
class Reviewer(Protocol):
    def assess(self, context: dict) -> list: ...

class Checking:
    def __init__(self, graph, reviewer: Reviewer):
        self.g=graph; self.reviewer=reviewer; self.e=Expression(graph,None)
        graph.db.executescript('''CREATE TABLE IF NOT EXISTS assessment(id TEXT PRIMARY KEY, run TEXT, snapshot TEXT, findings TEXT, state TEXT); CREATE TABLE IF NOT EXISTS reopen_ticket(id TEXT PRIMARY KEY, assessment TEXT REFERENCES assessment(id), layer TEXT, route TEXT, state TEXT, actor TEXT);''')
    def snapshot(self,run):
        draft=self.e.inspect(run)
        if draft['state']!='draft_unvalidated': raise ValueError('Current draft required')
        paragraph=(draft.get('input') or {}).get('paragraph')
        construction=self.e.context(draft['plan'],paragraph=paragraph)
        if construction.get('execution_profile')==RESOLVED_PROFILE:
            self._sentence_records(draft,construction['acts'])
        return {'draft':draft,'construction':construction}

    def _sentence_records(self,draft,acts):
        """Expose exact text and recorded act order, with graph agreement checked."""
        supplied=draft.get('detail',{}).get('sentences')
        if not isinstance(supplied,list) or len(supplied)!=len(draft['sentences']):
            raise ValueError('Exact sentence-to-act mapping required')
        records=[]
        for sentence,original in zip(draft['sentences'],supplied):
            refs=original.get('acts') if isinstance(original,dict) else None
            if (not isinstance(refs,list) or not refs
                    or any(not isinstance(ref,str) for ref in refs)
                    or len(refs)!=len(set(refs)) or not set(refs)<=set(acts)):
                raise ValueError('Invalid recorded sentence-to-act mapping')
            graph_refs={target for relation,target in self.g.prerequisites(sentence['id'])
                        if relation=='realizes'}
            if graph_refs!=set(refs):
                raise ValueError('Sentence act mapping changed')
            records.append({'id':sentence['id'],'text':sentence['payload']['text'],
                            'acts':list(refs)})
        return records

    def reviewer_context(self,run,context):
        """Compact only the provider request; retain the complete bound snapshot."""
        if context['construction'].get('execution_profile')!=RESOLVED_PROFILE:
            return json.loads(json.dumps(context))
        construction=self.e.writer_context(context['construction'],for_review=True)
        criteria=construction.get('criteria')
        if not isinstance(criteria,list) or not criteria:
            raise ValueError('Resolved checking criteria are missing')
        draft=context['draft']
        sentences=self._sentence_records(draft,context['construction']['acts'])
        # The entire paragraph is comparison context. Make each criterion's
        # permitted targets explicit without changing canonical act scope.
        for criterion in criteria:
            criterion['target_sentence_ids']=[sentence['id'] for sentence in sentences
                                              if set(sentence['acts']) & set(criterion['act_ids'])]
        voice_ids=set(context['construction'].get('voice_evidence',{}))
        sources=[]
        for ident,record in context['construction']['nodes'].items():
            node=record['node']; payload=node['payload']
            if (ident in voice_ids or node['kind']!='evidence'
                    or payload.get('origin')!='retrieved_unverified'):
                continue
            text=payload.get('text')
            if not isinstance(text,str):
                raise ValueError('Original subject source text is required for checking')
            sources.append({'id':ident,'revision':node['revision'],
                            'origin':payload['origin'],'reference':payload.get('source'),
                            'text':text,'text_sha256':hashlib.sha256(text.encode('utf-8')).hexdigest()})
        return {'execution_profile':RESOLVED_PROFILE,
                'draft':{'run':run,'plan':draft['plan'],'text':draft['text'],
                         'text_sha256':draft['text_sha256'],
                         'sentences':sentences},
                'construction':construction,'subject_sources':sources,
                'evaluation_scope':{
                    'criteria':'Evaluate every construction.criteria item against the exact draft.',
                    'source_fidelity':'Check the original subject sources for substantive fidelity and unintended inherited phrasing or syntax. Legitimate terminology is not a defect.',
                    'voice_evidence':'Assess compliance with the explicitly selected provisional rules and their stated criteria. Preserve their recorded authority and identify genuine evidence gaps. Provisional status alone does not answer whether the draft satisfies a stated criterion.',
                    'author_validation':'Final author judgment of this new paragraph remains separate and pending; the checker does not grant it.',
                    'local_findings':'Diagnose a concrete expression or construction defect, or an evidence limitation, with exact sentence references and a specific repair or evidence needed. Do not substitute a detector prediction for a writing diagnosis.'}}

    @staticmethod
    def _valid_refs(refs,available,*,required=False):
        return (isinstance(refs,list) and (bool(refs) or not required)
                and all(isinstance(item,str) for item in refs)
                and len(refs)==len(set(refs)) and set(refs)<=available)

    def _validate_resolved_findings(self,findings,request):
        criteria=request['construction']['criteria']
        by_id={}
        for criterion in criteria:
            if (not isinstance(criterion,dict) or not isinstance(criterion.get('id'),str)
                    or not criterion['id'] or criterion['id'] in by_id
                    or criterion.get('layer') not in LAYERS
                    or not self._valid_refs(criterion.get('act_ids'),set(request['construction']['acts']),required=True)):
                raise ValueError('Invalid or duplicate declared criterion')
            by_id[criterion['id']]=criterion
        if {criterion['layer'] for criterion in criteria}!=LAYERS:
            raise ValueError('Resolved criteria must cover every authorial layer')
        sentences={sentence['id']:sentence for sentence in request['draft']['sentences']}
        seen=set()
        required={'criterion_id','status','observation','sentences','defect_type','repair'}
        for finding in findings:
            checks=finding.get('checks')
            if not isinstance(checks,list) or not checks:
                raise ValueError('Every layer requires explicit criterion checks')
            for check in checks:
                if not isinstance(check,dict) or not required<=set(check):
                    raise ValueError('Incomplete criterion check')
                ident=check['criterion_id']
                if not isinstance(ident,str) or ident not in by_id or ident in seen:
                    raise ValueError('Unknown, duplicate or missing criterion check')
                criterion=by_id[ident]
                if criterion['layer']!=finding['layer']:
                    raise ValueError('Criterion check belongs to another authorial layer')
                allowed={ident for ident,sentence in sentences.items()
                         if set(sentence['acts']) & set(criterion['act_ids'])}
                if (check['status'] not in {'pass','fail','uncertain'}
                        or not isinstance(check['observation'],str) or not check['observation'].strip()
                        or not self._valid_refs(check['sentences'],allowed,required=True)
                        or check['defect_type'] not in {'none','expression','construction','evidence_limit'}):
                    raise ValueError('Invalid criterion observation, scope or defect type')
                if check['status']=='pass':
                    if check['defect_type']!='none' or check['repair'] is not None:
                        raise ValueError('A passing criterion cannot carry an unresolved defect')
                elif (check['defect_type']=='none' or not isinstance(check['repair'],str)
                      or not check['repair'].strip()):
                    raise ValueError('A nonpassing criterion requires a diagnosis and specific repair or missing evidence')
                seen.add(ident)
            statuses={check['status'] for check in checks}
            aggregate='uncertain' if 'uncertain' in statuses else 'fail' if 'fail' in statuses else 'pass'
            if finding['status']!=aggregate:
                raise ValueError('Layer status disagrees with its criterion findings')
            selected=[check for check in checks if check['status']!='pass'] or checks
            targets={ident for check in selected for ident in check['sentences']}
            if set(finding['sentences'])!=targets:
                raise ValueError('Layer sentence references must match its unresolved criterion targets')
        if seen!=set(by_id):
            raise ValueError('Every declared criterion must be checked exactly once')

    def _validate_findings(self,findings,ctx,request):
        if not isinstance(findings,list) or len(findings)!=4 or any(not isinstance(f,dict) for f in findings) or {f.get('layer') for f in findings}!=LAYERS: raise ValueError('Exactly one finding per layer required')
        ids={s['id'] for s in ctx['draft']['sentences']}
        for f in findings:
            if f.get('status') not in {'pass','fail','uncertain'} or not isinstance(f.get('reason'),str) or not f['reason'].strip() or not self._valid_refs(f.get('sentences'),ids,required=f['status']!='pass'): raise ValueError('Invalid finding')
        if ctx['construction'].get('execution_profile')==RESOLVED_PROFILE:
            self._validate_resolved_findings(findings,request)

    @staticmethod
    def repair_route(finding,profile=None):
        """Route the object requiring repair, not the layer that detected it.

        Only the resolved profile carries validated criterion-level diagnoses.
        Legacy findings retain their original conservative layer-based routes.
        """
        if finding['status']=='pass':
            return None
        if profile!=RESOLVED_PROFILE:
            return ROUTES[finding['layer']] if finding['status']=='fail' else 'author_review'
        defects=[check for check in finding['checks'] if check['status']!='pass']
        if not defects:
            raise ValueError('A nonpassing finding requires unresolved criterion diagnoses')
        if any(check['status']=='uncertain' or check['defect_type']=='evidence_limit' for check in defects):
            return 'author_review'
        if any(check['defect_type']=='construction' for check in defects):
            return 'construction'
        if all(check['status']=='fail' and check['defect_type']=='expression' for check in defects):
            return 'expression'
        raise ValueError('Unresolved criterion diagnosis has no permitted repair route')

    def current_repair_routes(self,assessment):
        """Revalidate current criterion scopes before a repair uses stored findings."""
        ctx=self.snapshot(assessment['run'])
        snapshot=json.dumps(ctx,sort_keys=True)
        if hashlib.sha256(snapshot.encode('utf-8')).hexdigest()!=assessment['snapshot_sha256']:
            raise ValueError('Repair assessment no longer identifies the current draft and construction')
        request=self.reviewer_context(assessment['run'],ctx)
        self._validate_findings(assessment['findings'],ctx,request)
        profile=ctx['construction'].get('execution_profile')
        return {finding['layer']:self.repair_route(finding,profile)
                for finding in assessment['findings'] if finding['status']!='pass'}

    def assess(self,run):
        ctx=self.snapshot(run); request=self.reviewer_context(run,ctx)
        findings=self.reviewer.assess(json.loads(json.dumps(request)))
        self._validate_findings(findings,ctx,request)
        profile=ctx['construction'].get('execution_profile')
        ident=str(uuid.uuid4()); state='review_required' if any(f['status']!='pass' for f in findings) else 'checks_passed'
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            if self.snapshot(run)!=ctx: raise ValueError('Draft changed during review')
            self.g.db.execute('INSERT INTO assessment VALUES(?,?,?,?,?)',(ident,run,json.dumps(ctx,sort_keys=True),json.dumps(findings),state))
            for f in findings:
                if f['status']!='pass': self.g.db.execute('INSERT INTO reopen_ticket VALUES(?,?,?,?,?,NULL)',(str(uuid.uuid4()),ident,f['layer'],self.repair_route(f,profile),'proposed'))
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
