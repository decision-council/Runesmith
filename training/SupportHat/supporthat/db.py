"""Database schema and connection management for SupportHat."""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

DEFAULT_DB_PATH = Path("supporthat.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'new',
    priority TEXT NOT NULL DEFAULT 'normal',
    source TEXT,
    assignee TEXT,
    subject TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_priority ON cases(priority);
CREATE INDEX IF NOT EXISTS idx_cases_assignee ON cases(assignee);

CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by TEXT,
    note TEXT,
    changed_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_status_history_case ON status_history(case_id);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    author TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_notes_case ON notes(case_id);
"""

VALID_STATUSES = ('new', 'triaged', 'in-progress', 'resolved', 'closed')
VALID_PRIORITIES = ('low', 'normal', 'high', 'urgent')

# Legacy status mapping for backward compatibility
LEGACY_STATUS_MAP = {
    'open': 'new',
    'in_progress': 'in-progress',
    'pending': 'triaged',
}


def get_connection(db_path=None):
    """Get a database connection, creating schema if needed."""
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _normalize_status(status):
    """Normalize legacy status values to new ones."""
    if status in LEGACY_STATUS_MAP:
        return LEGACY_STATUS_MAP[status]
    return status


def create_case(conn, subject, description=None, priority='normal', source=None, assignee=None):
    """Create a new case and return its ID."""
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {priority}. Must be one of {VALID_PRIORITIES}")
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        """INSERT INTO cases (subject, description, priority, source, assignee, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, 'new', ?, ?)""",
        (subject, description, priority, source, assignee, now, now)
    )
    case_id = cursor.lastrowid
    conn.execute(
        """INSERT INTO status_history (case_id, old_status, new_status, changed_at)
           VALUES (?, NULL, 'new', ?)""",
        (case_id, now)
    )
    conn.commit()
    return case_id


def get_case(conn, case_id):
    """Retrieve a single case by ID."""
    cursor = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,))
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def list_cases(conn, status=None, assignee=None, limit=50):
    """List cases with optional filters.
    
    Supports legacy status filters which match both the legacy value stored
    in first-slice databases and the normalized current value:
    - 'open' matches 'open' or 'new'
    - 'in_progress' matches 'in_progress' or 'in-progress'
    - 'pending' matches 'pending' or 'triaged'
    - 'resolved' and 'closed' match directly
    """
    query = "SELECT * FROM cases WHERE 1=1"
    params = []
    if status:
        if status in LEGACY_STATUS_MAP:
            # Legacy filter: match both the raw legacy value and the normalized value
            normalized = LEGACY_STATUS_MAP[status]
            query += " AND (status = ? OR status = ?)"
            params.append(status)
            params.append(normalized)
        else:
            # Native status or direct match
            query += " AND status = ?"
            params.append(status)
    if assignee:
        query += " AND assignee = ?"
        params.append(assignee)
    query += " ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 WHEN 'low' THEN 4 END, created_at DESC"
    query += " LIMIT ?"
    params.append(limit)
    cursor = conn.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def update_case(conn, case_id, changed_by=None, note=None, **fields):
    """Update a case with given fields. Returns True if case existed."""
    if 'status' in fields:
        fields['status'] = _normalize_status(fields['status'])
        if fields['status'] not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {fields['status']}. Must be one of {VALID_STATUSES}")
    if 'priority' in fields and fields['priority'] not in VALID_PRIORITIES:
        raise ValueError(f"Invalid priority: {fields['priority']}. Must be one of {VALID_PRIORITIES}")
    
    allowed = {'status', 'priority', 'source', 'assignee', 'subject', 'description'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    
    old_case = get_case(conn, case_id)
    if old_case is None:
        return False
    
    now = datetime.utcnow().isoformat()
    updates['updated_at'] = now
    set_clause = ', '.join(f"{k} = ?" for k in updates.keys())
    params = list(updates.values()) + [case_id]
    
    cursor = conn.execute(f"UPDATE cases SET {set_clause} WHERE id = ?", params)
    
    if 'status' in fields and fields['status'] != old_case['status']:
        conn.execute(
            """INSERT INTO status_history (case_id, old_status, new_status, changed_by, note, changed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (case_id, old_case['status'], fields['status'], changed_by, note, now)
        )
    
    conn.commit()
    return cursor.rowcount > 0


def triage_case(conn, case_id, priority=None, assignee=None, note=None, changed_by=None):
    """Triage a case: set to triaged status, optionally set priority and assignee."""
    case = get_case(conn, case_id)
    if case is None:
        return False
    
    fields = {'status': 'triaged'}
    if priority:
        fields['priority'] = priority
    if assignee is not None:
        fields['assignee'] = assignee if assignee != '' else None
    
    return update_case(conn, case_id, changed_by=changed_by, note=note, **fields)


def transition_status(conn, case_id, new_status, changed_by=None, note=None):
    """Transition a case to a new status, recording history."""
    new_status = _normalize_status(new_status)
    if new_status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {VALID_STATUSES}")
    return update_case(conn, case_id, changed_by=changed_by, note=note, status=new_status)


def get_status_history(conn, case_id):
    """Get the status transition history for a case."""
    cursor = conn.execute(
        """SELECT id, old_status, new_status, changed_by, note, changed_at
           FROM status_history WHERE case_id = ? ORDER BY changed_at ASC""",
        (case_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def add_note(conn, case_id, content, author=None):
    """Add a note to a case. Returns note ID or None if case doesn't exist."""
    case = get_case(conn, case_id)
    if case is None:
        return None
    now = datetime.utcnow().isoformat()
    cursor = conn.execute(
        """INSERT INTO notes (case_id, author, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (case_id, author, content, now)
    )
    conn.commit()
    return cursor.lastrowid


def get_notes(conn, case_id):
    """Get all notes for a case."""
    cursor = conn.execute(
        """SELECT id, author, content, created_at FROM notes
           WHERE case_id = ? ORDER BY created_at ASC""",
        (case_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
