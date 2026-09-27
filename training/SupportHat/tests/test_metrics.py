"""Unit tests for SupportHat metrics tracking."""

import unittest
import tempfile
import os
from pathlib import Path
from datetime import datetime, timedelta

from supporthat import db
from supporthat import metrics
from supporthat import drafts


class TestHandoffs(unittest.TestCase):
    """Tests for handoff tracking."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_record_handoff_increments_counter(self):
        """Recording handoffs increments the count for a case."""
        case_id = db.create_case(self.conn, subject="Handoff test")
        
        self.assertEqual(metrics.get_handoff_count(self.conn, case_id), 0)
        
        self.assertTrue(metrics.record_handoff(self.conn, case_id))
        self.assertEqual(metrics.get_handoff_count(self.conn, case_id), 1)
        
        self.assertTrue(metrics.record_handoff(self.conn, case_id))
        self.assertEqual(metrics.get_handoff_count(self.conn, case_id), 2)
    
    def test_record_handoff_nonexistent_case(self):
        """Recording handoff for nonexistent case returns False."""
        result = metrics.record_handoff(self.conn, 99999)
        self.assertFalse(result)
    
    def test_handoff_does_not_change_status(self):
        """Recording handoff does not modify case status."""
        case_id = db.create_case(self.conn, subject="Status test")
        original = db.get_case(self.conn, case_id)
        
        metrics.record_handoff(self.conn, case_id)
        
        updated = db.get_case(self.conn, case_id)
        self.assertEqual(original['status'], updated['status'])


class TestFeedback(unittest.TestCase):
    """Tests for quality feedback."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_record_and_list_feedback(self):
        """Feedback can be recorded and listed."""
        case_id = db.create_case(self.conn, subject="Feedback test")
        
        self.assertTrue(metrics.record_feedback(self.conn, case_id, 4))
        self.assertTrue(metrics.record_feedback(self.conn, case_id, 5))
        
        feedback_list = metrics.list_feedback(self.conn, case_id)
        self.assertEqual(len(feedback_list), 2)
        self.assertEqual(feedback_list[0]['rating'], 4)
        self.assertEqual(feedback_list[1]['rating'], 5)
    
    def test_invalid_rating_rejected(self):
        """Ratings outside 1-5 are rejected."""
        case_id = db.create_case(self.conn, subject="Invalid rating")
        
        with self.assertRaises(ValueError):
            metrics.record_feedback(self.conn, case_id, 0)
        
        with self.assertRaises(ValueError):
            metrics.record_feedback(self.conn, case_id, 6)
        
        with self.assertRaises(ValueError):
            metrics.record_feedback(self.conn, case_id, -1)
        
        # Verify no partial writes
        self.assertEqual(metrics.list_feedback(self.conn, case_id), [])
    
    def test_feedback_nonexistent_case(self):
        """Feedback for nonexistent case returns False."""
        result = metrics.record_feedback(self.conn, 99999, 3)
        self.assertFalse(result)


class TestMetricsSummary(unittest.TestCase):
    """Tests for metrics summary."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_summary_counts_resolved_cases(self):
        """Summary counts resolved and closed cases."""
        case1 = db.create_case(self.conn, subject="Open case")
        case2 = db.create_case(self.conn, subject="Resolved case")
        case3 = db.create_case(self.conn, subject="Closed case")
        
        db.transition_status(self.conn, case2, 'resolved')
        db.transition_status(self.conn, case3, 'closed')
        
        summary = metrics.get_metrics_summary(self.conn)
        self.assertEqual(summary['resolved_count'], 2)
    
    def test_summary_total_handoffs(self):
        """Summary counts total handoffs across cases."""
        case1 = db.create_case(self.conn, subject="Case 1")
        case2 = db.create_case(self.conn, subject="Case 2")
        
        metrics.record_handoff(self.conn, case1)
        metrics.record_handoff(self.conn, case1)
        metrics.record_handoff(self.conn, case2)
        
        summary = metrics.get_metrics_summary(self.conn)
        self.assertEqual(summary['total_handoffs'], 3)
    
    def test_summary_unanswered_count(self):
        """Summary counts unanswered cases (new/triaged with no draft)."""
        case1 = db.create_case(self.conn, subject="New no draft")
        case2 = db.create_case(self.conn, subject="Triaged no draft")
        case3 = db.create_case(self.conn, subject="Resolved")
        
        db.transition_status(self.conn, case2, 'triaged')
        db.transition_status(self.conn, case3, 'resolved')
        
        summary = metrics.get_metrics_summary(self.conn)
        self.assertEqual(summary['unanswered_count'], 2)
    
    def test_summary_average_rating(self):
        """Summary computes average rating, null when none."""
        # No ratings
        summary = metrics.get_metrics_summary(self.conn)
        self.assertIsNone(summary['average_rating'])
        
        # Add ratings
        case_id = db.create_case(self.conn, subject="Rated case")
        metrics.record_feedback(self.conn, case_id, 3)
        metrics.record_feedback(self.conn, case_id, 5)
        
        summary = metrics.get_metrics_summary(self.conn)
        self.assertEqual(summary['feedback_count'], 2)
        self.assertEqual(summary['average_rating'], 4.0)
    
    def test_summary_resolution_time(self):
        """Summary includes resolution time derived from timestamps."""
        case_id = db.create_case(self.conn, subject="Timed case")
        db.transition_status(self.conn, case_id, 'resolved')
        
        summary = metrics.get_metrics_summary(self.conn)
        self.assertIsNotNone(summary['avg_resolution_time_seconds'])
        self.assertIsInstance(summary['avg_resolution_time_seconds'], float)


if __name__ == '__main__':
    unittest.main()
