"""Grounded response draft generation and storage for SupportHat.

Drafts are composed only from passages returned by the existing search
module. Each citation retains the source path, exact passage text, and
1-based line_start/line_end so it can be verified against the current
source file. Drafts are stored locally on their case and are never sent.
No network or sender calls are made, and case status/history is not
modified to imply resolution or sending.
"""

import json
from datetime import datetime

from . import db
from . import search


DRAFT_SCHEMA = """
CREATE TABLE IF NOT EXISTS response_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    query TEXT NOT NULL,
    text TEXT NOT NULL,
    grounded INTEGER NOT NULL,
    citations TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_response_drafts_case ON response_drafts(case_id);
"""

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "Insufficient evidence found in the indexed source documents to answer "
    "this query. No grounded response can be drafted without inventing "
    "facts. Please index relevant product documentation and try again."
)


def init_draft_schema(conn):
    """Initialize the response_drafts table if it does not exist."""
    conn.executescript(DRAFT_SCHEMA)
    conn.commit()


def _citation_reference(citation):
    """Build a human-readable source reference for a citation."""
    return "{} (lines {}-{})".format(
        citation['path'], citation['line_start'], citation['line_end']
    )


def _compose_grounded_text(query, citations):
    """Compose draft text quoting complete cited passages with references.

    The draft quotes at least one complete cited passage verbatim and
    includes an explicit source reference for every quoted passage.
    It never synthesizes product facts beyond the quoted source text.
    """
    parts = [
        "Thank you for contacting HatOS support.",
        "",
        "Based on our documentation, here is the relevant information:",
    ]
    for citation in citations:
        parts.append("")
        parts.append(citation['passage'])
        parts.append("")
        parts.append("Source: {}".format(_citation_reference(citation)))
    parts.append("")
    parts.append(
        "If this does not resolve your issue, please reply with more details."
    )
    return '\n'.join(parts)


def _row_to_record(row):
    """Convert a response_drafts row into the public draft record format.

    Returns dict with id, integer case_id, text, boolean grounded,
    and citations (list of dicts with path, passage, line_start, line_end).
    """
    return {
        'id': row['id'],
        'case_id': row['case_id'],
        'query': row['query'],
        'text': row['text'],
        'grounded': bool(row['grounded']),
        'citations': json.loads(row['citations']),
        'created_at': row['created_at'],
    }


def create_draft(conn, case_id, query=None):
    """Generate and persist a response draft for a case.

    query is the explicit search query; if None, the case subject and
    description are used. Returns the stored record dict, or None if the
    case does not exist (nothing is persisted in that case).

    When no relevant passage is found, the draft is stored with
    grounded=false, citations=[], and a clear insufficient-evidence text.
    """
    init_draft_schema(conn)

    case = db.get_case(conn, case_id)
    if case is None:
        return None

    if query is None:
        query = case['subject']
        if case.get('description'):
            query = "{} {}".format(case['subject'], case['description'])

    passages = search.search_documents(conn, query)

    if not passages:
        text = INSUFFICIENT_EVIDENCE_MESSAGE
        grounded = False
        citations = []
    else:
        citations = [
            {
                'path': p['path'],
                'passage': p['passage'],
                'line_start': p['line_start'],
                'line_end': p['line_end'],
            }
            for p in passages[:3]
        ]
        text = _compose_grounded_text(query, citations)
        grounded = True

    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        """INSERT INTO response_drafts (case_id, query, text, grounded, citations, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (case_id, query, text, 1 if grounded else 0, json.dumps(citations), now)
    )
    conn.commit()

    return {
        'id': cursor.lastrowid,
        'case_id': case_id,
        'query': query,
        'text': text,
        'grounded': grounded,
        'citations': citations,
        'created_at': now,
    }


def list_drafts(conn, case_id):
    """List stored response drafts for a case.

    Returns a list of draft record dicts (as produced by create_draft),
    ordered by id. Returns an empty list if no drafts exist for the case.
    """
    init_draft_schema(conn)
    cursor = conn.execute(
        """SELECT id, case_id, query, text, grounded, citations, created_at
           FROM response_drafts WHERE case_id = ? ORDER BY id ASC""",
        (case_id,)
    )
    return [_row_to_record(row) for row in cursor.fetchall()]
