"""Unit tests for Outcome confidence field and migration."""

import os
import sqlite3
import tempfile
import unittest

from growthhat.models import Hypothesis, Outcome, Test
from growthhat.repository import Repository


class TestConfidenceStorage(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def _make_test(self, repo):
        hyp = repo.create(Hypothesis(statement="H"))
        return repo.create(Test(hypothesis_id=hyp.id, name="T"))

    def test_confidence_roundtrip_after_reopen(self):
        repo = Repository(self.temp_path)
        test = self._make_test(repo)
        outcome = repo.create(Outcome(test_id=test.id, result="Worked", confidence=0.75))
        repo.close()

        repo2 = Repository(self.temp_path)
        loaded = repo2.get(Outcome, outcome.id)
        repo2.close()
        self.assertEqual(loaded.confidence, 0.75)
        self.assertEqual(loaded.result, "Worked")

    def test_confidence_none_stays_none(self):
        repo = Repository(self.temp_path)
        test = self._make_test(repo)
        outcome = repo.create(Outcome(test_id=test.id, result="Unknown"))
        loaded = repo.get(Outcome, outcome.id)
        repo.close()
        self.assertIsNone(loaded.confidence)

    def test_confidence_zero_preserved(self):
        repo = Repository(self.temp_path)
        test = self._make_test(repo)
        outcome = repo.create(Outcome(test_id=test.id, result="No signal", confidence=0.0))
        loaded = repo.get(Outcome, outcome.id)
        repo.close()
        self.assertIsNotNone(loaded.confidence)
        self.assertEqual(loaded.confidence, 0.0)

    def test_confidence_one_accepted(self):
        repo = Repository(self.temp_path)
        test = self._make_test(repo)
        outcome = repo.create(Outcome(test_id=test.id, confidence=1))
        loaded = repo.get(Outcome, outcome.id)
        repo.close()
        self.assertEqual(loaded.confidence, 1.0)

    def test_supports_hypothesis_false_vs_none_preserved(self):
        repo = Repository(self.temp_path)
        test = self._make_test(repo)
        false_outcome = repo.create(Outcome(
            test_id=test.id, supports_hypothesis=False, confidence=0.3))
        none_outcome = repo.create(Outcome(
            test_id=test.id, supports_hypothesis=None, confidence=0.4))
        loaded_false = repo.get(Outcome, false_outcome.id)
        loaded_none = repo.get(Outcome, none_outcome.id)
        repo.close()
        self.assertFalse(loaded_false.supports_hypothesis)
        self.assertIsNone(loaded_none.supports_hypothesis)


class TestConfidenceValidation(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)
        self.repo = Repository(self.temp_path)
        hyp = self.repo.create(Hypothesis(statement="H"))
        self.test = self.repo.create(Test(hypothesis_id=hyp.id, name="T"))

    def tearDown(self):
        self.repo.close()
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def _assert_rejected(self, confidence, exc_type):
        with self.assertRaises(exc_type):
            self.repo.create(Outcome(test_id=self.test.id, confidence=confidence))
        # Nothing inserted
        self.assertEqual(len(self.repo.list_all(Outcome)), 0)

    def test_rejects_nan(self):
        self._assert_rejected(float("nan"), ValueError)

    def test_rejects_positive_infinity(self):
        self._assert_rejected(float("inf"), ValueError)

    def test_rejects_negative_infinity(self):
        self._assert_rejected(float("-inf"), ValueError)

    def test_rejects_below_zero(self):
        self._assert_rejected(-0.1, ValueError)

    def test_rejects_above_one(self):
        self._assert_rejected(1.1, ValueError)

    def test_rejects_non_numeric(self):
        self._assert_rejected("high", TypeError)

    def test_none_allowed(self):
        outcome = self.repo.create(Outcome(test_id=self.test.id, confidence=None))
        self.assertIsNone(outcome.confidence)


class TestConfidenceMigration(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)
        os.unlink(self.temp_path)  # start with no file

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def _build_legacy_db(self):
        """Create an outcomes table without the confidence column."""
        conn = sqlite3.connect(self.temp_path)
        conn.executescript("""
        CREATE TABLE hypotheses (
            id TEXT PRIMARY KEY, statement TEXT NOT NULL,
            audience_id TEXT, offer_id TEXT, source_id TEXT,
            rationale TEXT DEFAULT '', evidence_type TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE tests (
            id TEXT PRIMARY KEY, hypothesis_id TEXT NOT NULL, name TEXT NOT NULL,
            method TEXT DEFAULT '', success_criteria TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'planned',
            evidence_type TEXT NOT NULL DEFAULT 'proposed',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE outcomes (
            id TEXT PRIMARY KEY, test_id TEXT NOT NULL,
            result TEXT DEFAULT '', metrics TEXT DEFAULT '',
            interpretation TEXT DEFAULT '', supports_hypothesis INTEGER,
            evidence_type TEXT NOT NULL DEFAULT 'measured',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        INSERT INTO hypotheses VALUES ('h1', 'Legacy H', NULL, NULL, NULL, '',
            'proposed', '2024-01-01', '2024-01-01');
        INSERT INTO tests VALUES ('t1', 'h1', 'Legacy T', '', '', 'completed',
            'proposed', '2024-01-01', '2024-01-01');
        INSERT INTO outcomes VALUES ('o1', 't1', 'Legacy result', 'm', 'i', 0,
            'measured', '2024-01-01', '2024-01-01');
        """)
        conn.commit()
        conn.close()

    def test_legacy_db_opens_and_preserves_rows(self):
        self._build_legacy_db()
        repo = Repository(self.temp_path)
        outcomes = repo.list_all(Outcome)
        self.assertEqual(len(outcomes), 1)
        o = outcomes[0]
        self.assertEqual(o.id, "o1")
        self.assertEqual(o.result, "Legacy result")
        self.assertFalse(o.supports_hypothesis)
        self.assertIsNone(o.confidence)
        repo.close()

    def test_new_outcomes_store_confidence_after_migration(self):
        self._build_legacy_db()
        repo = Repository(self.temp_path)
        new_outcome = repo.create(Outcome(test_id="t1", result="New", confidence=0.9))
        repo.close()

        repo2 = Repository(self.temp_path)
        loaded = repo2.get(Outcome, new_outcome.id)
        self.assertEqual(loaded.confidence, 0.9)
        self.assertEqual(len(repo2.list_all(Outcome)), 2)
        repo2.close()

    def test_reopen_is_idempotent(self):
        self._build_legacy_db()
        for _ in range(3):
            repo = Repository(self.temp_path)
            self.assertEqual(len(repo.list_all(Outcome)), 1)
            repo.close()


if __name__ == "__main__":
    unittest.main()
