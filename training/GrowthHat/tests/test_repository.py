"""Unit tests for GrowthHat repository layer."""

import unittest
from growthhat import (
    Repository,
    EvidenceType,
    Source,
    Audience,
    Offer,
    Hypothesis,
    Test,
    Outcome,
    Recommendation,
)


class TestSourceCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        source = Source(
            name="Customer Interview 1",
            source_type="interview",
            url="https://example.com/notes",
            notes="Key insights from early adopter",
            evidence_type=EvidenceType.MEASURED,
        )
        created = self.repo.create(source)
        self.assertEqual(created.id, source.id)

        retrieved = self.repo.get(Source, source.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "Customer Interview 1")
        self.assertEqual(retrieved.evidence_type, EvidenceType.MEASURED)

    def test_update(self):
        source = Source(name="Draft Source", source_type="article")
        self.repo.create(source)

        source.name = "Final Source"
        source.evidence_type = EvidenceType.MEASURED
        self.repo.update(source)

        retrieved = self.repo.get(Source, source.id)
        self.assertEqual(retrieved.name, "Final Source")
        self.assertEqual(retrieved.evidence_type, EvidenceType.MEASURED)

    def test_delete(self):
        source = Source(name="To Delete", source_type="survey")
        self.repo.create(source)

        deleted = self.repo.delete(Source, source.id)
        self.assertTrue(deleted)

        retrieved = self.repo.get(Source, source.id)
        self.assertIsNone(retrieved)

    def test_list_all(self):
        self.repo.create(Source(name="S1", source_type="a"))
        self.repo.create(Source(name="S2", source_type="b"))

        sources = self.repo.list_all(Source)
        self.assertEqual(len(sources), 2)


class TestAudienceCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        audience = Audience(
            name="Early Adopters",
            description="Tech-savvy users who try new tools",
            needs="Automation, speed",
            objections="Learning curve",
            discovery_channels="HackerNews, Twitter",
            evidence_type=EvidenceType.ASSUMED,
        )
        self.repo.create(audience)

        retrieved = self.repo.get(Audience, audience.id)
        self.assertEqual(retrieved.name, "Early Adopters")
        self.assertEqual(retrieved.evidence_type, EvidenceType.ASSUMED)

    def test_update(self):
        audience = Audience(name="Segment A")
        self.repo.create(audience)

        audience.description = "Updated description"
        self.repo.update(audience)

        retrieved = self.repo.get(Audience, audience.id)
        self.assertEqual(retrieved.description, "Updated description")

    def test_delete(self):
        audience = Audience(name="To Remove")
        self.repo.create(audience)

        self.assertTrue(self.repo.delete(Audience, audience.id))
        self.assertIsNone(self.repo.get(Audience, audience.id))


class TestOfferCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        offer = Offer(
            name="Pro Plan",
            description="Advanced features",
            value_proposition="Save 10 hours/week",
            evidence_type=EvidenceType.PROPOSED,
        )
        self.repo.create(offer)

        retrieved = self.repo.get(Offer, offer.id)
        self.assertEqual(retrieved.name, "Pro Plan")
        self.assertEqual(retrieved.evidence_type, EvidenceType.PROPOSED)

    def test_with_audience_link(self):
        audience = Audience(name="SMB Owners")
        self.repo.create(audience)

        offer = Offer(name="SMB Package", audience_id=audience.id)
        self.repo.create(offer)

        retrieved = self.repo.get(Offer, offer.id)
        self.assertEqual(retrieved.audience_id, audience.id)

    def test_update_and_delete(self):
        offer = Offer(name="Basic")
        self.repo.create(offer)

        offer.value_proposition = "Free forever"
        self.repo.update(offer)
        self.assertEqual(self.repo.get(Offer, offer.id).value_proposition, "Free forever")

        self.assertTrue(self.repo.delete(Offer, offer.id))


class TestHypothesisCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        hypothesis = Hypothesis(
            statement="SMB owners will pay for automation",
            rationale="Time is their scarcest resource",
            evidence_type=EvidenceType.PROPOSED,
        )
        self.repo.create(hypothesis)

        retrieved = self.repo.get(Hypothesis, hypothesis.id)
        self.assertEqual(retrieved.statement, "SMB owners will pay for automation")

    def test_with_links(self):
        source = Source(name="Market Report", source_type="report")
        audience = Audience(name="Freelancers")
        offer = Offer(name="Starter")
        self.repo.create(source)
        self.repo.create(audience)
        self.repo.create(offer)

        hypothesis = Hypothesis(
            statement="Freelancers prefer simple pricing",
            source_id=source.id,
            audience_id=audience.id,
            offer_id=offer.id,
        )
        self.repo.create(hypothesis)

        retrieved = self.repo.get(Hypothesis, hypothesis.id)
        self.assertEqual(retrieved.source_id, source.id)
        self.assertEqual(retrieved.audience_id, audience.id)
        self.assertEqual(retrieved.offer_id, offer.id)

    def test_update_and_delete(self):
        h = Hypothesis(statement="Initial")
        self.repo.create(h)

        h.statement = "Revised"
        self.repo.update(h)
        self.assertEqual(self.repo.get(Hypothesis, h.id).statement, "Revised")

        self.assertTrue(self.repo.delete(Hypothesis, h.id))


class TestTestCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        hypothesis = Hypothesis(statement="Users want feature X")
        self.repo.create(hypothesis)

        test = Test(
            hypothesis_id=hypothesis.id,
            name="A/B Test Feature X",
            method="50/50 split",
            success_criteria="10% lift in conversion",
            status="planned",
        )
        self.repo.create(test)

        retrieved = self.repo.get(Test, test.id)
        self.assertEqual(retrieved.name, "A/B Test Feature X")
        self.assertEqual(retrieved.hypothesis_id, hypothesis.id)

    def test_update_and_delete(self):
        h = Hypothesis(statement="H")
        self.repo.create(h)

        t = Test(hypothesis_id=h.id, name="T1")
        self.repo.create(t)

        t.status = "completed"
        self.repo.update(t)
        self.assertEqual(self.repo.get(Test, t.id).status, "completed")

        self.assertTrue(self.repo.delete(Test, t.id))


class TestOutcomeCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        h = Hypothesis(statement="H")
        self.repo.create(h)
        t = Test(hypothesis_id=h.id, name="T")
        self.repo.create(t)

        outcome = Outcome(
            test_id=t.id,
            result="12% lift observed",
            metrics="conversion: 4.2% -> 4.7%",
            interpretation="Statistically significant",
            supports_hypothesis=True,
            evidence_type=EvidenceType.MEASURED,
        )
        self.repo.create(outcome)

        retrieved = self.repo.get(Outcome, outcome.id)
        self.assertEqual(retrieved.result, "12% lift observed")
        self.assertTrue(retrieved.supports_hypothesis)
        self.assertEqual(retrieved.evidence_type, EvidenceType.MEASURED)

    def test_update_and_delete(self):
        h = Hypothesis(statement="H")
        self.repo.create(h)
        t = Test(hypothesis_id=h.id, name="T")
        self.repo.create(t)
        o = Outcome(test_id=t.id, result="Initial")
        self.repo.create(o)

        o.supports_hypothesis = False
        self.repo.update(o)
        self.assertFalse(self.repo.get(Outcome, o.id).supports_hypothesis)

        self.assertTrue(self.repo.delete(Outcome, o.id))


class TestRecommendationCRUD(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_create_and_read(self):
        rec = Recommendation(
            title="Add Feature X",
            description="Based on test results",
            action="Implement feature X in Q1",
            reasoning="12% conversion lift",
            uncertainty_level="low",
            source_ids="src1,src2",
        )
        self.repo.create(rec)

        retrieved = self.repo.get(Recommendation, rec.id)
        self.assertEqual(retrieved.title, "Add Feature X")
        self.assertEqual(retrieved.uncertainty_level, "low")

    def test_with_links(self):
        h = Hypothesis(statement="H")
        self.repo.create(h)
        t = Test(hypothesis_id=h.id, name="T")
        self.repo.create(t)
        o = Outcome(test_id=t.id, result="R")
        self.repo.create(o)

        rec = Recommendation(
            title="Linked Rec",
            hypothesis_id=h.id,
            outcome_id=o.id,
        )
        self.repo.create(rec)

        retrieved = self.repo.get(Recommendation, rec.id)
        self.assertEqual(retrieved.hypothesis_id, h.id)
        self.assertEqual(retrieved.outcome_id, o.id)

    def test_update_and_delete(self):
        rec = Recommendation(title="Draft")
        self.repo.create(rec)

        rec.uncertainty_level = "high"
        self.repo.update(rec)
        self.assertEqual(self.repo.get(Recommendation, rec.id).uncertainty_level, "high")

        self.assertTrue(self.repo.delete(Recommendation, rec.id))


class TestDeleteNonexistent(unittest.TestCase):
    def setUp(self):
        self.repo = Repository(":memory:")

    def tearDown(self):
        self.repo.close()

    def test_delete_returns_false_for_missing(self):
        result = self.repo.delete(Source, "nonexistent-id")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
