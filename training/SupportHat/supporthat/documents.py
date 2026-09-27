"""Document ingestion and keyword indexing for SupportHat."""

import hashlib
import os
import re
from datetime import datetime
from pathlib import Path


DOCUMENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    content_hash TEXT NOT NULL,
    title TEXT,
    ingested_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);

CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    frequency INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_document ON keywords(document_id);
"""

SUPPORTED_EXTENSIONS = {'.txt', '.md'}


def init_document_schema(conn):
    """Initialize document tables if they don't exist."""
    conn.executescript(DOCUMENT_SCHEMA)
    conn.commit()


def compute_content_hash(content):
    """Compute SHA-256 hash of document content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def extract_keywords(content):
    """Extract keywords from document content.
    
    Returns a dict of keyword -> frequency.
    Converts to lowercase, filters short words and common stopwords.
    """
    # Simple tokenization: split on non-alphanumeric characters
    words = re.findall(r'[a-zA-Z0-9]+', content.lower())
    
    # Common English stopwords to filter out
    stopwords = {
        'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'it', 'its', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she',
        'we', 'they', 'what', 'which', 'who', 'whom', 'when', 'where', 'why',
        'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
        'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than',
        'too', 'very', 'just', 'also', 'now', 'here', 'there', 'then', 'once',
        'if', 'as', 'any', 'about', 'into', 'through', 'during', 'before',
        'after', 'above', 'below', 'up', 'down', 'out', 'off', 'over', 'under',
        'again', 'further', 'because', 'until', 'while'
    }
    
    keyword_freq = {}
    for word in words:
        # Skip short words (less than 3 chars) and stopwords
        if len(word) >= 3 and word not in stopwords:
            keyword_freq[word] = keyword_freq.get(word, 0) + 1
    
    return keyword_freq


def extract_title(content, file_path):
    """Extract title from document content or use filename.
    
    For markdown, looks for first # heading.
    Falls back to filename without extension.
    """
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('# '):
            return line[2:].strip()
    # Fall back to filename
    return Path(file_path).stem


def get_document_by_hash(conn, content_hash):
    """Get document by content hash."""
    cursor = conn.execute(
        "SELECT id, path, content_hash, title, ingested_at FROM documents WHERE content_hash = ?",
        (content_hash,)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def get_document_by_path(conn, path):
    """Get document by file path."""
    cursor = conn.execute(
        "SELECT id, path, content_hash, title, ingested_at FROM documents WHERE path = ?",
        (str(path),)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def ingest_document(conn, file_path, content):
    """Ingest a single document into the index.
    
    Returns (document_id, is_new) tuple.
    Document identity is by path: different files with identical content
    get separate entries with distinct IDs. Re-ingesting the same path
    with unchanged content preserves the existing ID.
    """
    content_hash = compute_content_hash(content)
    
    # Check if document with same path already exists
    existing = get_document_by_path(conn, file_path)
    if existing:
        # Same path exists - check if content changed
        if existing['content_hash'] == content_hash:
            # Unchanged - skip, preserve ID
            return existing['id'], False
        else:
            # Content changed - update hash, title, and keywords
            title = extract_title(content, file_path)
            now = datetime.utcnow().isoformat()
            conn.execute(
                "UPDATE documents SET content_hash = ?, title = ?, ingested_at = ? WHERE id = ?",
                (content_hash, title, now, existing['id'])
            )
            # Remove old keywords and add new ones
            conn.execute("DELETE FROM keywords WHERE document_id = ?", (existing['id'],))
            keywords = extract_keywords(content)
            for keyword, freq in keywords.items():
                conn.execute(
                    """INSERT INTO keywords (document_id, keyword, frequency)
                       VALUES (?, ?, ?)""",
                    (existing['id'], keyword, freq)
                )
            conn.commit()
            return existing['id'], False
    
    # Insert new document
    title = extract_title(content, file_path)
    now = datetime.utcnow().isoformat()
    
    cursor = conn.execute(
        """INSERT INTO documents (path, content_hash, title, ingested_at)
           VALUES (?, ?, ?, ?)""",
        (str(file_path), content_hash, title, now)
    )
    doc_id = cursor.lastrowid
    
    # Extract and store keywords
    keywords = extract_keywords(content)
    for keyword, freq in keywords.items():
        conn.execute(
            """INSERT INTO keywords (document_id, keyword, frequency)
               VALUES (?, ?, ?)""",
            (doc_id, keyword, freq)
        )
    
    conn.commit()
    return doc_id, True


def ingest_directory(conn, directory_path):
    """Recursively ingest all supported documents from a directory.
    
    Returns dict with 'ingested', 'skipped', 'errors' counts and 'files' list.
    Does not modify input documents or perform network access.
    """
    init_document_schema(conn)
    
    directory = Path(directory_path)
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory_path}")
    
    results = {
        'ingested': 0,
        'skipped': 0,
        'errors': 0,
        'files': []
    }
    
    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = Path(root) / filename
            ext = file_path.suffix.lower()
            
            # Skip unsupported extensions
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8')
                doc_id, is_new = ingest_document(conn, file_path, content)
                
                if is_new:
                    results['ingested'] += 1
                else:
                    results['skipped'] += 1
                
                results['files'].append({
                    'path': str(file_path),
                    'id': doc_id,
                    'new': is_new
                })
            except Exception as e:
                results['errors'] += 1
                results['files'].append({
                    'path': str(file_path),
                    'error': str(e)
                })
    
    return results


def list_sources(conn):
    """List all indexed document sources.
    
    Returns list of dicts with 'id', 'path', 'title', 'ingested_at'.
    """
    init_document_schema(conn)
    
    cursor = conn.execute(
        """SELECT id, path, title, ingested_at FROM documents
           ORDER BY id ASC"""
    )
    return [dict(row) for row in cursor.fetchall()]


def get_document(conn, doc_id):
    """Get a single document by ID."""
    cursor = conn.execute(
        "SELECT id, path, content_hash, title, ingested_at FROM documents WHERE id = ?",
        (doc_id,)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def get_document_keywords(conn, doc_id):
    """Get keywords for a document."""
    cursor = conn.execute(
        """SELECT keyword, frequency FROM keywords
           WHERE document_id = ? ORDER BY frequency DESC""",
        (doc_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
