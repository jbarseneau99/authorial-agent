"""Synthetic configuration and provider integration checks for resolved voice."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from checking import Checking
from expression import Expression
from faculty import Faculty
from model import Graph
from paragraph_loop import ParagraphLoop
from pangram_check import PangramCheck
from providers import JSONModel, PROFILE_TEMPLATES
from run_agent import validate_configuration
from run_binding import ProviderJournal
from test_faculty import Research
from test_paragraph_cli import live_configuration
from test_paragraph_loop import TwoActReasoner, PipelineReviewer
from test_construction_closure import close_fixture_plan
from test_pangram_check import CONFIG, Writer
from test_providers import completion
from test_run_binding import CONFIGURATION, fixture_binding


def calibration():
    text = 'A synthetic approved passage for configuration tests only.'
    return {'id': 'fixture-reference', 'source_path': 'fixture:reference',
            'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
            'authority': 'generated_author_approved_passage', 'scope': 'passage_only',
            'author_judgment': 'Fixture approval; no claim about real author voice.'}


class ResolvedProfileCLITests(unittest.TestCase):
    def test_single_paragraph_preserves_multiple_constituent_acts(self):
        graph = Graph()
        self.addCleanup(graph.db.close)
        faculty = Faculty(graph, TwoActReasoner(), Research())
        plan = faculty.build('Synthetic grouping fixture')
        close_fixture_plan(faculty, plan)
        expression, checking = Expression(graph, Writer()), Checking(graph, PipelineReviewer())
        scanner = PangramCheck(graph, expression, checking, configuration=CONFIG,
                               transport=lambda request: None)
        loop = ParagraphLoop(graph, expression, checking, scanner,
                             paragraph_groups='all_acts_one_paragraph')
        progress = loop.prepare('fixture-execution', plan, mode='fixture')
        self.assertEqual(progress['act_groups'], [[0, 1]])
        self.assertEqual(len(progress['paragraphs']), 1)
        self.assertEqual(len(progress['paragraphs'][0]['acts']), 2)
        self.assertEqual(progress['grouping_policy'], 'all_closed_acts_in_one_paragraph')

    def test_profile_calibration_is_hash_bound_without_general_voice_promotion(self):
        config = live_configuration()
        config.update(execution_profile='resolved-voice-v1',
                      paragraph_groups='all_acts_one_paragraph',
                      written_calibration=[calibration()])
        self.assertEqual(validate_configuration(copy.deepcopy(config)), config)
        for change in (lambda c: c['written_calibration'][0].update(text='Changed'),
                       lambda c: c['written_calibration'][0].update(scope='all_future_writing'),
                       lambda c: c['written_calibration'][0].update(authority='original_author_written'),
                       lambda c: c.update(execution_profile=None),
                       lambda c: c.update(execution_profile='unknown')):
            invalid = copy.deepcopy(config)
            change(invalid)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_configuration(invalid)

    def test_resolved_profile_selects_frozen_prompt_and_journals_actual_packet(self):
        graph, binding, _ = fixture_binding(self)
        journal = ProviderJournal(graph, binding, 'construction')
        context = {'execution_profile': 'resolved-voice-v1', 'intent': 'Synthetic fixture'}
        def transport(request):
            body = json.loads(request.data)
            self.assertIn(PROFILE_TEMPLATES['resolved-voice-v1']['construction']['role'],
                          body['messages'][0]['content'])
            self.assertEqual(json.loads(body['messages'][1]['content']), context)
            self.assertEqual(journal.inspect()[0]['request'].encode(), request.data)
            return completion()
        model = JSONModel(**CONFIGURATION, transport=transport, journal=journal)
        with patch.dict('os.environ', {'TEST_KEY': 'fixture-secret-key'}):
            model.propose(context)
        self.assertEqual(journal.inspect()[0]['state'], 'succeeded')


if __name__ == '__main__':
    unittest.main()
