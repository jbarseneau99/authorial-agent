"""One recorded, synthetic construction-provider call; never a manuscript run."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from model import Graph
from providers import JSONModel
from run_binding import ProviderJournal, RunBinding

CONFIG = ROOT / 'verification/probes/openai-provider-v0.1.json'
SOURCE = ROOT / 'verification/probes/openai-provider-source-v0.1.txt'


def read_key(path):
    value = path.read_text(encoding='utf-8-sig').strip()
    if len(value.splitlines()) != 1:
        raise ValueError('Expected one credential value or assignment')
    assignment = re.fullmatch(r'(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*(.+)', value)
    value = assignment.group(1) if assignment else value
    parts = shlex.split(value, comments=False)
    if len(parts) != 1 or not parts[0] or any(char.isspace() for char in parts[0]):
        raise ValueError('Invalid credential value')
    return parts[0]


def validate_output(output):
    claims, acts = output.get('claims'), output.get('acts')
    if not isinstance(claims, list) or not claims or not isinstance(acts, list) or not acts:
        raise ValueError('Claims and acts required')
    keys = set()
    for claim in claims:
        if (not isinstance(claim, dict) or not isinstance(claim.get('key'), str)
                or not claim['key'].strip() or claim['key'] in keys
                or not isinstance(claim.get('text'), str) or not claim['text'].strip()
                or claim.get('origin') not in {'author', 'external', 'agent_hypothesis'}
                or not isinstance(claim.get('evidence'), list) or not claim['evidence']
                or any(ref != 'intent' for ref in claim['evidence'])):
            raise ValueError('Invalid synthetic claim or evidence reference')
        keys.add(claim['key'])
    used = set()
    for act in acts:
        if (not isinstance(act, dict) or not isinstance(act.get('purpose'), str)
                or not act['purpose'].strip() or not isinstance(act.get('claims'), list)
                or not act['claims'] or any(not isinstance(ref, str) or ref not in keys for ref in act['claims'])):
            raise ValueError('Invalid intellectual act or claim reference')
        used.update(act['claims'])
    if used != keys:
        raise ValueError('Every synthetic claim must be referenced by an act')


def write_json(destination, name, value):
    with (destination / name).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', required=True, type=Path)
    parser.add_argument('--output-directory', required=True, type=Path)
    args = parser.parse_args(argv)
    graph = journal = binding = destination = None
    destination_created = False
    previous_key = None
    key_loaded = False
    phase = 'preflight'
    report = {'probe': 'openai-provider-v0.1', 'scope': 'synthetic_provider_connectivity',
              'manuscript_generated': False, 'author_approval_requested': False,
              'author_approval_recorded': False, 'provider_invocations': 0}
    try:
        destination = args.output_directory.expanduser().resolve()
        if destination == ROOT or ROOT in destination.parents:
            raise ValueError('Diagnostic output must be outside the source checkout')
        destination.mkdir(parents=True, exist_ok=False, mode=0o700)
        destination_created = True
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        if config['prompt_templates_sha256'] != JSONModel.templates_digest():
            raise ValueError('Prompt templates differ from committed probe configuration')
        for relative in [str(CONFIG.relative_to(ROOT)), *config['sources']]:
            checked = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '--error-unmatch', '--', relative],
                                     capture_output=True, check=False)
            if checked.returncode:
                raise ValueError('Probe harness, source and configuration must be committed')
        source = SOURCE.read_text(encoding='utf-8')
        if source.strip() != 'The test object has one input and one output':
            raise ValueError('Unexpected synthetic source')
        context = {
            'intent': 'Represent only the synthetic test object as one concise claim and one ordered intellectual act.',
            'evidence': {'intent': {'text': source, 'origin': 'synthetic_probe_fixture'}},
            'voice_candidates': [],
            'probe': {'kind': 'provider_connectivity', 'synthetic': True,
                      'manuscript_generation': False, 'authorial_judgment': False},
        }
        write_json(destination, 'context.json', context)
        graph = Graph(str(destination / 'provider-probe.sqlite'))
        binding = RunBinding.create(graph, repository_root=ROOT,
            procedure_path=config['procedure'], ledger_path=config['ledger'], source_paths=config['sources'],
            providers=config['providers'], prompt_templates=JSONModel.prompt_templates(), mode='live',
            configuration_path=CONFIG)
        manifest = binding.verify()
        write_json(destination, 'binding.json', manifest)
        report.update(binding_id=binding.id, repository_commit=manifest['repository']['commit'],
                      configured_model=config['providers']['construction']['model'],
                      endpoint=config['providers']['construction']['endpoint'])
        journal = ProviderJournal(graph, binding, 'construction')
        provider = JSONModel(**config['providers']['construction'], journal=journal)
        phase = 'credential_load'
        previous_key = os.environ.get('AGENT_API_KEY')
        os.environ['AGENT_API_KEY'] = read_key(args.key_file)
        key_loaded = True
        phase = 'provider_call'
        output = provider.propose(context)
        write_json(destination, 'parsed-output.json', output)
        phase = 'output_validation'
        validate_output(output)
        binding.verify()
        report.update(status='passed', claims=len(output['claims']), acts=len(output['acts']),
                      validation='JSON response, declared claim origins, source references and act references checked')
    except Exception as exc:
        report.update(status='failed', phase=phase, error_type=type(exc).__name__,
                      reason='Probe stopped; inspect retained diagnostic evidence. No raw exception text is exposed.')
    finally:
        if key_loaded:
            if previous_key is None:
                os.environ.pop('AGENT_API_KEY', None)
            else:
                os.environ['AGENT_API_KEY'] = previous_key
        if journal is not None:
            attempts = journal.inspect()
            report['provider_invocations'] = len(attempts)
            report['invocation_states'] = [attempt['state'] for attempt in attempts]
            for attempt in attempts:
                for event in attempt['events']:
                    if event['state'] == 'response_received':
                        detail = event['detail']
                        try:
                            raw = base64.b64decode(detail['body']) if detail['format'] == 'base64' else detail['body']
                            response = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                            report['returned_model'] = response.get('model')
                            report['usage'] = response.get('usage')
                            report['response_id'] = response.get('id')
                        except (ValueError, TypeError, KeyError):
                            report['response_metadata'] = 'unavailable'
            write_json(destination, 'provider-journal.json', attempts)
        if graph is not None:
            graph.db.close()
        if destination_created:
            write_json(destination, 'report.json', report)
        print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get('status') == 'passed' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'probe': 'openai-provider-v0.1', 'status': 'failed',
                          'error_type': type(exc).__name__, 'reason': 'Diagnostic persistence failed; no exception details exposed.'}))
        raise SystemExit(1)
