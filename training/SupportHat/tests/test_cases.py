"""Unit tests for SupportHat case management."""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db


class TestCaseDatabase(unittest.TestCase):
    """Tests for case database operations."""
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_create_and_retrieve_case(self):
        """Test creating a case and retrieving it by ID."""
        case_id = db.create_case(
            self.conn,
            subject="HatOS won't boot after update",
            description="User reports black screen after v2.1 update",
            priority='high',
            source='email',
            assignee='alice'
        )
        
        self.assertIsInstance(case_id, int)
        self.assertGreater(case_id, 0)
        
        case = db.get_case(self.conn, case_id)
        self.assertIsNotNone(case)
        self.assertEqual(case['subject'], "HatOS won't boot after update")
        self.assertEqual(case['status'], 'new')
        self.assertEqual(case['priority'], 'high')
        self.assertEqual(case['source'], 'email')
        self.assertEqual(case['assignee'], 'alice')
    
    def test_list_cases_with_filters(self):
        """Test listing cases with status and assignee filters."""
        db.create_case(self.conn, subject="Case A", assignee='alice')
        case_b_id = db.create_case(self.conn, subject="Case B", assignee='bob')
        db.create_case(self.conn, subject="Case C", assignee='alice')
        
        db.update_case(self.conn, case_b_id, status='resolved')
        
        # Filter by assignee
        alice_cases = db.list_cases(self.conn, assignee='alice')
        self.assertEqual(len(alice_cases), 2)
        
        # Filter by status
        new_cases = db.list_cases(self.conn, status='new')
        self.assertEqual(len(new_cases), 2)
        
        resolved_cases = db.list_cases(self.conn, status='resolved')
        self.assertEqual(len(resolved_cases), 1)
        self.assertEqual(resolved_cases[0]['subject'], 'Case B')
    
    def test_update_case_fields(self):
        """Test updating various case fields."""
        case_id = db.create_case(
            self.conn,
            subject="Original subject",
            priority='normal'
        )
        
        success = db.update_case(
            self.conn,
            case_id,
            status='in-progress',
            priority='urgent',
            assignee='charlie'
        )
        self.assertTrue(success)
        
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'in-progress')
        self.assertEqual(case['priority'], 'urgent')
        self.assertEqual(case['assignee'], 'charlie')
    
    def test_persistence_across_connections(self):
        """Test that data persists when connection is closed and reopened."""
        case_id = db.create_case(
            self.conn,
            subject="Persistent case",
            description="Should survive reconnect"
        )
        self.conn.close()
        
        # Reopen connection
        self.conn = db.get_connection(self.db_path)
        case = db.get_case(self.conn, case_id)
        
        self.assertIsNotNone(case)
        self.assertEqual(case['subject'], "Persistent case")
        self.assertEqual(case['description'], "Should survive reconnect")


class TestCaseValidation(unittest.TestCase):
    """Tests for case validation."""
    
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_file.close()
        self.db_path = Path(self.temp_file.name)
        self.conn = db.get_connection(self.db_path)
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
    
    def test_invalid_priority_rejected(self):
        """Test that invalid priorities are rejected."""
        with self.assertRaises(ValueError) as ctx:
            db.create_case(self.conn, subject="Test", priority='critical')
        self.assertIn('Invalid priority', str(ctx.exception))
    
    def test_invalid_status_rejected(self):
        """Test that invalid statuses are rejected."""
        case_id = db.create_case(self.conn, subject="Test")
        with self.assertRaises(ValueError) as ctx:
            db.update_case(self.conn, case_id, status='done')
        self.assertIn('Invalid status', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
