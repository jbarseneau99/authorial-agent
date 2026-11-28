"""Inspect and advance the existing Execution through explicit bound commands."""
import argparse
import json
from pathlib import Path
import sqlite3

from model import Graph
from ingest import ingest
from faculty import Faculty
from expression import Expression
from checking import Checking
from construction import Construction
from execution import Execution
from providers import JSONModel
from research import EuropePMC
from research_loop import BoundSources, ResearchBridge  # compatibility export
from run_binding import PARAGRAPH_ADDENDUM, ProviderJournal, RunBinding
from pangram_check import PangramCheck, validate_configuration as validate_pangram_configuration
from paragraph_loop import ParagraphLoop

ROOT = Path(__file__).resolve().parent.parent


def validate_configuration(config):
    if not isinstance(config, dict) or config.get('mode') != 'live':
        raise ValueError('Committed configuration must declare live mode')
    if not isinstance(config.get('intent'), str) or not config['intent'].strip():
        raise ValueError('Author intent is required in the committed configuration')
    if config.get('paragraph_mode') != 'pangram-gated-v1':
        raise ValueError('New live runs require paragraph_mode="pangram-gated-v1"')
    validate_pangram_configuration(config.get('pangram'))
    if config.get('procedure_addenda') != [PARAGRAPH_ADDENDUM]:
        raise ValueError('Bind the author-directed paragraph Pangram addendum')
    groups = config.get('paragraph_groups')
    if groups is not None and groups != 'all_acts_one_paragraph':
        if (not isinstance(groups, list) or not groups
                or any(not isinstance(group, list) or not group for group in groups)
                or any(type(index) is not int for group in groups for index in group)):
            raise ValueError('Paragraph groups must contain ordered integer act indices')
        flat = [index for group in groups for index in group]
        if flat != list(range(len(flat))):
            raise ValueError('Paragraph groups must cover act indices exactly once in order')
    for field in ('procedure', 'ledger', 'prompt_templates_sha256'):
        if not isinstance(config.get(field), str) or not config[field].strip():
            raise ValueError('Configuration requires ' + field)
    if not isinstance(config.get('sources'), list) or not config['sources'] or any(not isinstance(path, str) for path in config['sources']):
        raise ValueError('Bound source paths are required')
    if not isinstance(config.get('providers'), dict) or set(config['providers']) != {'construction', 'expression', 'checking'}:
        raise ValueError('Declare construction, expression and checking providers')
    research = config.get('research')
    if research is not None and (not isinstance(research, dict) or set(research) != {'support', 'challenge'}
            or any(not isinstance(value, str) or not value.strip() for value in research.values())):
        raise ValueError('Research requires both support and challenge queries')
    selected = config.get('selected_rule_ids')
    if selected is not None and (not isinstance(selected, list) or any(not isinstance(value, str) or not value.strip() for value in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError('Selected rule IDs must be a unique list')
    profile = config.get('execution_profile')
    if profile not in {None, 'resolved-voice-v1'}:
        raise ValueError('Unsupported execution profile')
    if profile == 'resolved-voice-v1':
        from voice_resolution import validate_written_calibration
        validate_written_calibration(config.get('written_calibration', []))
    elif config.get('written_calibration'):
        raise ValueError('Written calibration requires the resolved voice profile')
    budget = config.get('max_attempts', 3)
    if type(budget) is not int or budget < 1:
        raise ValueError('Positive attempt budget required')
    if config['prompt_templates_sha256'] != JSONModel.templates_digest():
        raise ValueError('Configuration prompt templates differ from this runtime')
    return config


def read_configuration(path):
    return validate_configuration(json.loads(Path(path).read_text(encoding='utf-8')))


def create_binding(graph, configuration_path, repository_root=ROOT):
    config = read_configuration(configuration_path)
    binding = RunBinding.create(graph, repository_root=repository_root,
        procedure_path=config['procedure'], ledger_path=config['ledger'], source_paths=config['sources'],
        providers=config['providers'], prompt_templates=JSONModel.prompt_templates(),
        mode='live', configuration_path=configuration_path, addenda_paths=config['procedure_addenda'])
    return binding, config


def runtime(graph, binding, config=None):
    manifest = binding.verify()
    if manifest['mode'] != 'live':
        raise ValueError('The CLI requires a live binding; fixtures use the test API')
    frozen = read_configuration(manifest['configuration']['path'])
    if config is not None and config != frozen:
        raise ValueError('Runtime configuration differs from the original binding')
    config = frozen
    models = {role: JSONModel(**configuration, journal=ProviderJournal(graph, binding, role))
              for role, configuration in manifest['providers'].items()}
    research = config.get('research')
    bridge = ResearchBridge(EuropePMC(), research['support'], research['challenge'], graph, binding) if research else None
    sources = BoundSources(binding, bridge)
    faculty = Faculty(graph, models['construction'], sources, baseline_digest=manifest['ledger']['sha256'],
                      rule_ids=config.get('selected_rule_ids'),
                      execution_profile=config.get('execution_profile'),
                      written_calibration=config.get('written_calibration', []))
    expression = Expression(graph, models['expression'])
    checking = Checking(graph, models['checking'])
    detector = PangramCheck(graph, expression, checking, binding=binding, configuration=config['pangram'])
    paragraphs = ParagraphLoop(graph, expression, checking, detector,
                               paragraph_groups=config.get('paragraph_groups'),
                               max_attempts=config.get('max_attempts', 3))
    engine = Execution(graph, faculty, expression, checking, binding=binding, paragraph_loop=paragraphs)
    return engine, sources, config


def execute(graph, intent, constructor, writer, reviewer, research, *, binding=None, mode='live',
            max_attempts=3, selected_rule_ids=None, pangram_configuration=None,
            paragraph_groups=None, detector_transport=None):
    """Test/service API. Production callers must supply a verified binding."""
    baseline = binding.inspect()['ledger']['sha256'] if binding is not None else None
    expression, checking = Expression(graph, writer), Checking(graph, reviewer)
    paragraphs = None
    if pangram_configuration is not None:
        detector = PangramCheck(graph, expression, checking, binding=binding,
                               configuration=pangram_configuration, transport=detector_transport)
        paragraphs = ParagraphLoop(graph, expression, checking, detector,
                                   paragraph_groups=paragraph_groups, max_attempts=max_attempts)
    engine = Execution(graph, Faculty(graph, constructor, research, baseline_digest=baseline, rule_ids=selected_rule_ids),
                       expression, checking, binding=binding, paragraph_loop=paragraphs)
    result = engine.start(intent, max_attempts=max_attempts, mode=mode)
    if getattr(research, 'report', None) is not None:
        result['research_report'] = research.report
    return result


def inspect_execution(graph, ident):
    """SELECT-only report; accepts a read-only connection and never builds providers."""
    row = graph.db.execute('SELECT data FROM execution WHERE id=?', (ident,)).fetchone()
    if row is None:
        raise KeyError(ident)
    result = {'execution': json.loads(row[0])}
    execution = result['execution']
    result['current_state'] = execution['state']
    # Read-only views reuse existing gate logic without constructors that create
    # tables. No provider or alternate validation implementation is involved.
    gate = object.__new__(Construction)
    gate.g = graph
    expression = object.__new__(Expression)
    expression.g, expression.c = graph, gate
    checking = object.__new__(Checking)
    checking.g, checking.e = graph, expression
    result['history'] = [json.loads(row[0]) for row in graph.db.execute(
        'SELECT data FROM execution_revision WHERE execution_id=? ORDER BY revision', (ident,))]
    if execution.get('plan'):
        row = graph.db.execute('SELECT intent,acts,context,state FROM construction_plan WHERE id=?', (execution['plan'],)).fetchone()
        result['construction'] = {'id': execution['plan'], 'intent': row[0], 'acts': json.loads(row[1]),
                                  'context': json.loads(row[2]), 'state': row[3]} if row else None
    if execution.get('construction_review'):
        row = graph.db.execute('SELECT snapshot,findings,state FROM construction_review WHERE id=?', (execution['construction_review'],)).fetchone()
        result['construction_review'] = {'snapshot': json.loads(row[0]), 'findings': json.loads(row[1]), 'state': row[2]} if row else None
    if execution.get('closure'):
        row = graph.db.execute('SELECT plan,review,snapshot,actor,authority FROM construction_closure WHERE id=?', (execution['closure'],)).fetchone()
        result['construction_closure'] = dict(zip(('plan', 'review', 'snapshot', 'actor', 'authority'), row)) if row else None
        if row:
            result['construction_closure']['snapshot'] = json.loads(row[2])
    if execution.get('run'):
        row = graph.db.execute('SELECT plan,state,sentences,detail FROM expression_run WHERE id=?', (execution['run'],)).fetchone()
        result['draft'] = {'plan': row[0], 'state': row[1], 'sentences': [graph.get(item) for item in json.loads(row[2])],
                           'detail': json.loads(row[3])} if row else None
    if execution.get('assessment'):
        row = graph.db.execute('SELECT snapshot,findings,state FROM assessment WHERE id=?', (execution['assessment'],)).fetchone()
        result['assessment'] = {'snapshot': json.loads(row[0]), 'findings': json.loads(row[1]), 'state': row[2]} if row else None
    try:
        if execution.get('construction_review') and gate.inspect_review(execution['construction_review'])['state'] == 'stale':
            result['current_state'] = 'stale'
        if execution.get('closure'):
            gate.require_closed(execution['plan'])
        if execution.get('assessment') and checking.inspect(execution['assessment'])['state'] == 'stale':
            result['current_state'] = 'stale'
    except (KeyError, ValueError):
        result['current_state'] = 'stale'
    if execution.get('binding_id'):
        binding = RunBinding.load(graph, execution['binding_id'])
        result['binding'] = binding.inspect()
        try:
            binding.verify()
            result['binding_verification'] = {'state': 'current'}
        except (OSError, ValueError) as exc:
            result['binding_verification'] = {'state': 'changed_or_unavailable', 'reason': str(exc)}
            result['current_state'] = 'binding_changed'
        result['provider_invocations'] = {role: ProviderJournal(graph, binding, role).inspect()
                                          for role in result['binding']['providers']}
    else:
        result['binding_verification'] = {'state': 'unbound_fixture' if execution.get('mode') == 'fixture' else 'missing'}
    if execution.get('execution_scope') == 'paragraphs':
        # Reuse SELECT-only inspection helpers. Do not instantiate HTTP providers
        # or schema-writing constructors for inspection.
        row = graph.db.execute(
            'SELECT data FROM paragraph_checkpoint WHERE execution_id=? ORDER BY revision DESC LIMIT 1',
            (ident,)).fetchone()
        if row:
            stored = json.loads(row[0])
            scanner = object.__new__(PangramCheck)
            scanner.g, scanner.expression, scanner.checking = graph, expression, checking
            scanner.binding = binding if execution.get('binding_id') else None
            scan_id = next((p.get('scan') for p in stored['paragraphs'] if p.get('scan')), None)
            if scan_id:
                scan_record = json.loads(graph.db.execute('SELECT record FROM pangram_scan WHERE id=?', (scan_id,)).fetchone()[0])
                scanner.configuration = scan_record['configuration']
            elif execution.get('binding_id'):
                scanner.configuration = binding.inspect()['configuration']['contents']['pangram']
            else:
                scanner.configuration = {}
            loop = object.__new__(ParagraphLoop)
            loop.g, loop.expression, loop.checking, loop.pangram = graph, expression, checking, scanner
            result['paragraph_progress'] = loop.inspect(ident)
            result['paragraph_history'] = loop.history(ident)
            result['pangram_scans'] = [scanner.inspect(p['scan']) for p in stored['paragraphs'] if p.get('scan')]
            if result['paragraph_progress']['state'] == 'stale':
                result['current_state'] = 'stale'
    result['report_scope'] = 'Stored execution evidence plus structural freshness checks; provider judgments do not establish semantic correctness or authorial approval.'
    return result


def _read_only_graph(database):
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError('Execution database does not exist')
    graph = object.__new__(Graph)
    graph.db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    return graph


def _report(graph, ident, output):
    report = inspect_execution(graph, ident)
    if output:
        destination = Path(output)
        with destination.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, indent=2)
        print(str(destination.resolve()))
    else:
        print(json.dumps(report, indent=2))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    start = commands.add_parser('start')
    start.add_argument('--config', required=True, type=Path)
    start.add_argument('--database', required=True, type=Path)
    start.add_argument('--live', action='store_true')
    start.add_argument('--output', type=Path)
    for name in ('inspect', 'review-construction', 'close-construction', 'resume', 'approve'):
        command = commands.add_parser(name)
        command.add_argument('--database', required=True, type=Path)
        command.add_argument('--execution', required=True)
        command.add_argument('--output', type=Path)
        if name in {'review-construction', 'resume'}:
            command.add_argument('--live', action='store_true')
        if name in {'close-construction', 'approve'}:
            command.add_argument('--actor', choices=['author'], required=True)
        elif name == 'resume':
            command.add_argument('--actor', choices=['author'])
    args = parser.parse_args(argv)
    if args.command in {'start', 'resume', 'review-construction'} and not args.live:
        parser.error('Explicit --live required for commands that may call providers')
    if args.output and args.output.exists():
        parser.error('Report already exists; choose a new output version')
    graph = None
    try:
        if args.command == 'inspect':
            graph = _read_only_graph(args.database)
            return _report(graph, args.execution, args.output)
        if args.command != 'start' and not args.database.is_file():
            raise ValueError('Execution database does not exist')
        if args.command == 'start':
            # Validate before creating a database or constructing providers.
            read_configuration(args.config)
            graph = Graph(str(args.database))
            binding, config = create_binding(graph, args.config)
            BoundSources(binding)  # reject binary/missing sources before ingest or model use
            ingest(graph, binding.inspect()['ledger']['path'])
            engine, research, config = runtime(graph, binding, config)
            result = engine.start(config['intent'], max_attempts=config.get('max_attempts', 3), mode='live')
        else:
            graph = Graph(str(args.database))
            row = graph.db.execute('SELECT data FROM execution WHERE id=?', (args.execution,)).fetchone()
            if row is None:
                raise ValueError('Unknown execution')
            original = json.loads(row[0])
            if not original.get('binding_id'):
                raise ValueError('Resume requires the original live run binding')
            binding = RunBinding.load(graph, original['binding_id'])
            engine, _, _ = runtime(graph, binding)
            if args.command == 'review-construction':
                result = engine.review_construction(args.execution)
            elif args.command == 'close-construction':
                result = engine.close_construction(args.execution, actor=args.actor)
            elif args.command == 'resume':
                result = engine.advance(args.execution, actor=args.actor)
            else:
                result = engine.approve(args.execution, actor=args.actor)
        return _report(graph, result['id'], args.output)
    except (KeyError, OSError, ValueError, RuntimeError, sqlite3.DatabaseError) as exc:
        parser.error(str(exc))
    finally:
        if graph is not None:
            graph.db.close()


if __name__ == '__main__':
    main()
