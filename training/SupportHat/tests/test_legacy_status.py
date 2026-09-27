"""Unit tests for legacy status filter compatibility.

Verifies that all declared legacy status mappings work correctly:
- open -> matches 'open' or 'new'
- in_progress -> matches 'in_progress' or 'in-progress'
- pending -> matches 'pending' or 'triaged'
- resolved -> resolved (direct match)
- closed -> closed (direct match)

This covers both first-slice databases that may have raw legacy values
and new databases that use normalized status values.
"""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db


class TestLegacyStatusFilters(unittest.TestCase):
    """Tests for all legacy status filter mappings with normalized values."""
    
    def setUp(self):
        """Create a temporary database with cases in all statuses."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
        
        # Create cases and transition them to various statuses
        self.case_new = db.create_case(self.conn, subject="Case in new status")
        
        self.case_triaged = db.create_case(self.conn, subject="Case in triaged status")
        db.transition_status(self.conn, self.case_triaged, 'triaged')
        
        self.case_in_progress = db.create_case(self.conn, subject="Case in in-progress status")
        db.transition_status(self.conn, self.case_in_progress, 'in-progress')
        
        self.case_resolved = db.create_case(self.conn, subject="Case in resolved status")
        db.transition_status(self.conn, self.case_resolved, 'resolved')
        
        self.case_closed = db.create_case(self.conn, subject="Case in closed status")
        db.transition_status(self.conn, self.case_closed, 'closed')
    
    def tearDown(self):
        """Clean up temporary database."""
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_legacy_open_filter_finds_new_cases(self):
        """Legacy 'open' filter should find cases with 'new' status."""
        cases = db.list_cases(self.conn, status='open')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], self.case_new)
        self.assertEqual(cases[0]['status'], 'new')
    
    def test_legacy_in_progress_filter_finds_in_progress_cases(self):
        """Legacy 'in_progress' filter should find cases with 'in-progress' status."""
        cases = db.list_cases(self.conn, status='in_progress')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], self.case_in_progress)
        self.assertEqual(cases[0]['status'], 'in-progress')
    
    def test_legacy_pending_filter_finds_triaged_cases(self):
        """Legacy 'pending' filter should find cases with 'triaged' status."""
        cases = db.list_cases(self.conn, status='pending')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], self.case_triaged)
        self.assertEqual(cases[0]['status'], 'triaged')
    
    def test_legacy_resolved_filter_finds_resolved_cases(self):
        """Legacy 'resolved' filter should find cases with 'resolved' status."""
        cases = db.list_cases(self.conn, status='resolved')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], self.case_resolved)
        self.assertEqual(cases[0]['status'], 'resolved')
    
    def test_legacy_closed_filter_finds_closed_cases(self):
        """Legacy 'closed' filter should find cases with 'closed' status."""
        cases = db.list_cases(self.conn, status='closed')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], self.case_closed)
        self.assertEqual(cases[0]['status'], 'closed')
    
    def test_native_status_filters_still_work(self):
        """Native status values should continue to work directly."""
        # Test each native status
        new_cases = db.list_cases(self.conn, status='new')
        self.assertEqual(len(new_cases), 1)
        self.assertEqual(new_cases[0]['id'], self.case_new)
        
        triaged_cases = db.list_cases(self.conn, status='triaged')
        self.assertEqual(len(triaged_cases), 1)
        self.assertEqual(triaged_cases[0]['id'], self.case_triaged)
        
        in_progress_cases = db.list_cases(self.conn, status='in-progress')
        self.assertEqual(len(in_progress_cases), 1)
        self.assertEqual(in_progress_cases[0]['id'], self.case_in_progress)
    
    def test_no_filter_returns_all_cases(self):
        """No status filter should return all cases."""
        cases = db.list_cases(self.conn)
        self.assertEqual(len(cases), 5)
    
    def test_legacy_mapping_constants_declared(self):
        """Verify LEGACY_STATUS_MAP contains expected mappings."""
        self.assertIn('open', db.LEGACY_STATUS_MAP)
        self.assertIn('in_progress', db.LEGACY_STATUS_MAP)
        self.assertIn('pending', db.LEGACY_STATUS_MAP)
        self.assertEqual(db.LEGACY_STATUS_MAP['open'], 'new')
        self.assertEqual(db.LEGACY_STATUS_MAP['in_progress'], 'in-progress')
        self.assertEqual(db.LEGACY_STATUS_MAP['pending'], 'triaged')


class TestLegacyStatusRawValues(unittest.TestCase):
    """Tests for databases that store raw legacy status values.
    
    This simulates first-slice databases where cases were inserted
    with raw legacy status strings like 'open', 'in_progress', 'pending'.
    """
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def _insert_raw_status(self, subject, status):
        """Insert a case with a raw status value directly into the database."""
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        cursor = self.conn.execute(
            """INSERT INTO cases (subject, status, priority, created_at, updated_at)
               VALUES (?, ?, 'normal', ?, ?)""",
            (subject, status, now, now)
        )
        self.conn.commit()
        return cursor.lastrowid
    
    def test_legacy_open_filter_finds_raw_open_cases(self):
        """Legacy 'open' filter should find cases with raw 'open' status."""
        case_id = self._insert_raw_status("Raw open case", 'open')
        cases = db.list_cases(self.conn, status='open')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], case_id)
        self.assertEqual(cases[0]['status'], 'open')
    
    def test_legacy_in_progress_filter_finds_raw_in_progress_cases(self):
        """Legacy 'in_progress' filter should find cases with raw 'in_progress' status."""
        case_id = self._insert_raw_status("Raw in_progress case", 'in_progress')
        cases = db.list_cases(self.conn, status='in_progress')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], case_id)
        self.assertEqual(cases[0]['status'], 'in_progress')
    
    def test_legacy_pending_filter_finds_raw_pending_cases(self):
        """Legacy 'pending' filter should find cases with raw 'pending' status."""
        case_id = self._insert_raw_status("Raw pending case", 'pending')
        cases = db.list_cases(self.conn, status='pending')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], case_id)
        self.assertEqual(cases[0]['status'], 'pending')
    
    def test_mixed_raw_and_normalized_values(self):
        """Legacy filter should find both raw and normalized values."""
        # Insert a case with raw 'open' status
        raw_id = self._insert_raw_status("Raw open case", 'open')
        # Create a case with normalized 'new' status
        new_id = db.create_case(self.conn, subject="New status case")
        
        cases = db.list_cases(self.conn, status='open')
        case_ids = [c['id'] for c in cases]
        self.assertEqual(len(cases), 2)
        self.assertIn(raw_id, case_ids)
        self.assertIn(new_id, case_ids)


class TestLegacyStatusNormalization(unittest.TestCase):
    """Tests for status normalization in updates and transitions."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_transition_with_legacy_in_progress(self):
        """Transitioning with 'in_progress' should set 'in-progress'."""
        case_id = db.create_case(self.conn, subject="Legacy transition test")
        db.transition_status(self.conn, case_id, 'in_progress')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'in-progress')
    
    def test_update_with_legacy_pending(self):
        """Updating with 'pending' status should set 'triaged'."""
        case_id = db.create_case(self.conn, subject="Legacy update test")
        db.update_case(self.conn, case_id, status='pending')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'triaged')
    
    def test_update_with_legacy_open(self):
        """Updating with 'open' status should set 'new'."""
        case_id = db.create_case(self.conn, subject="Legacy open update")
        db.transition_status(self.conn, case_id, 'triaged')
        db.update_case(self.conn, case_id, status='open')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'new')


if __name__ == '__main__':
    unittest.main()
