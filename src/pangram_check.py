"""Revision-bound Pangram paragraph gate, with resumable one-request advances.

Pangram is an external observation, not authorial approval. Failed observations
stop progression; this module never rewrites prose or supplies detector feedback
as an expression prompt. API references: https://docs.pangram.com/quickstart-rest
and https://www.pangram.com/research/model-card/pangram-4.
"""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.request
import urllib.error
import uuid

from run_binding import canonical, contains_credential, digest


DEFAULT_CONFIGURATION = {
    'endpoint': 'https://text.external-api.pangram.com',
    'model': 'pangram-4',
    'expected_version': None,  # callers must explicitly pin the expected version
    'key_env': 'PANGRAM_API_KEY',
    'public_dashboard_link': False,
    'policy': 'all-human-v1',
    'minimum_words': 50,
}
TERMINAL = {'passed', 'flagged', 'unscorable', 'error', 'stale'}
LABEL_FIELDS = {'Human Written': 'human', 'AI-Assisted': 'ai_assisted', 'AI-Generated': 'ai'}


@dataclass(frozen=True)
class HTTPReply:
    status: int
    body: bytes


def _now():
    return datetime.now(timezone.utc).isoformat()


def validate_configuration(configuration):
    if not isinstance(configuration, dict) or set(configuration) != set(DEFAULT_CONFIGURATION):
        raise ValueError('An explicit complete Pangram configuration is required')
    if configuration['endpoint'] != DEFAULT_CONFIGURATION['endpoint']:
        raise ValueError('Pangram endpoint must be the declared official task service')
    if configuration['model'] != 'pangram-4' or configuration['public_dashboard_link'] is not False:
        raise ValueError('Explicit pangram-4 and private result handling are required')
    if configuration['policy'] != 'all-human-v1':
        raise ValueError('Unsupported Pangram gate policy')
    if not isinstance(configuration['expected_version'], str) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', configuration['expected_version']):
        raise ValueError('An exact expected detector version is required')
    if not isinstance(configuration['key_env'], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', configuration['key_env']):
        raise ValueError('Credential environment variable name required')
    if type(configuration['minimum_words']) is not int or configuration['minimum_words'] < 50:
        raise ValueError('Pangram requires at least 50 words; no padding or aggregation is permitted')
    return json.loads(canonical(configuration))


def _schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS pangram_scan(
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
            record TEXT NOT NULL, record_sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pangram_event(
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, scan TEXT NOT NULL REFERENCES pangram_scan(id),
            state TEXT NOT NULL, detail TEXT NOT NULL, recorded_at TEXT NOT NULL);
    ''')
    for table in ('pangram_scan', 'pangram_event'):
        for operation in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()}
                BEFORE {operation} ON {table} BEGIN
                SELECT RAISE(ABORT, 'Pangram evidence is append-only'); END''')
    db.commit()


class PangramCheck:
    def __init__(self, graph, expression, checking, binding=None, configuration=None, transport=None):
        self.g, self.expression, self.checking = graph, expression, checking
        self.binding = binding
        self.configuration = validate_configuration(configuration)
        self.transport = transport or self._http
        self.live_transport = transport is None
        _schema(graph.db)

    @staticmethod
    def _http(request):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return HTTPReply(response.status, response.read())
        except urllib.error.HTTPError as response:
            # Preserve response bodies for rejected/failed requests as well.
            return HTTPReply(response.code, response.read())

    def preflight(self, mode='live'):
        """No HTTP. The paragraph owner calls this before invoking the writer."""
        try:
            validate_configuration(self.configuration)
            if mode not in {'fixture', 'live'}:
                raise ValueError('Explicit live or fixture mode required')
            if mode == 'fixture' and self.live_transport:
                raise ValueError('Fixture mode requires an explicit fixture transport')
            if mode == 'live' and not self.live_transport:
                raise ValueError('Live mode requires the declared HTTP transport')
            if self.binding is not None:
                manifest = self.binding.verify()
                if manifest['mode'] != mode:
                    raise ValueError('Detector mode differs from the run binding')
            elif mode == 'live':
                raise ValueError('Live Pangram checks require the original run binding')
            if mode == 'live':
                manifest = self.binding.inspect()
                declared = manifest.get('pangram')
                if declared is None:
                    configuration = manifest.get('configuration')
                    if not configuration:
                        raise ValueError('Committed detector configuration is missing')
                    contents = configuration.get('contents')
                    declared = (contents if contents is not None else json.loads(Path(configuration['path']).read_text(encoding='utf-8'))).get('pangram')
                if declared != self.configuration:
                    raise ValueError('Pangram configuration differs from the bound configuration')
                if not os.environ.get(self.configuration['key_env']):
                    return {'state': 'blocked', 'mode': mode, 'code': 'missing_credential',
                            'reason': 'Pangram API credential is not configured in ' + self.configuration['key_env']}
            return {'state': 'ready', 'mode': mode}
        except (KeyError, OSError, TypeError, ValueError):
            # Fixed diagnostics avoid accidentally exposing a credential-bearing
            # path, request or transport exception.
            return {'state': 'blocked', 'mode': mode,
                    'reason': 'Pangram configuration, binding, transport or credential is unavailable or changed'}

    def _snapshot(self, run, assessment, mode):
        checked = self.checking.inspect(assessment)
        if checked.get('run') != run or checked.get('state') != 'checks_passed' or checked.get('tickets'):
            raise ValueError('A current passing four-layer assessment for this paragraph is required')
        if not isinstance(checked.get('snapshot_sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', checked['snapshot_sha256']):
            raise ValueError('Exact assessment snapshot identity is required')
        draft = self.expression.inspect(run)
        if draft.get('state') != 'draft_unvalidated' or not draft.get('sentences'):
            raise ValueError('A current paragraph expression is required')
        paragraph = (draft.get('input') or {}).get('paragraph') or {}
        paragraph_id = paragraph.get('id')
        if not isinstance(paragraph_id, str) or not paragraph_id.strip():
            if mode == 'live':
                raise ValueError('Live detector input requires a paragraph identity')
            paragraph_id = run
        text = draft.get('text')
        if text is None and mode == 'fixture':
            text = ' '.join(sentence['payload']['text'].strip() for sentence in draft['sentences'])
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Exact paragraph text is missing')
        text_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
        if draft.get('text_sha256', text_sha) != text_sha:
            raise ValueError('Paragraph serialization hash differs')
        return {
            'paragraph_id': paragraph_id, 'run': run, 'assessment': assessment,
            'assessment_snapshot_sha256': checked.get('snapshot_sha256'),
            'plan': draft['plan'], 'text': text, 'text_sha256': text_sha,
            'sentences': [{'id': sentence['id'], 'revision': sentence['revision'],
                           'payload_sha256': digest(sentence['payload'])} for sentence in draft['sentences']],
        }

    def _event(self, scan, state, detail):
        with self.g.db:
            self.g.db.execute('INSERT INTO pangram_event(scan,state,detail,recorded_at) VALUES(?,?,?,?)',
                              (scan, state, canonical(detail), _now()))

    def start(self, run, assessment, mode='live'):
        if mode not in {'fixture', 'live'}:
            raise ValueError('Explicit live or fixture mode required')
        snapshot = self._snapshot(run, assessment, mode)
        identity = {'snapshot': snapshot, 'mode': mode, 'configuration': self.configuration,
                    'binding_id': self.binding.id if self.binding else None}
        fingerprint = digest(identity)
        existing = self.g.db.execute('SELECT id FROM pangram_scan WHERE fingerprint=?', (fingerprint,)).fetchone()
        if existing:
            return existing[0]
        ident = str(uuid.uuid4())
        record = dict(identity, id=ident, created_at=_now())
        state, reason = 'prepared', 'Paragraph observation has not been submitted'
        if len(snapshot['text'].split()) < self.configuration['minimum_words']:
            state, reason = 'unscorable', 'Paragraph is shorter than the configured detector minimum; do not pad or combine it'
        elif self.preflight(mode)['state'] != 'ready':
            state, reason = 'error', 'Pangram preflight is blocked'
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            existing = self.g.db.execute('SELECT id FROM pangram_scan WHERE fingerprint=?', (fingerprint,)).fetchone()
            if existing:
                return existing[0]
            self.g.db.execute('INSERT INTO pangram_scan VALUES(?,?,?,?)', (ident, fingerprint, canonical(record), digest(record)))
            self.g.db.execute('INSERT INTO pangram_event(scan,state,detail,recorded_at) VALUES(?,?,?,?)',
                              (ident, state, canonical({'reason': reason}), _now()))
        return ident

    def _record(self, ident):
        row = self.g.db.execute('SELECT record,record_sha256 FROM pangram_scan WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        record = json.loads(row[0])
        if record.get('id') != ident or digest(record) != row[1]:
            raise ValueError('Corrupt Pangram scan record')
        return record

    def inspect(self, ident):
        """SELECT-only inspection; it never polls, resubmits, or creates evidence."""
        record = self._record(ident)
        events = [dict(sequence=sequence, state=state, detail=json.loads(detail), recorded_at=at)
                  for sequence, state, detail, at in self.g.db.execute(
                      'SELECT sequence,state,detail,recorded_at FROM pangram_event WHERE scan=? ORDER BY sequence', (ident,))]
        latest = events[-1] if events else {'state': 'error', 'detail': {'reason': 'Missing scan events'}}
        state = 'pending' if latest['state'] == 'request_prepared' else latest['state']
        task = next((event['detail']['task_id'] for event in reversed(events) if event['detail'].get('task_id')), None)
        full_result = next((event['detail']['result'] for event in reversed(events) if 'result' in event['detail']), None)
        reason = latest['detail'].get('reason')
        try:
            if self.configuration != record['configuration'] or (self.binding.id if self.binding else None) != record['binding_id']:
                raise ValueError('Detector binding changed')
            if self.binding is not None:
                self.binding.verify()
            if self._snapshot(record['snapshot']['run'], record['snapshot']['assessment'], record['mode']) != record['snapshot']:
                raise ValueError('Paragraph or assessment changed')
        except (KeyError, OSError, TypeError, ValueError):
            state, reason = 'stale', 'Paragraph, assessment, configuration or run binding changed'
        return {**record['snapshot'], 'id': ident, 'mode': record['mode'],
                'binding_id': record['binding_id'], 'configuration': record['configuration'],
                'state': state, 'reason': reason, 'task_id': task,
                'full_result': full_result, 'version': full_result.get('version') if isinstance(full_result, dict) else None,
                'events': events}

    def _success(self, result, snapshot):
        text = snapshot['text']
        if result.get('text') != text:
            raise ValueError('Detector returned different text')
        if result.get('version') != self.configuration['expected_version']:
            raise ValueError('Detector version differs from the bound version')
        fractions = {}
        for kind in LABEL_FIELDS.values():
            value = result.get('fraction_' + kind)
            if type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Malformed detector fractions')
            fractions[kind] = value
        if not math.isclose(sum(fractions.values()), 1.0, abs_tol=1e-6):
            raise ValueError('Detector fractions do not sum to one')
        windows = result.get('windows')
        if not isinstance(windows, list) or not windows:
            raise ValueError('Missing detector windows')
        cursor, counts, lengths = 0, dict.fromkeys(LABEL_FIELDS.values(), 0), dict.fromkeys(LABEL_FIELDS.values(), 0)
        for window in windows:
            if not isinstance(window, dict) or window.get('label') not in LABEL_FIELDS or window.get('confidence') not in {'High', 'Medium', 'Low'}:
                raise ValueError('Malformed detector window')
            start, end = window.get('start_index'), window.get('end_index')
            if type(start) is not int or type(end) is not int or start != cursor or not start < end <= len(text):
                raise ValueError('Detector windows do not cover the exact paragraph')
            if window.get('text') != text[start:end]:
                raise ValueError('Detector window text differs from the paragraph')
            kind = LABEL_FIELDS[window['label']]
            counts[kind] += 1
            lengths[kind] += end - start
            cursor = end
        if cursor != len(text):
            raise ValueError('Incomplete detector window coverage')
        for kind in LABEL_FIELDS.values():
            count = result.get('num_' + kind + '_segments')
            if type(count) is not int or count != counts[kind]:
                raise ValueError('Detector segment counts disagree')
            if not math.isclose(fractions[kind], lengths[kind] / len(text), abs_tol=1e-6):
                raise ValueError('Detector fractions disagree with segment coverage')
        # The service can return machine-scale residue for an otherwise wholly
        # human result. Account only for float representation precision; this is
        # not an acceptance threshold for a nonzero AI classification. Preserve
        # the original values in the result/event without rounding them.
        zero_ai = math.isclose(fractions['ai'], 0.0, rel_tol=0.0, abs_tol=sys.float_info.epsilon)
        zero_assisted = math.isclose(fractions['ai_assisted'], 0.0, rel_tol=0.0, abs_tol=sys.float_info.epsilon)
        all_human = math.isclose(fractions['human'], 1.0, rel_tol=0.0, abs_tol=sys.float_info.epsilon)
        return 'passed' if (zero_ai and zero_assisted and all_human
                            and counts['ai'] == 0 and counts['ai_assisted'] == 0
                            and counts['human'] == len(windows)) else 'flagged'

    def advance(self, ident):
        current = self.inspect(ident)
        if current['state'] in TERMINAL:
            return current
        if self.preflight(current['mode'])['state'] != 'ready':
            self._event(ident, 'error', {'reason': 'Pangram preflight is blocked'})
            return self.inspect(ident)
        # Serialize claiming the next request. A crash after POST preparation is
        # deliberately unresolved; an uncertain task must never be submitted twice.
        with self.g.db:
            self.g.db.execute('BEGIN IMMEDIATE')
            current = self.inspect(ident)
            if current['state'] in TERMINAL:
                return current
            if current['events'][-1]['state'] == 'request_prepared':
                return current
            task = current['task_id']
            if current['state'] == 'pending' and not task:
                raise ValueError('Pending detector task has no identity')
            method = 'GET' if task else 'POST'
            url = self.configuration['endpoint'] + '/task' + ('/' + task if task else '')
            body = None if task else canonical({'text': current['text'], 'model': self.configuration['model'], 'public_dashboard_link': False})
            request_id = str(uuid.uuid4())
            detail = {'request_id': request_id, 'method': method, 'url': url, 'body': body,
                      'binding_id': current['binding_id'], 'run': current['run'],
                      'assessment': current['assessment'], 'text_sha256': current['text_sha256']}
            if task:
                detail['task_id'] = task
            self.g.db.execute('INSERT INTO pangram_event(scan,state,detail,recorded_at) VALUES(?,?,?,?)',
                              (ident, 'request_prepared', canonical(detail), _now()))
        credential = os.environ.get(self.configuration['key_env']) if current['mode'] == 'live' else 'fixture-only-pangram-key'
        try:
            request = urllib.request.Request(url, data=body.encode('utf-8') if body else None,
                headers={'x-api-key': credential, 'Content-Type': 'application/json'}, method=method)
            reply = self.transport(request)
            http_status = reply.status if isinstance(reply, HTTPReply) else 200
            raw = reply.body if isinstance(reply, HTTPReply) else reply
            if contains_credential(raw, credential):
                self._event(ident, 'error', {'request_id': request_id, 'reason': 'Detector echoed a credential; response omitted'})
                return self.inspect(ident)
            retained = {'format': 'base64', 'body': base64.b64encode(raw).decode('ascii')} if isinstance(raw, bytes) else {
                'format': 'text' if isinstance(raw, str) else 'json', 'body': raw}
            outcome = {'request_id': request_id, 'http_status': http_status, 'raw_response': retained}
            if task:
                outcome['task_id'] = task
            try:
                if type(http_status) is not int or not 200 <= http_status < 300:
                    raise ValueError('Detector HTTP request was rejected or failed')
                result = json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if not isinstance(result, dict):
                    raise ValueError('Expected detector object response')
                outcome['result'] = result
                if method == 'POST':
                    task_id = result.get('task_id')
                    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
                        raise ValueError('Detector task identity is missing or malformed')
                    outcome.update(task_id=task_id, reason='Submitted; awaiting detector result')
                    state = 'pending'
                else:
                    if result.get('task_id', task) != task:
                        raise ValueError('Detector returned another task')
                    stage = result.get('stage')
                    if stage == 'STAGE_SUCCESS':
                        state = self._success(result, current)
                        outcome['reason'] = 'Detector observation passed the configured policy' if state == 'passed' else 'Detector flagged the paragraph; progression stops for review'
                    elif stage == 'STAGE_FAILED':
                        state = 'error'
                        outcome['reason'] = 'Detector task failed'
                    elif isinstance(stage, str) and stage.startswith('STAGE_'):
                        state = 'pending'
                        outcome['reason'] = 'Detector task remains pending'
                    else:
                        raise ValueError('Detector task stage is missing or malformed')
            except (KeyError, TypeError, ValueError) as exc:
                state = 'error'
                outcome['reason'] = str(exc) if type(exc) is ValueError else 'Malformed detector result'
            # Preserve the response while refusing it if the paragraph changed.
            after = self.inspect(ident)
            if after['state'] == 'stale':
                state, outcome['reason'] = 'stale', after['reason']
            self._event(ident, state, outcome)
        except Exception as exc:
            self._event(ident, 'error', {'request_id': request_id, 'error_type': type(exc).__name__,
                                       'reason': 'Detector request failed; no automatic resubmission'})
        return self.inspect(ident)
