"""Unit tests for GrowthHat CLI."""

import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from growthhat.cli import main, build_parser
from growthhat.repository import Repository
from growthhat.models import Source, Audience, Offer, Hypothesis, Test, EvidenceType


class TestCLISourceAdd(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_add_source_basic(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "source", "add",
                          "--name", "Test Source", "--url", "https://example.com"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Created source:", output)
        self.assertIn("Test Source", output)

        # Verify persistence
        repo = Repository(self.temp_path)
        sources = repo.list_all(Source)
        repo.close()
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].name, "Test Source")
        self.assertEqual(sources[0].url, "https://example.com")

    def test_add_source_with_all_fields(self):
        with patch("sys.stdout", new_callable=StringIO):
            result = main(["--db", self.temp_path, "source", "add",
                          "--name", "Full Source",
                          "--url", "https://example.com/report",
                          "--type", "article",
                          "--notes", "Important findings here",
                          "--evidence-type", "measured"])
        self.assertEqual(result, 0)

        repo = Repository(self.temp_path)
        sources = repo.list_all(Source)
        repo.close()
        self.assertEqual(len(sources), 1)
        s = sources[0]
        self.assertEqual(s.name, "Full Source")
        self.assertEqual(s.source_type, "article")
        self.assertEqual(s.notes, "Important findings here")
        self.assertEqual(s.evidence_type, EvidenceType.MEASURED)

    def test_add_source_invalid_evidence_type(self):
        # argparse validates choices and calls sys.exit(2) for invalid values
        # before our code even runs, so we expect SystemExit
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as ctx:
                main(["--db", self.temp_path, "source", "add",
                      "--name", "Bad Source",
                      "--evidence-type", "invalid"])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("invalid choice", mock_stderr.getvalue())


class TestCLISourceList(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_list_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "source", "list"])
        self.assertEqual(result, 0)
        self.assertIn("No sources found", mock_stdout.getvalue())

    def test_list_with_sources(self):
        repo = Repository(self.temp_path)
        repo.create(Source(name="Source A", source_type="interview"))
        repo.create(Source(name="Source B", source_type="survey"))
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "source", "list"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Source A", output)
        self.assertIn("Source B", output)
        self.assertIn("Total: 2 source(s)", output)


class TestCLISourceShow(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_show_existing_source(self):
        repo = Repository(self.temp_path)
        source = Source(
            name="Detailed Source",
            source_type="analytics",
            url="https://analytics.example.com",
            notes="Conversion data Q1",
            evidence_type=EvidenceType.MEASURED,
        )
        repo.create(source)
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "source", "show", source.id])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn(source.id, output)
        self.assertIn("Detailed Source", output)
        self.assertIn("analytics", output)
        self.assertIn("https://analytics.example.com", output)
        self.assertIn("Conversion data Q1", output)
        self.assertIn("measured", output)

    def test_show_nonexistent_source(self):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["--db", self.temp_path, "source", "show", "nonexistent-id"])
        self.assertEqual(result, 1)
        self.assertIn("not found", mock_stderr.getvalue())


class TestCLIHelp(unittest.TestCase):
    def test_no_command_shows_help(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main([])
        self.assertEqual(result, 0)

    def test_parser_builds_successfully(self):
        parser = build_parser()
        self.assertIsNotNone(parser)


class TestCLIPersistence(unittest.TestCase):
    """Test that data persists across CLI invocations."""

    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_data_persists_across_runs(self):
        # First run: add a source
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--db", self.temp_path, "source", "add",
                  "--name", "Persistent Source", "--url", "https://persist.test"])
        output1 = mock_stdout.getvalue()
        # Extract ID from output
        source_id = None
        for line in output1.split("\n"):
            if "Created source:" in line:
                source_id = line.split(":")[1].strip()
                break
        self.assertIsNotNone(source_id)

        # Second run: list sources (simulates new process)
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--db", self.temp_path, "source", "list"])
        output2 = mock_stdout.getvalue()
        self.assertIn("Persistent Source", output2)

        # Third run: show the specific source
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            main(["--db", self.temp_path, "source", "show", source_id])
        output3 = mock_stdout.getvalue()
        self.assertIn("Persistent Source", output3)
        self.assertIn("https://persist.test", output3)


class TestCLIAudienceAdd(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_add_audience_basic(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "audience", "add",
                          "--name", "Early Adopters"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Created audience:", output)
        self.assertIn("Early Adopters", output)

        repo = Repository(self.temp_path)
        audiences = repo.list_all(Audience)
        repo.close()
        self.assertEqual(len(audiences), 1)
        self.assertEqual(audiences[0].name, "Early Adopters")

    def test_add_audience_with_all_fields(self):
        with patch("sys.stdout", new_callable=StringIO):
            result = main(["--db", self.temp_path, "audience", "add",
                          "--name", "SMB Owners",
                          "--description", "Small business owners",
                          "--needs", "Automation tools",
                          "--objections", "Price concerns",
                          "--channels", "LinkedIn, Twitter",
                          "--evidence-type", "measured"])
        self.assertEqual(result, 0)

        repo = Repository(self.temp_path)
        audiences = repo.list_all(Audience)
        repo.close()
        self.assertEqual(len(audiences), 1)
        a = audiences[0]
        self.assertEqual(a.name, "SMB Owners")
        self.assertEqual(a.description, "Small business owners")
        self.assertEqual(a.needs, "Automation tools")
        self.assertEqual(a.objections, "Price concerns")
        self.assertEqual(a.discovery_channels, "LinkedIn, Twitter")
        self.assertEqual(a.evidence_type, EvidenceType.MEASURED)


class TestCLIAudienceList(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_list_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "audience", "list"])
        self.assertEqual(result, 0)
        self.assertIn("No audiences found", mock_stdout.getvalue())

    def test_list_with_audiences(self):
        repo = Repository(self.temp_path)
        repo.create(Audience(name="Audience A"))
        repo.create(Audience(name="Audience B"))
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "audience", "list"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Audience A", output)
        self.assertIn("Audience B", output)
        self.assertIn("Total: 2 audience(s)", output)


class TestCLIOfferAdd(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_add_offer_basic(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "offer", "add",
                          "--name", "Pro Plan"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Created offer:", output)
        self.assertIn("Pro Plan", output)

        repo = Repository(self.temp_path)
        offers = repo.list_all(Offer)
        repo.close()
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].name, "Pro Plan")

    def test_add_offer_with_all_fields(self):
        # Create audience first
        repo = Repository(self.temp_path)
        audience = Audience(name="Test Audience")
        repo.create(audience)
        repo.close()

        with patch("sys.stdout", new_callable=StringIO):
            result = main(["--db", self.temp_path, "offer", "add",
                          "--name", "Enterprise Plan",
                          "--description", "Full features",
                          "--value", "Save 20 hours/week",
                          "--audience-id", audience.id,
                          "--evidence-type", "proposed"])
        self.assertEqual(result, 0)

        repo = Repository(self.temp_path)
        offers = repo.list_all(Offer)
        repo.close()
        self.assertEqual(len(offers), 1)
        o = offers[0]
        self.assertEqual(o.name, "Enterprise Plan")
        self.assertEqual(o.description, "Full features")
        self.assertEqual(o.value_proposition, "Save 20 hours/week")
        self.assertEqual(o.audience_id, audience.id)
        self.assertEqual(o.evidence_type, EvidenceType.PROPOSED)

    def test_add_offer_invalid_audience(self):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["--db", self.temp_path, "offer", "add",
                          "--name", "Bad Offer",
                          "--audience-id", "nonexistent-id"])
        self.assertEqual(result, 1)
        self.assertIn("not found", mock_stderr.getvalue())


class TestCLIOfferList(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_list_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "offer", "list"])
        self.assertEqual(result, 0)
        self.assertIn("No offers found", mock_stdout.getvalue())

    def test_list_with_offers(self):
        repo = Repository(self.temp_path)
        repo.create(Offer(name="Offer A"))
        repo.create(Offer(name="Offer B"))
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "offer", "list"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Offer A", output)
        self.assertIn("Offer B", output)
        self.assertIn("Total: 2 offer(s)", output)


class TestCLIHypothesisAdd(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_add_hypothesis_valid(self):
        repo = Repository(self.temp_path)
        s = repo.create(Source(name="S"))
        a = repo.create(Audience(name="A"))
        o = repo.create(Offer(name="O"))
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "hypothesis", "add",
                          "--statement", "Test H", "--evidence-type", "proposed",
                          "--source-id", s.id, "--audience-id", a.id, "--offer-id", o.id])
        self.assertEqual(result, 0)
        self.assertIn("Created hypothesis", mock_stdout.getvalue())

    def test_add_hypothesis_invalid_ids(self):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["--db", self.temp_path, "hypothesis", "add",
                          "--statement", "Test H", "--evidence-type", "proposed",
                          "--source-id", "missing"])
        self.assertEqual(result, 1)
        self.assertIn("not found", mock_stderr.getvalue())

    def test_list_hypothesis(self):
        repo = Repository(self.temp_path)
        from growthhat.models import Hypothesis
        h = Hypothesis(statement="Important theory", rationale="Because logic", evidence_type=EvidenceType.MEASURED)
        repo.create(h)
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "hypothesis", "list"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Important theory", output)
        self.assertIn("Because logic", output)
        self.assertIn(h.id, output)


class TestCLITestAdd(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def _make_hypothesis(self):
        repo = Repository(self.temp_path)
        hyp = repo.create(Hypothesis(statement="Users want X",
                                     evidence_type=EvidenceType.PROPOSED))
        repo.close()
        return hyp

    def test_add_test_success(self):
        hyp = self._make_hypothesis()
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "test", "add",
                          "--hypothesis-id", hyp.id,
                          "--name", "Smoke test",
                          "--method", "Landing page A/B",
                          "--success-criteria", "5% signup rate"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Created test:", output)
        self.assertIn(hyp.id, output)
        self.assertIn("Smoke test", output)

        repo = Repository(self.temp_path)
        tests = repo.list_all(Test)
        repo.close()
        self.assertEqual(len(tests), 1)
        t = tests[0]
        self.assertEqual(t.hypothesis_id, hyp.id)
        self.assertEqual(t.name, "Smoke test")
        self.assertEqual(t.method, "Landing page A/B")
        self.assertEqual(t.success_criteria, "5% signup rate")
        self.assertEqual(t.status, "planned")

    def test_add_test_invalid_hypothesis_rejected(self):
        with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            result = main(["--db", self.temp_path, "test", "add",
                          "--hypothesis-id", "nonexistent-id",
                          "--name", "Bad test"])
        self.assertEqual(result, 1)
        self.assertIn("not found", mock_stderr.getvalue())

        # No partial test record persisted
        repo = Repository(self.temp_path)
        tests = repo.list_all(Test)
        repo.close()
        self.assertEqual(len(tests), 0)


class TestCLITestList(unittest.TestCase):
    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_fd)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            os.unlink(self.temp_path)

    def test_list_empty(self):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "test", "list"])
        self.assertEqual(result, 0)
        self.assertIn("No tests found", mock_stdout.getvalue())

    def test_list_shows_ids_and_names(self):
        repo = Repository(self.temp_path)
        hyp = repo.create(Hypothesis(statement="H",
                                     evidence_type=EvidenceType.PROPOSED))
        test = repo.create(Test(hypothesis_id=hyp.id, name="Checkout experiment"))
        repo.close()

        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            result = main(["--db", self.temp_path, "test", "list"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn(test.id, output)
        self.assertIn(hyp.id, output)
        self.assertIn("Checkout experiment", output)
        self.assertIn("Total: 1 test(s)", output)


if __name__ == "__main__":
    unittest.main()
