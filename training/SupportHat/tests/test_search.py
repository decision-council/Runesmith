"""Unit tests for SupportHat grounded search."""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db
from supporthat import documents
from supporthat import search


class TestGroundedSearch(unittest.TestCase):
    """Tests for grounded passage search."""
    
    def setUp(self):
        """Create temporary database and document directory."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_file.close()
        self.db_path = Path(self.db_file.name)
        self.conn = db.get_connection(self.db_path)
        
        self.doc_dir = tempfile.mkdtemp()
    
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
    
    def _create_doc(self, name, content):
        """Helper to create a test document."""
        file_path = Path(self.doc_dir) / name
        file_path.write_text(content, encoding='utf-8')
        return file_path
    
    def test_search_returns_matching_passage_with_citation(self):
        """Test that search returns passages containing query keywords with source citations."""
        content = """# HatOS Guide

Welcome to HatOS documentation.

The authentication module provides secure login.
Users can configure two-factor authentication.

For troubleshooting, check the logs."""
        self._create_doc('guide.md', content)
        documents.ingest_directory(self.conn, self.doc_dir)
        
        results = search.search_documents(self.conn, 'authentication')
        
        self.assertGreater(len(results), 0)
        result = results[0]
        
        # Check required fields exist
        self.assertIn('path', result)
        self.assertIn('passage', result)
        self.assertIn('line_start', result)
        self.assertIn('line_end', result)
        
        # Passage must contain the keyword (grounded, not synthesized)
        self.assertIn('authentication', result['passage'].lower())
        
        # Line numbers should be positive integers
        self.assertIsInstance(result['line_start'], int)
        self.assertIsInstance(result['line_end'], int)
        self.assertGreater(result['line_start'], 0)
        self.assertGreaterEqual(result['line_end'], result['line_start'])
    
    def test_search_returns_empty_for_absent_keyword(self):
        """Test that search returns empty list when no documents contain the query."""
        content = """# Simple Document

This document talks about cats and dogs.
Nothing about technology here."""
        self._create_doc('pets.md', content)
        documents.ingest_directory(self.conn, self.doc_dir)
        
        results = search.search_documents(self.conn, 'authentication')
        
        self.assertEqual(results, [])
    
    def test_search_reproducible_results(self):
        """Test that identical queries yield identical ordered results."""
        content = """# HatOS Features

HatOS provides authentication services.
The authentication module is secure.
Authorization comes after authentication."""
        self._create_doc('features.md', content)
        documents.ingest_directory(self.conn, self.doc_dir)
        
        results1 = search.search_documents(self.conn, 'authentication')
        results2 = search.search_documents(self.conn, 'authentication')
        
        self.assertEqual(results1, results2)
    
    def test_search_passage_is_exact_source_lines(self):
        """Test that passage content matches exact source lines at cited location."""
        content = """Line one here.
Line two here.
The zorblax feature is unique.
Line four here.
Line five here."""
        doc_path = self._create_doc('unique.md', content)
        documents.ingest_directory(self.conn, self.doc_dir)
        
        results = search.search_documents(self.conn, 'zorblax')
        
        self.assertEqual(len(results), 1)
        result = results[0]
        
        # Read the file and verify passage matches
        lines = content.split('\n')
        start_idx = result['line_start'] - 1  # Convert to 0-based
        end_idx = result['line_end']  # Exclusive for slice
        expected_passage = '\n'.join(lines[start_idx:end_idx])
        
        self.assertEqual(result['passage'], expected_passage)


if __name__ == '__main__':
    unittest.main()
