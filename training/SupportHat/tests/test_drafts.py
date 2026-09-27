"""Unit tests for SupportHat grounded response draft generation."""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db
from supporthat import documents
from supporthat import drafts


class TestDraftGeneration(unittest.TestCase):
    """Tests for response draft generation and persistence."""
    
    def setUp(self):
        """Create temporary database and document directory."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_file.close()
        self.db_path = Path(self.db_file.name)
        self.conn = db.get_connection(self.db_path)
        
        self.doc_dir = tempfile.mkdtemp()
        content = """# HatOS Guide

Welcome to HatOS documentation.

The authentication module provides secure login.
Users can configure two-factor authentication.

For troubleshooting, check the logs."""
        self.doc_path = Path(self.doc_dir) / 'guide.md'
        self.doc_path.write_text(content, encoding='utf-8')
        self.doc_content = content
        documents.ingest_directory(self.conn, self.doc_dir)
        
        self.case_id = db.create_case(
            self.conn,
            subject="Cannot login to HatOS",
            description="User cannot complete authentication"
        )
    
    def tearDown(self):
        """Clean up temporary files."""
        self.conn.close()
        os.unlink(self.db_path)
        for root, dirs, files in os.walk(self.doc_dir, topdown=False):
            for name in files:
                os.unlink(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.doc_dir)
    
    def _verify_citation_in_source(self, citation):
        """Verify a citation's passage matches exact lines in current source."""
        content = Path(citation['path']).read_text(encoding='utf-8')
        lines = content.split('\n')
        expected = '\n'.join(
            lines[citation['line_start'] - 1:citation['line_end']]
        )
        self.assertEqual(citation['passage'], expected)
    
    def test_grounded_draft_quotes_cited_passage(self):
        """Grounded draft quotes at least one complete cited passage with a source reference."""
        record = drafts.create_draft(self.conn, self.case_id,
                                     query='authentication')
        
        self.assertIsInstance(record['id'], int)
        self.assertEqual(record['case_id'], self.case_id)
        self.assertIsInstance(record['case_id'], int)
        self.assertIs(record['grounded'], True)
        self.assertGreater(len(record['citations']), 0)
        
        citation = record['citations'][0]
        for key in ('path', 'passage', 'line_start', 'line_end'):
            self.assertIn(key, citation)
        self.assertIsInstance(citation['line_start'], int)
        self.assertIsInstance(citation['line_end'], int)
        
        # Draft quotes at least one complete cited passage with a source reference
        self.assertIn(citation['passage'], record['text'])
        self.assertIn(citation['path'], record['text'])
        
        # Every citation is verifiable in the current source
        for c in record['citations']:
            self._verify_citation_in_source(c)
    
    def test_draft_persists_across_reopening(self):
        """Stored draft is reproduced exactly after closing and reopening the DB."""
        record = drafts.create_draft(self.conn, self.case_id,
                                     query='authentication')
        self.conn.close()
        
        self.conn = db.get_connection(self.db_path)
        stored = drafts.list_drafts(self.conn, self.case_id)
        
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0], record)
    
    def test_absence_flags_grounded_false(self):
        """No relevant passage yields grounded=false, empty citations, and clear message."""
        record = drafts.create_draft(self.conn, self.case_id,
                                     query='zorblaxnonexistent')
        
        self.assertIs(record['grounded'], False)
        self.assertEqual(record['citations'], [])
        self.assertTrue(record['text'].strip())
        self.assertIn('Insufficient evidence', record['text'])
        
        # Stored draft matches returned record
        stored = drafts.list_drafts(self.conn, self.case_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0], record)
    
    def test_nonexistent_case_persists_nothing(self):
        """A nonexistent case ID returns None and stores no draft."""
        result = drafts.create_draft(self.conn, 99999, query='authentication')
        self.assertIsNone(result)
        self.assertEqual(drafts.list_drafts(self.conn, 99999), [])
    
    def test_default_query_uses_case_subject(self):
        """Omitted --query falls back to case subject/description."""
        record = drafts.create_draft(self.conn, self.case_id)
        self.assertIn('Cannot login to HatOS', record['query'])
        self.assertIs(record['grounded'], True)
    
    def test_existing_case_data_preserved(self):
        """Draft generation does not modify case data or indexed documents."""
        before_case = db.get_case(self.conn, self.case_id)
        before_sources = documents.list_sources(self.conn)
        
        drafts.create_draft(self.conn, self.case_id, query='authentication')
        
        self.assertEqual(db.get_case(self.conn, self.case_id), before_case)
        self.assertEqual(documents.list_sources(self.conn), before_sources)


if __name__ == '__main__':
    unittest.main()
