"""Prepare isolated evaluation records; live starts require committed case configs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from model import Graph
from run_agent import create_binding, read_configuration
from research_loop import BoundSources

ROOT = Path(__file__).resolve().parent


def prepare(destination):
    cases = json.loads((ROOT / 'evaluation_cases.json').read_text())['cases']
    destination.mkdir(parents=True, exist_ok=False)
    for case in cases:
        folder = destination / case['id']
        folder.mkdir()
        (folder / 'review.json').write_text(json.dumps({
            'case': case['id'], 'criteria': [{'criterion': criterion, 'judgment': None, 'evidence': None}
                                          for criterion in case['criteria']],
            'voice_fidelity': None, 'pangram_human_percent': None, 'author_approval': None,
        }, indent=2), encoding='utf-8')
    return cases


def preflight(cases, configuration_directory):
    configurations = {}
    for case in cases:
        path = configuration_directory / (case['id'] + '.json')
        config = read_configuration(path)
        if config['intent'] != case['intent'] or config.get('research') != case.get('research'):
            raise ValueError('Committed case configuration differs from evaluation intent or research: ' + case['id'])
        graph = Graph()
        try:
            binding, _ = create_binding(graph, path, ROOT.parent)
            BoundSources(binding)
        finally:
            graph.db.close()
        configurations[case['id']] = path.resolve()
    return configurations


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--config-directory', type=Path)
    args = parser.parse_args(argv)
    cases = json.loads((ROOT / 'evaluation_cases.json').read_text())['cases']
    configurations = {}
    if args.live:
        if args.config_directory is None:
            parser.error('Live evaluation requires a committed configuration for every case via --config-directory')
        try:
            configurations = preflight(cases, args.config_directory.resolve())
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    destination = args.destination.resolve()
    prepare(destination)
    if args.live:
        for case in cases:
            folder = destination / case['id']
            command = [sys.executable, str(ROOT / 'run_agent.py'), 'start', '--live',
                       '--config', str(configurations[case['id']]), '--database', str(folder / 'graph.sqlite'),
                       '--output', str(folder / 'report.json')]
            result = subprocess.run(command, cwd=ROOT)
            (folder / 'execution.json').write_text(json.dumps({
                'returncode': result.returncode,
                'scope': 'Construction start only; explicit construction closure and later author validation are separate.',
            }), encoding='utf-8')
    print('Prepared', len(cases), 'cases; human review required.')


if __name__ == '__main__':
    main()
