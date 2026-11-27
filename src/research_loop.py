"""Research-loop owner; retrieval does not confer evidential closure."""
import hashlib
import json
from pathlib import Path
import uuid
from governance import BilateralResearch


class ResearchBridge:
    def __init__(self, provider, support, challenge, graph=None, binding=None):
        if not isinstance(support, str) or not support.strip() or not isinstance(challenge, str) or not challenge.strip():
            raise ValueError('Both bilateral research queries are required')
        self.provider, self.support, self.challenge = provider, support, challenge
        self.graph, self.binding = graph, binding
        self.report = None
        if graph is not None:
            graph.db.execute('''CREATE TABLE IF NOT EXISTS research_run_event(
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT NOT NULL,
                binding TEXT, state TEXT NOT NULL, detail TEXT NOT NULL)''')

    def _record(self, run, state, detail):
        if self.graph is not None:
            with self.graph.db:
                self.graph.db.execute('INSERT INTO research_run_event(run,binding,state,detail) VALUES(?,?,?,?)',
                    (run, self.binding.id if self.binding else None, state, json.dumps(detail)))

    def search(self, intent):
        if self.binding:
            self.binding.verify()
        ident = str(uuid.uuid4())
        self._record(ident, 'retrieving', {'intent': intent, 'support': self.support, 'challenge': self.challenge})
        try:
            self.report = BilateralResearch(self.provider).investigate(intent, self.support, self.challenge)
            self._record(ident, 'retrieved', self.report)
            if any(attempt['status'] != 'retrieved' for attempt in self.report['attempts']):
                raise RuntimeError('Bilateral retrieval incomplete')
            return [dict(text=record['text'], source=record['source'], metadata=dict(
                record['metadata'], directions=record['directions'], polarity='unassessed'))
                for record in self.report['records']]
        except Exception as exc:
            self._record(ident, 'unresolved', {'error_type': type(exc).__name__})
            raise RuntimeError('Research retrieval unresolved; see research evidence') from None


class BoundSources:
    """Read exact bound text artifacts and optionally add bilateral retrieval."""
    def __init__(self, binding, research=None):
        self.binding, self.research = binding, research
        self.report = None
        self.records = self._read()

    def _read(self):
        manifest = self.binding.verify()
        records = []
        for item in manifest['sources']:
            path = Path(item['path'])
            if path.suffix.lower() not in {'.txt', '.md'}:
                raise ValueError('Source artifacts must be prepared UTF-8 .txt or .md files')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('Source artifact changed during reading')
            text = raw.decode('utf-8', errors='strict')
            if not text.strip() or '\x00' in text:
                raise ValueError('Source artifact is empty or contains binary text')
            records.append({'text': text, 'source': str(path), 'metadata': {
                'sha256': item['sha256'], 'origin': 'supplied_bound_source',
                'binding': self.binding.id, 'polarity': 'unassessed'}})
        return records

    def search(self, intent):
        self.records = self._read()
        additional = self.research.search(intent) if self.research else []
        self.report = {'bound_sources': [dict(source=item['source'], metadata=item['metadata']) for item in self.records],
                       'retrieval': getattr(self.research, 'report', None),
                       'evidence_status': 'retrieval is not verification or construction closure'}
        return self.records + additional
