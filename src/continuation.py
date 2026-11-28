"""Pinned imports of exhausted expression work; no provider or loop execution.

Execution and ParagraphLoop own continuation. These helpers preserve a settled
source database, verify its current closed work, and record an append-only import
witness in a different database. Historical detector results are not inputs.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from checking import Checking
from construction import Construction
from editing import Editing
from expression import Expression
from model import Graph
from run_binding import RunBinding, canonical, digest


KIND = 'expression-repair-v1'
HASH_FIELDS = {'source_database_sha256', 'source_binding_sha256',
               'source_execution_sha256', 'source_progress_sha256',
               'source_construction_sha256', 'source_assessment_sha256',
               'source_text_sha256'}
ID_FIELDS = {'source_execution_id', 'source_binding_id', 'source_plan_id',
             'source_closure_id', 'source_run_id', 'source_assessment_id'}
REFERENCE_FIELDS = HASH_FIELDS | ID_FIELDS | {'kind', 'source_execution_revision'}
REGISTRATION_FIELDS = {'id', 'version', 'authorization', 'recovery_authorization',
                       'comparison', 'registration'}


def validate_reference(reference):
    if (not isinstance(reference, dict) or set(reference) != REFERENCE_FIELDS
            or reference.get('kind') != KIND
            or type(reference.get('source_execution_revision')) is not int
            or reference['source_execution_revision'] < 1
            or any(not isinstance(reference[field], str) or not reference[field].strip()
                   for field in ID_FIELDS)
            or any(not isinstance(reference[field], str)
                   or re.fullmatch(r'[0-9a-f]{64}', reference[field]) is None
                   for field in HASH_FIELDS)):
        raise ValueError('An exact versioned expression-continuation reference is required')
    return reference


def _source(graph, execution_id):
    """Use existing read-only construction, expression and editing gates."""
    row = graph.db.execute('SELECT data FROM execution WHERE id=?', (execution_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown parent execution')
    parent = json.loads(row[0])
    if parent.get('state') != 'budget_exhausted' or parent.get('execution_scope') != 'paragraphs':
        raise ValueError('Only an exhausted paragraph execution can continue')
    gate = object.__new__(Construction)
    gate.g = graph
    expression = object.__new__(Expression)
    expression.g, expression.c, expression.writer = graph, gate, None
    checking = object.__new__(Checking)
    checking.g, checking.e, checking.reviewer = graph, expression, None
    editing = object.__new__(Editing)
    editing.g, editing.expression, editing.checking = graph, expression, checking
    closure = gate.require_closed(parent['plan'])
    if closure['id'] != parent.get('closure') or closure['review'] != parent.get('construction_review'):
        raise ValueError('Parent construction closure does not match its recorded execution')
    row = graph.db.execute(
        'SELECT data FROM paragraph_checkpoint WHERE execution_id=? ORDER BY revision DESC LIMIT 1',
        (execution_id,)).fetchone()
    if row is None:
        raise ValueError('Parent paragraph evidence is missing')
    progress = json.loads(row[0])
    if (progress.get('state') != 'budget_exhausted' or progress.get('active_index') != 0
            or len(progress.get('paragraphs', [])) != 1
            or progress.get('plan') != parent['plan']
            or progress.get('mode') != parent['mode']
            or progress.get('max_attempts_per_paragraph') != parent.get('max_attempts')):
        raise ValueError('Continuation is limited to one exhausted closed paragraph')
    paragraph = progress['paragraphs'][0]
    attempts = paragraph.get('attempts', [])
    if (not attempts or len(attempts) != parent['max_attempts']
            or parent.get('attempts') != len(attempts)
            or attempts[-1].get('state') != 'expression_repair_required'
            or paragraph.get('run') != parent.get('run')
            or paragraph.get('assessment') != parent.get('assessment')
            or attempts[-1].get('run') != parent.get('run')
            or attempts[-1].get('assessment') != parent.get('assessment')
            or paragraph.get('scan') is not None):
        raise ValueError('A final diagnosed expression repair with its full attempt history is required')
    assessment = editing._current(parent['run'], parent['assessment'])
    draft = expression.inspect(parent['run'])
    scope = {'id': paragraph['id'], 'index': 0, 'acts': paragraph['acts'], 'prior_paragraphs': []}
    if (draft['state'] != 'draft_unvalidated' or draft['plan'] != parent['plan']
            or (draft.get('input') or {}).get('paragraph') != scope):
        raise ValueError('Parent exact draft or paragraph scope is no longer current')
    manifest = RunBinding.load(graph, parent['binding_id']).inspect()
    if manifest['mode'] != parent['mode'] or not (manifest.get('configuration') or {}).get('contents'):
        raise ValueError('Parent requires its original declared configuration and binding')
    if manifest['configuration']['contents'].get('max_attempts', 3) != parent['max_attempts']:
        raise ValueError('Parent attempt budget differs from its original configuration')
    return {'execution': parent, 'progress': progress, 'closure': closure,
            'construction': gate.snapshot(parent['plan']), 'draft': draft,
            'assessment': assessment, 'manifest': manifest}


def _reference(source, database_sha256):
    parent = source['execution']
    return {'kind': KIND, 'source_database_sha256': database_sha256,
            'source_execution_id': parent['id'], 'source_execution_revision': parent['revision'],
            'source_execution_sha256': digest(parent), 'source_binding_id': parent['binding_id'],
            'source_binding_sha256': digest(source['manifest']),
            'source_progress_sha256': digest(source['progress']),
            'source_plan_id': parent['plan'], 'source_closure_id': parent['closure'],
            'source_construction_sha256': digest(source['construction']),
            'source_run_id': parent['run'], 'source_assessment_id': parent['assessment'],
            'source_assessment_sha256': digest(source['assessment']),
            'source_text_sha256': source['draft']['text_sha256']}


def _database_hash(path):
    if not path.is_file():
        raise ValueError('Source execution database does not exist')
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Use a settled source database without an uncheckpointed WAL')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def _read_only(path):
    graph = object.__new__(Graph)
    graph.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    return graph


def continuation_reference(database, execution_id):
    """Return registration data without writing to the source or calling providers."""
    path = Path(database).resolve()
    fingerprint = _database_hash(path)
    graph = _read_only(path)
    with closing(graph.db):
        reference = _reference(_source(graph, execution_id), fingerprint)
    if _database_hash(path) != fingerprint:
        raise ValueError('Source database changed during inspection')
    return reference


def copy_source_database(source_database, destination_database, reference):
    """Create a new database via SQLite backup and append a pinned import witness."""
    validate_reference(reference)
    source, destination = Path(source_database).resolve(), Path(destination_database).resolve()
    if source == destination or destination.exists():
        raise ValueError('Continuation requires a new, different database path')
    actual = continuation_reference(source, reference['source_execution_id'])
    if actual != reference:
        raise ValueError('Source database differs from the committed continuation reference')
    # Exclusive creation prevents accidentally replacing any prior experiment.
    with destination.open('xb'):
        pass
    graph = _read_only(source)
    try:
        with closing(graph.db), closing(sqlite3.connect(destination)) as copied:
            graph.db.backup(copied)
            target = object.__new__(Graph)
            target.db = copied
            if (_reference(_source(target, reference['source_execution_id']), actual['source_database_sha256']) != reference
                    or _database_hash(source) != actual['source_database_sha256']):
                raise ValueError('Source database changed while its snapshot was copied')
            copied.executescript('''
                CREATE TABLE IF NOT EXISTS continuation_snapshot(
                    id TEXT PRIMARY KEY, reference TEXT NOT NULL,
                    source_path TEXT NOT NULL, recorded_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS continuation_snapshot_no_update
                    BEFORE UPDATE ON continuation_snapshot BEGIN
                    SELECT RAISE(ABORT, 'Continuation evidence is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS continuation_snapshot_no_delete
                    BEFORE DELETE ON continuation_snapshot BEGIN
                    SELECT RAISE(ABORT, 'Continuation evidence is append-only'); END;
            ''')
            with copied:
                copied.execute('INSERT INTO continuation_snapshot VALUES(?,?,?,?)',
                               (str(uuid.uuid4()), canonical(reference), str(source),
                                datetime.now(timezone.utc).isoformat()))
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return reference


def imported_source(graph, reference):
    validate_reference(reference)
    if not graph.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='continuation_snapshot'").fetchone():
        raise ValueError('A pinned source database import is required')
    receipt = graph.db.execute('SELECT source_path FROM continuation_snapshot WHERE reference=?',
                               (canonical(reference),)).fetchone()
    database = next(row[2] for row in graph.db.execute('PRAGMA database_list') if row[1] == 'main')
    if not receipt or not database or Path(database).resolve() == Path(receipt[0]).resolve():
        raise ValueError('Continuation must use its separately imported source snapshot')
    source = _source(graph, reference['source_execution_id'])
    if _reference(source, reference['source_database_sha256']) != reference:
        raise ValueError('Imported parent work differs from the committed continuation reference')
    return source


def validate_binding(parent, current, reference):
    """Permit a new code binding and budget, not a new writing treatment."""
    old = parent['configuration']['contents']
    new = (current.get('configuration') or {}).get('contents')
    if not isinstance(new, dict) or new.get('continuation') != reference:
        raise ValueError('The new binding must commit its exact continuation reference')
    ignored = REGISTRATION_FIELDS | {'max_attempts', 'continuation'}
    if {k: v for k, v in old.items() if k not in ignored} != {k: v for k, v in new.items() if k not in ignored}:
        raise ValueError('Continuation may change only registration, authorization, parent references and total budget')
    if (current['id'] == parent['id'] or current['mode'] != parent['mode']
            or type(new.get('max_attempts')) is not int
            or new['max_attempts'] <= old.get('max_attempts', 3)):
        raise ValueError('Continuation requires a new binding and an extended total attempt budget')
    for key in ('providers', 'prompt_templates', 'prompt_templates_sha256'):
        if current[key] != parent[key]:
            raise ValueError('Continuation must preserve parent provider configuration and prompts')
    for key in ('procedure', 'ledger'):
        if current[key]['sha256'] != parent[key]['sha256']:
            raise ValueError('Continuation must preserve the bound procedure and ledger')
    for key in ('sources', 'procedure_addenda'):
        if [item['sha256'] for item in current.get(key, [])] != [item['sha256'] for item in parent.get(key, [])]:
            raise ValueError('Continuation must preserve bound sources and procedure addenda')
