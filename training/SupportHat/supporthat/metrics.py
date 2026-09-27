"""Metrics tracking for SupportHat.

Tracks resolution time, handoff counts, unanswered cases, and quality feedback.
All operations are local-only with no network calls.
"""

from datetime import datetime

from . import db
from . import drafts


METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_handoffs_case ON handoffs(case_id);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL,
    rating INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX IF NOT EXISTS idx_feedback_case ON feedback(case_id);
"""


def init_metrics_schema(conn):
    """Initialize metrics tables if they don't exist."""
    conn.executescript(METRICS_SCHEMA)
    conn.commit()


def record_handoff(conn, case_id):
    """Record a handoff for a case.
    
    Increments the handoff counter without changing case status.
    Returns True if successful, False if case doesn't exist.
    """
    init_metrics_schema(conn)
    
    case = db.get_case(conn, case_id)
    if case is None:
        return False
    
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO handoffs (case_id, recorded_at) VALUES (?, ?)",
        (case_id, now)
    )
    conn.commit()
    return True


def get_handoff_count(conn, case_id):
    """Get the handoff count for a specific case."""
    init_metrics_schema(conn)
    cursor = conn.execute(
        "SELECT COUNT(*) as count FROM handoffs WHERE case_id = ?",
        (case_id,)
    )
    return cursor.fetchone()['count']


def record_feedback(conn, case_id, rating):
    """Record quality feedback for a case.
    
    Rating must be an integer 1-5 inclusive.
    Returns True if successful, False if case doesn't exist.
    Raises ValueError if rating is out of range.
    """
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise ValueError("Rating must be an integer from 1 to 5")
    
    init_metrics_schema(conn)
    
    case = db.get_case(conn, case_id)
    if case is None:
        return False
    
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO feedback (case_id, rating, recorded_at) VALUES (?, ?, ?)",
        (case_id, rating, now)
    )
    conn.commit()
    return True


def list_feedback(conn, case_id):
    """List all feedback entries for a case.
    
    Returns list of dicts with id, case_id, rating, recorded_at.
    """
    init_metrics_schema(conn)
    cursor = conn.execute(
        """SELECT id, case_id, rating, recorded_at FROM feedback
           WHERE case_id = ? ORDER BY id ASC""",
        (case_id,)
    )
    return [dict(row) for row in cursor.fetchall()]


def _compute_resolution_time_seconds(case):
    """Compute resolution time in seconds from case timestamps.
    
    Returns seconds between created_at and updated_at for resolved/closed cases.
    Returns None for non-resolved cases.
    """
    if case['status'] not in ('resolved', 'closed'):
        return None
    
    created = datetime.fromisoformat(case['created_at'])
    updated = datetime.fromisoformat(case['updated_at'])
    delta = updated - created
    return delta.total_seconds()


def get_metrics_summary(conn):
    """Get metrics summary.
    
    Returns dict with:
    - resolved_count: number of cases in resolved or closed status
    - total_handoffs: total handoff count across all cases
    - unanswered_count: cases in new/triaged status with no draft
    - feedback_count: total number of feedback ratings
    - average_rating: average rating (null/None if no ratings)
    - avg_resolution_time_seconds: average resolution time in seconds (null if none)
    """
    init_metrics_schema(conn)
    drafts.init_draft_schema(conn)
    
    # Count resolved/closed cases
    cursor = conn.execute(
        "SELECT COUNT(*) as count FROM cases WHERE status IN ('resolved', 'closed')"
    )
    resolved_count = cursor.fetchone()['count']
    
    # Total handoffs
    cursor = conn.execute("SELECT COUNT(*) as count FROM handoffs")
    total_handoffs = cursor.fetchone()['count']
    
    # Unanswered: new or triaged cases with no draft
    cursor = conn.execute(
        """SELECT COUNT(*) as count FROM cases c
           WHERE c.status IN ('new', 'triaged')
           AND NOT EXISTS (
               SELECT 1 FROM response_drafts d WHERE d.case_id = c.id
           )"""
    )
    unanswered_count = cursor.fetchone()['count']
    
    # Feedback stats
    cursor = conn.execute("SELECT COUNT(*) as count, AVG(rating) as avg FROM feedback")
    row = cursor.fetchone()
    feedback_count = row['count']
    average_rating = row['avg']  # Will be None if no ratings
    
    # Average resolution time
    cursor = conn.execute(
        "SELECT id, status, created_at, updated_at FROM cases WHERE status IN ('resolved', 'closed')"
    )
    resolution_times = []
    for case_row in cursor.fetchall():
        case = dict(case_row)
        rt = _compute_resolution_time_seconds(case)
        if rt is not None:
            resolution_times.append(rt)
    
    if resolution_times:
        avg_resolution_time_seconds = sum(resolution_times) / len(resolution_times)
    else:
        avg_resolution_time_seconds = None
    
    return {
        'resolved_count': resolved_count,
        'total_handoffs': total_handoffs,
        'unanswered_count': unanswered_count,
        'feedback_count': feedback_count,
        'average_rating': average_rating,
        'avg_resolution_time_seconds': avg_resolution_time_seconds
    }
