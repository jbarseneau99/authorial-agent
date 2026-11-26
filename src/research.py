"""Europe PMC abstract retrieval; provenance is not independent verification."""
import json, urllib.parse, urllib.request, hashlib
from datetime import datetime, timezone

class EuropePMC:
    endpoint = 'https://www.ebi.ac.uk/europepmc/webservices/rest/search'
    def __init__(self, query=None, limit=8, transport=None):
        if not 1 <= limit <= 25: raise ValueError('Invalid result limit')
        self.query=query; self.limit=limit; self.transport=transport or self._http
    @staticmethod
    def _http(url):
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.load(r)
    def search(self, question):
        q=self.query or question
        if not q.strip(): raise ValueError('Research query required')
        url=self.endpoint+'?'+urllib.parse.urlencode({'query':q,'format':'json','resultType':'core','pageSize':self.limit})
        result=self.transport(url); records=[]; seen=set()
        for item in result['resultList']['result'][:self.limit]:
            passage=item.get('abstractText'); ident=item.get('id'); db=item.get('source'); doi=item.get('doi')
            if not passage or not ident or not db: continue
            key=doi.lower().strip() if doi else db+':'+ident
            if key in seen: continue
            seen.add(key)
            records.append({'text':passage,'source':'https://europepmc.org/article/'+urllib.parse.quote(db,safe='')+'/'+urllib.parse.quote(ident,safe=''),'metadata':{'title':item.get('title'),'doi':doi,'year':item.get('pubYear'),'query':q,'retrieved_at':datetime.now(timezone.utc).isoformat(),'passage_sha256':hashlib.sha256(passage.encode()).hexdigest(),'passage_type':'abstract','independence':'unknown','dependencies':[],'verification':'unverified'}})
        return records
