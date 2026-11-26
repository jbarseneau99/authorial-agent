"""Structural construction gate; no model calls or truth certification."""
from model import Kind

class Construction:
    def __init__(self, graph): self.g=graph
    def intent(self,text):
        if not text.strip(): raise ValueError('Empty intent')
        return self.g.add(Kind.INTENT,{'text':text})
    def claim(self,text,provenance,origin):
        if not text.strip() or not provenance or origin not in {'author','external','agent_hypothesis'}: raise ValueError('Claim provenance and origin required')
        for p in provenance:
            if self.g.get(p)['kind']!='evidence': raise ValueError('Expected evidence')
        c=self.g.add(Kind.CLAIM,{'text':text,'origin':origin,'verified':False})
        for p in set(provenance): self.g.link(c,'supports',p)
        return c
    def act(self,intent,purpose,claims):
        if self.g.get(intent)['kind']!='intent' or not purpose.strip() or not claims: raise ValueError('Intent, purpose and claims required')
        for c in claims:
            if self.g.get(c)['kind']!='claim': raise ValueError('Expected claim')
        a=self.g.add(Kind.ACT,{'purpose':purpose}); self.g.link(a,'addresses',intent)
        for c in set(claims): self.g.link(a,'asserts',c)
        return a
    def check(self,intent,acts):
        errors=[]; seen=set(); active=set()
        def visit(n):
            if n in active: errors.append('Cyclic prerequisite: '+n); return
            if n in seen: return
            active.add(n); obj=self.g.get(n); edges=self.g.prerequisites(n)
            if obj['status']=='stale': errors.append('Stale object: '+n)
            if obj['kind']=='act':
                if not obj['payload'].get('purpose') or ('addresses',intent) not in edges or not any(r=='asserts' for r,d in edges): errors.append('Incomplete act: '+n)
            if obj['kind']=='claim' and (not obj['payload'].get('origin') or not any(r=='supports' and self.g.get(d)['kind']=='evidence' for r,d in edges)): errors.append('Missing provenance: '+n)
            for r,d in edges:
                if r in {'addresses','asserts','supports','depends'}: visit(d)
            active.remove(n); seen.add(n)
        if self.g.get(intent)['kind']!='intent' or not acts or len(set(acts))!=len(acts): errors.append('Invalid plan')
        for a in acts:
            if self.g.get(a)['kind']!='act': errors.append('Expected act')
            visit(a)
        return errors
    def sentence(self,intent,plan,acts,text):
        if not text.strip() or not acts or not set(acts)<=set(plan): raise ValueError('Sentence requires planned acts')
        errors=self.check(intent,plan)
        if errors: raise ValueError('; '.join(errors))
        s=self.g.add(Kind.SENTENCE,{'text':text})
        for a in set(acts): self.g.link(s,'realizes',a)
        return s
