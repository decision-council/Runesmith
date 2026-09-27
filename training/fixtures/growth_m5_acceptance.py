"""Trainer-owned synthetic acceptance for recommendation export, before authoring."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from growthhat.cli import main
from growthhat.models import Source, Hypothesis, Test, Outcome, Recommendation
from growthhat.repository import Repository


class RecommendationExportAcceptance(unittest.TestCase):
    PUBLIC_CRITERIA = {
        'test_cli_persists_and_exports_full_provenance': ['recommendation.create', 'recommendation.export', 'recommendation.values'],
        'test_invalid_inputs_are_rejected_without_persistence': ['recommendation.validation'],
        'test_unknown_and_incomplete_links_are_explicit': ['recommendation.gaps', 'recommendation.values'],
        'test_empty_export_and_schema_are_explicit': ['recommendation.schema', 'recommendation.export'],
        'test_export_refuses_to_replace_an_existing_file': ['recommendation.local'],
    }

    def call(self, database, *args, success=True):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            try:
                result = main(['--db', str(database), *args])
            except SystemExit as error:
                result = error.code
        if success:
            self.assertEqual(result, 0, errors.getvalue())
        else:
            self.assertNotEqual(result, 0)
        return output.getvalue()

    def chain(self, database, confidence=0.0, support=False):
        repo = Repository(str(database))
        try:
            source = repo.create(Source(name='Synthetic source: Ω', notes='No real participants'))
            hypothesis = repo.create(Hypothesis(statement='Synthetic hypothesis', source_id=source.id))
            trial = repo.create(Test(hypothesis_id=hypothesis.id, name='Synthetic comparison'))
            outcome = repo.create(Outcome(test_id=trial.id, result='Not a success',
                supports_hypothesis=support, confidence=confidence))
            return source, hypothesis, trial, outcome
        finally:
            repo.close()

    def rows(self, database):
        repo = Repository(str(database))
        try:
            return repo.list_all(Recommendation)
        finally:
            repo.close()

    def test_cli_persists_and_exports_full_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'fixture.db'
            source, hypothesis, trial, outcome = self.chain(database)
            self.call(database, 'recommendation', 'add', '--title', 'Reconsider assumption',
                '--action', 'Run another local comparison', '--reasoning', 'No positive evidence',
                '--outcome-id', outcome.id, '--uncertainty-level', 'high')
            [recommendation] = self.rows(database)
            self.assertEqual(recommendation.outcome_id, outcome.id)
            self.assertEqual(recommendation.hypothesis_id, hypothesis.id)
            target = Path(directory)/'recommendations.json'
            self.call(database, 'export', 'recommendations', '--output', str(target))
            result = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(result['schema'], 'growthhat.recommendations.v1')
            [row] = result['recommendations']
            self.assertEqual(row['recommendation']['id'], recommendation.id)
            self.assertEqual(row['recommendation']['uncertainty_level'], 'high')
            self.assertEqual(row['recommendation']['action'], recommendation.action)
            self.assertEqual(row['outcome']['id'], outcome.id)
            self.assertIs(row['outcome']['supports_hypothesis'], False)
            self.assertEqual(row['outcome']['confidence'], 0.0)
            self.assertEqual(row['test']['id'], trial.id)
            self.assertEqual(row['hypothesis']['id'], hypothesis.id)
            self.assertIn(source.id, {s['id'] for s in row['sources']})
            self.assertIn(source.name, {s['name'] for s in row['sources']})
            self.assertEqual(row['missing_links'], [])
            self.assertEqual(self.rows(database), [recommendation])

    def test_invalid_inputs_are_rejected_without_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'fixture.db'
            *_, outcome = self.chain(database)
            for outcome_id, level in [('absent-fixture', 'high'), (outcome.id, 'certain')]:
                self.call(database, 'recommendation', 'add', '--title', 'Invalid', '--action', 'Nothing',
                    '--reasoning', 'Fixture', '--outcome-id', outcome_id, '--uncertainty-level', level,
                    success=False)
            self.assertEqual(self.rows(database), [])

    def test_unknown_and_incomplete_links_are_explicit(self):
        from growthhat.exporting import export_recommendations
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'fixture.db'
            _, hypothesis, _, outcome = self.chain(database, confidence=None, support=None)
            repo = Repository(str(database))
            try:
                complete = repo.create(Recommendation(title='Unknown result', action='Observe',
                    outcome_id=outcome.id, hypothesis_id=hypothesis.id))
                incomplete = repo.create(Recommendation(title='Old unlinked suggestion', action='Review'))
                by_id = {r['recommendation']['id']:r for r in export_recommendations(repo)['recommendations']}
                self.assertIsNone(by_id[complete.id]['outcome']['confidence'])
                self.assertIsNone(by_id[complete.id]['outcome']['supports_hypothesis'])
                self.assertIsNone(by_id[incomplete.id]['outcome'])
                self.assertIsNone(by_id[incomplete.id]['test'])
                self.assertIsNone(by_id[incomplete.id]['hypothesis'])
                self.assertEqual(by_id[incomplete.id]['sources'], [])
                self.assertTrue(by_id[incomplete.id]['missing_links'])
            finally:
                repo.close()

    def test_empty_export_and_schema_are_explicit(self):
        from growthhat.exporting import EXPORT_SCHEMA, export_recommendations
        repo = Repository(':memory:')
        try:
            result = export_recommendations(repo)
            self.assertEqual(result, {'schema':'growthhat.recommendations.v1', 'recommendations':[]})
            self.assertEqual(EXPORT_SCHEMA['type'], 'object')
            self.assertTrue({'schema', 'recommendations'} <= set(EXPORT_SCHEMA['required']))
            properties = EXPORT_SCHEMA['properties']
            self.assertEqual(properties['schema']['const'], result['schema'])
            self.assertEqual(properties['recommendations']['type'], 'array')
            required = properties['recommendations']['items']['required']
            self.assertTrue({'recommendation','outcome','test','hypothesis','sources','missing_links'} <= set(required))
        finally:
            repo.close()

    def test_export_refuses_to_replace_an_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'fixture.db'
            repo = Repository(str(database)); repo.close()
            target = Path(directory)/'existing.json'
            target.write_text('owner content', encoding='utf-8')
            self.call(database, 'export', 'recommendations', '--output', str(target), success=False)
            self.assertEqual(target.read_text(encoding='utf-8'), 'owner content')
