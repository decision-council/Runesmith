"""Unit tests for SupportHat document ingestion and indexing."""

import unittest
import tempfile
import os
from pathlib import Path

from supporthat import db
from supporthat import documents


class TestDocumentIngestion(unittest.TestCase):
    """Tests for document ingestion functionality."""
    
    def setUp(self):
        """Create temporary database and document directory."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_file.close()
        self.db_path = Path(self.db_file.name)
        self.conn = db.get_connection(self.db_path)
        
        # Create temp directory for test documents
        self.doc_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        self.conn.close()
        os.unlink(self.db_path)
        # Clean up document directory
        for root, dirs, files in os.walk(self.doc_dir, topdown=False):
            for name in files:
                os.unlink(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.doc_dir)
    
    def _create_doc(self, name, content, subdir=None):
        """Helper to create a test document."""
        if subdir:
            dir_path = Path(self.doc_dir) / subdir
            dir_path.mkdir(parents=True, exist_ok=True)
            file_path = dir_path / name
        else:
            file_path = Path(self.doc_dir) / name
        file_path.write_text(content, encoding='utf-8')
        return file_path
    
    def test_ingest_single_markdown_document(self):
        """Test ingesting a single markdown document."""
        self._create_doc('readme.md', '# HatOS Guide\n\nWelcome to HatOS documentation.')
        
        results = documents.ingest_directory(self.conn, self.doc_dir)
        
        self.assertEqual(results['ingested'], 1)
        self.assertEqual(results['skipped'], 0)
        self.assertEqual(results['errors'], 0)
        
        sources = documents.list_sources(self.conn)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['title'], 'HatOS Guide')
    
    def test_ingest_multiple_documents_recursive(self):
        """Test recursive ingestion of multiple documents."""
        self._create_doc('intro.txt', 'Introduction to HatOS features.')
        self._create_doc('install.md', '# Installation\n\nHow to install HatOS.')
        self._create_doc('config.md', '# Configuration\n\nConfiguration options.', subdir='guides')
        
        results = documents.ingest_directory(self.conn, self.doc_dir)
        
        self.assertEqual(results['ingested'], 3)
        sources = documents.list_sources(self.conn)
        self.assertEqual(len(sources), 3)
    
    def test_skip_unsupported_extensions(self):
        """Test that unsupported file extensions are ignored."""
        self._create_doc('doc.md', '# Valid Document')
        self._create_doc('image.png', 'not really an image')
        self._create_doc('data.json', '{"key": "value"}')
        self._create_doc('script.py', 'print("hello")')
        
        results = documents.ingest_directory(self.conn, self.doc_dir)
        
        self.assertEqual(results['ingested'], 1)
        sources = documents.list_sources(self.conn)
        self.assertEqual(len(sources), 1)
        self.assertIn('doc.md', sources[0]['path'])
    
    def test_idempotent_ingestion_preserves_ids(self):
        """Test that re-ingesting unchanged files does not duplicate or change IDs."""
        self._create_doc('stable.md', '# Stable Document\n\nThis content will not change.')
        
        # First ingestion
        results1 = documents.ingest_directory(self.conn, self.doc_dir)
        self.assertEqual(results1['ingested'], 1)
        sources1 = documents.list_sources(self.conn)
        original_id = sources1[0]['id']
        
        # Second ingestion of same content
        results2 = documents.ingest_directory(self.conn, self.doc_dir)
        self.assertEqual(results2['ingested'], 0)
        self.assertEqual(results2['skipped'], 1)
        
        # Verify same ID preserved
        sources2 = documents.list_sources(self.conn)
        self.assertEqual(len(sources2), 1)
        self.assertEqual(sources2[0]['id'], original_id)
    
    def test_persistence_across_connections(self):
        """Test that indexed documents persist after reopening database."""
        self._create_doc('persist.md', '# Persistent\n\nShould survive reconnect.')
        
        documents.ingest_directory(self.conn, self.doc_dir)
        self.conn.close()
        
        # Reopen connection
        self.conn = db.get_connection(self.db_path)
        sources = documents.list_sources(self.conn)
        
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]['title'], 'Persistent')
    
    def test_keyword_extraction(self):
        """Test that keywords are extracted from document content."""
        self._create_doc('keywords.md', '# HatOS Features\n\nHatOS provides authentication and authorization services.')
        
        documents.ingest_directory(self.conn, self.doc_dir)
        sources = documents.list_sources(self.conn)
        doc_id = sources[0]['id']
        
        keywords = documents.get_document_keywords(self.conn, doc_id)
        keyword_words = [k['keyword'] for k in keywords]
        
        # Check some expected keywords exist
        self.assertIn('hatos', keyword_words)
        self.assertIn('authentication', keyword_words)
        self.assertIn('authorization', keyword_words)
        # Common stopwords should be filtered
        self.assertNotIn('and', keyword_words)
        self.assertNotIn('the', keyword_words)
    
    def test_identical_content_different_paths_get_distinct_ids(self):
        """Test that different files with identical content get separate IDs."""
        identical_content = '# Identical\n\nThis content is the same in both files.'
        self._create_doc('file_a.md', identical_content)
        self._create_doc('file_b.md', identical_content)
        
        results = documents.ingest_directory(self.conn, self.doc_dir)
        
        # Both should be ingested as new
        self.assertEqual(results['ingested'], 2)
        self.assertEqual(results['skipped'], 0)
        
        sources = documents.list_sources(self.conn)
        self.assertEqual(len(sources), 2)
        
        # Verify distinct IDs
        ids = [s['id'] for s in sources]
        self.assertEqual(len(set(ids)), 2)  # Two unique IDs
        
        # Verify both paths are present
        paths = [s['path'] for s in sources]
        self.assertTrue(any('file_a.md' in p for p in paths))
        self.assertTrue(any('file_b.md' in p for p in paths))
    
    def test_reingestion_preserves_both_identical_files(self):
        """Test that re-ingestion preserves both files with identical content."""
        identical_content = '# Same\n\nIdentical content here.'
        self._create_doc('first.md', identical_content)
        self._create_doc('second.md', identical_content)
        
        # First ingestion
        documents.ingest_directory(self.conn, self.doc_dir)
        sources1 = documents.list_sources(self.conn)
        ids1 = {s['path']: s['id'] for s in sources1}
        
        # Second ingestion
        documents.ingest_directory(self.conn, self.doc_dir)
        sources2 = documents.list_sources(self.conn)
        ids2 = {s['path']: s['id'] for s in sources2}
        
        # Both files should still exist with same IDs
        self.assertEqual(len(sources2), 2)
        for path, doc_id in ids1.items():
            self.assertIn(path, ids2)
            self.assertEqual(ids2[path], doc_id)


class TestDocumentCompatibility(unittest.TestCase):
    """Tests that document ingestion doesn't break existing case functionality."""
    
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_file.close()
        self.db_path = Path(self.db_file.name)
        self.conn = db.get_connection(self.db_path)
        self.doc_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        self.conn.close()
        os.unlink(self.db_path)
        for root, dirs, files in os.walk(self.doc_dir, topdown=False):
            for name in files:
                os.unlink(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.doc_dir)
    
    def test_cases_work_after_document_ingestion(self):
        """Test that case operations continue working after document ingestion."""
        # Create a case first
        case_id = db.create_case(self.conn, subject='Test case before docs')
        
        # Ingest documents
        doc_path = Path(self.doc_dir) / 'test.md'
        doc_path.write_text('# Test Doc\n\nTest content.')
        documents.ingest_directory(self.conn, self.doc_dir)
        
        # Verify case operations still work
        case = db.get_case(self.conn, case_id)
        self.assertIsNotNone(case)
        self.assertEqual(case['subject'], 'Test case before docs')
        
        # Create another case after ingestion
        case_id2 = db.create_case(self.conn, subject='Test case after docs')
        case2 = db.get_case(self.conn, case_id2)
        self.assertIsNotNone(case2)
        
        # Triage and transition still work
        db.triage_case(self.conn, case_id, priority='high', assignee='alice')
        case = db.get_case(self.conn, case_id)
        self.assertEqual(case['status'], 'triaged')
        self.assertEqual(case['priority'], 'high')


if __name__ == '__main__':
    unittest.main()
