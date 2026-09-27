"""Unit tests for SupportHat triage workflow."""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db


class TestStatusTransitions(unittest.TestCase):
    """Tests for status transition workflow."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_new_case_starts_with_new_status(self):
        """New cases should start with 'new' status."""
        case_id = db.create_case(self.conn, subject="Fresh case")
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'new')
    
    def test_transition_records_history(self):
        """Status transitions should be recorded in history."""
        case_id = db.create_case(self.conn, subject="Transition test")
        
        db.transition_status(self.conn, case_id, 'triaged', changed_by='alice', note='Looks like a bug')
        db.transition_status(self.conn, case_id, 'in-progress', changed_by='bob')
        db.transition_status(self.conn, case_id, 'resolved', changed_by='bob', note='Fixed in v2.2')
        
        history = db.get_status_history(self.conn, case_id)
        
        self.assertEqual(len(history), 4)  # initial + 3 transitions
        
        # Check initial entry
        self.assertIsNone(history[0]['old_status'])
        self.assertEqual(history[0]['new_status'], 'new')
        
        # Check transition to triaged
        self.assertEqual(history[1]['old_status'], 'new')
        self.assertEqual(history[1]['new_status'], 'triaged')
        self.assertEqual(history[1]['changed_by'], 'alice')
        self.assertEqual(history[1]['note'], 'Looks like a bug')
        
        # Check transition to in-progress
        self.assertEqual(history[2]['old_status'], 'triaged')
        self.assertEqual(history[2]['new_status'], 'in-progress')
        self.assertEqual(history[2]['changed_by'], 'bob')
        
        # Check transition to resolved
        self.assertEqual(history[3]['old_status'], 'in-progress')
        self.assertEqual(history[3]['new_status'], 'resolved')
        self.assertEqual(history[3]['note'], 'Fixed in v2.2')
    
    def test_triage_case_sets_status_and_fields(self):
        """Triage command should set status to triaged and update fields."""
        case_id = db.create_case(self.conn, subject="Needs triage", priority='normal')
        
        result = db.triage_case(
            self.conn, case_id,
            priority='high',
            assignee='charlie',
            note='Urgent customer issue',
            changed_by='alice'
        )
        
        self.assertTrue(result)
        
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'triaged')
        self.assertEqual(case['priority'], 'high')
        self.assertEqual(case['assignee'], 'charlie')
        
        history = db.get_status_history(self.conn, case_id)
        triage_entry = history[-1]
        self.assertEqual(triage_entry['new_status'], 'triaged')
        self.assertEqual(triage_entry['changed_by'], 'alice')
        self.assertEqual(triage_entry['note'], 'Urgent customer issue')
    
    def test_full_lifecycle_transitions(self):
        """Test complete case lifecycle: new -> triaged -> in-progress -> resolved -> closed."""
        case_id = db.create_case(self.conn, subject="Lifecycle test")
        
        # Triage
        db.triage_case(self.conn, case_id, priority='high', assignee='dev1')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'triaged')
        
        # Start work
        db.transition_status(self.conn, case_id, 'in-progress')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'in-progress')
        
        # Resolve
        db.transition_status(self.conn, case_id, 'resolved', note='Deployed fix')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'resolved')
        
        # Close
        db.transition_status(self.conn, case_id, 'closed', note='Customer confirmed')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'closed')
        
        # Verify full history
        history = db.get_status_history(self.conn, case_id)
        statuses = [h['new_status'] for h in history]
        self.assertEqual(statuses, ['new', 'triaged', 'in-progress', 'resolved', 'closed'])
    
    def test_invalid_status_transition_rejected(self):
        """Invalid statuses should be rejected."""
        case_id = db.create_case(self.conn, subject="Invalid test")
        
        with self.assertRaises(ValueError) as ctx:
            db.transition_status(self.conn, case_id, 'invalid_status')
        self.assertIn('Invalid status', str(ctx.exception))
    
    def test_no_history_for_unchanged_status(self):
        """No history entry should be added if status doesn't change."""
        case_id = db.create_case(self.conn, subject="No change test")
        
        # Update without changing status
        db.update_case(self.conn, case_id, priority='high')
        
        history = db.get_status_history(self.conn, case_id)
        self.assertEqual(len(history), 1)  # Only initial entry
    
    def test_legacy_open_filter_returns_new_cases(self):
        """Filtering by legacy 'open' status should return cases with 'new' status."""
        case_id = db.create_case(self.conn, subject="Legacy filter test")
        
        # Verify case has 'new' status
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'new')
        
        # Filter by 'open' should find it
        cases = db.list_cases(self.conn, status='open')
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]['id'], case_id)


class TestCaseNotes(unittest.TestCase):
    """Tests for case notes functionality."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_add_and_retrieve_notes(self):
        """Test adding and retrieving notes."""
        case_id = db.create_case(self.conn, subject="Notes test")
        
        note1_id = db.add_note(self.conn, case_id, "First observation", author='alice')
        note2_id = db.add_note(self.conn, case_id, "Follow-up details", author='bob')
        note3_id = db.add_note(self.conn, case_id, "Anonymous note")
        
        self.assertIsNotNone(note1_id)
        self.assertIsNotNone(note2_id)
        self.assertIsNotNone(note3_id)
        
        notes = db.get_notes(self.conn, case_id)
        self.assertEqual(len(notes), 3)
        
        self.assertEqual(notes[0]['content'], "First observation")
        self.assertEqual(notes[0]['author'], 'alice')
        
        self.assertEqual(notes[1]['content'], "Follow-up details")
        self.assertEqual(notes[1]['author'], 'bob')
        
        self.assertEqual(notes[2]['content'], "Anonymous note")
        self.assertIsNone(notes[2]['author'])
    
    def test_add_note_to_nonexistent_case(self):
        """Adding note to nonexistent case should return None."""
        result = db.add_note(self.conn, 9999, "Orphan note")
        self.assertIsNone(result)
    
    def test_get_notes_empty_case(self):
        """Getting notes for case with no notes returns empty list."""
        case_id = db.create_case(self.conn, subject="No notes")
        notes = db.get_notes(self.conn, case_id)
        self.assertEqual(notes, [])


if __name__ == '__main__':
    unittest.main()
