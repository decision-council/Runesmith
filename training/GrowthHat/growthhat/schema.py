"""SQLite schema for GrowthHat."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT '',
    url TEXT,
    notes TEXT DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT 'assumed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audiences (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    needs TEXT DEFAULT '',
    objections TEXT DEFAULT '',
    discovery_channels TEXT DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT 'assumed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS offers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    value_proposition TEXT DEFAULT '',
    audience_id TEXT,
    evidence_type TEXT NOT NULL DEFAULT 'assumed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (audience_id) REFERENCES audiences(id)
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    audience_id TEXT,
    offer_id TEXT,
    source_id TEXT,
    rationale TEXT DEFAULT '',
    evidence_type TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (audience_id) REFERENCES audiences(id),
    FOREIGN KEY (offer_id) REFERENCES offers(id),
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE TABLE IF NOT EXISTS tests (
    id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    name TEXT NOT NULL,
    method TEXT DEFAULT '',
    success_criteria TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'planned',
    evidence_type TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id)
);

CREATE TABLE IF NOT EXISTS outcomes (
    id TEXT PRIMARY KEY,
    test_id TEXT NOT NULL,
    result TEXT DEFAULT '',
    metrics TEXT DEFAULT '',
    interpretation TEXT DEFAULT '',
    supports_hypothesis INTEGER,
    confidence REAL,
    evidence_type TEXT NOT NULL DEFAULT 'measured',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (test_id) REFERENCES tests(id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    action TEXT DEFAULT '',
    reasoning TEXT DEFAULT '',
    uncertainty_level TEXT NOT NULL DEFAULT 'medium',
    source_ids TEXT DEFAULT '',
    hypothesis_id TEXT,
    outcome_id TEXT,
    evidence_type TEXT NOT NULL DEFAULT 'assumed',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (hypothesis_id) REFERENCES hypotheses(id),
    FOREIGN KEY (outcome_id) REFERENCES outcomes(id)
);

CREATE INDEX IF NOT EXISTS idx_offers_audience ON offers(audience_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_audience ON hypotheses(audience_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_offer ON hypotheses(offer_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_source ON hypotheses(source_id);
CREATE INDEX IF NOT EXISTS idx_tests_hypothesis ON tests(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_test ON outcomes(test_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_hypothesis ON recommendations(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_outcome ON recommendations(outcome_id);
"""


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    """Add column to table if missing (idempotent migration)."""
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(conn):
    """Initialize the database schema, migrating existing databases."""
    conn.executescript(SCHEMA_SQL)
    _ensure_column(conn, "outcomes", "confidence", "REAL")
    conn.commit()
