"""Repository layer for GrowthHat persistence."""

import math
import sqlite3
from datetime import datetime
from typing import List, Optional, Type, TypeVar

from .models import (
    EvidenceType,
    Source,
    Audience,
    Offer,
    Hypothesis,
    Test,
    Outcome,
    Recommendation,
)
from .schema import init_db

T = TypeVar("T")

# Mapping from model class to table name and fields
MODEL_CONFIG = {
    Source: {
        "table": "sources",
        "fields": ["id", "name", "source_type", "url", "notes", "evidence_type", "created_at", "updated_at"],
    },
    Audience: {
        "table": "audiences",
        "fields": ["id", "name", "description", "needs", "objections", "discovery_channels", "evidence_type", "created_at", "updated_at"],
    },
    Offer: {
        "table": "offers",
        "fields": ["id", "name", "description", "value_proposition", "audience_id", "evidence_type", "created_at", "updated_at"],
    },
    Hypothesis: {
        "table": "hypotheses",
        "fields": ["id", "statement", "audience_id", "offer_id", "source_id", "rationale", "evidence_type", "created_at", "updated_at"],
    },
    Test: {
        "table": "tests",
        "fields": ["id", "hypothesis_id", "name", "method", "success_criteria", "status", "evidence_type", "created_at", "updated_at"],
    },
    Outcome: {
        "table": "outcomes",
        "fields": ["id", "test_id", "result", "metrics", "interpretation", "supports_hypothesis", "confidence", "evidence_type", "created_at", "updated_at"],
    },
    Recommendation: {
        "table": "recommendations",
        "fields": ["id", "title", "description", "action", "reasoning", "uncertainty_level", "source_ids", "hypothesis_id", "outcome_id", "evidence_type", "created_at", "updated_at"],
    },
}


class Repository:
    """SQLite-backed repository for all GrowthHat entities."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        init_db(self.conn)

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def _to_db_value(self, value):
        """Convert Python value to database value."""
        if isinstance(value, EvidenceType):
            return value.value
        if isinstance(value, bool):
            return 1 if value else 0
        return value

    def _from_db_row(self, model_cls: Type[T], row: sqlite3.Row) -> T:
        """Convert database row to model instance."""
        config = MODEL_CONFIG[model_cls]
        kwargs = {}
        for field_name in config["fields"]:
            value = row[field_name]
            if field_name == "evidence_type":
                value = EvidenceType(value)
            elif field_name == "supports_hypothesis" and value is not None:
                value = bool(value)
            kwargs[field_name] = value
        return model_cls(**kwargs)

    def _validate(self, entity: T) -> None:
        """Validate entity before insert; raises ValueError/TypeError."""
        if isinstance(entity, Outcome) and entity.confidence is not None:
            c = entity.confidence
            if not isinstance(c, (int, float)) or isinstance(c, bool):
                raise TypeError("confidence must be a number, None, or omitted")
            if not math.isfinite(c):
                raise ValueError("confidence must be finite (no NaN or infinity)")
            if c < 0 or c > 1:
                raise ValueError("confidence must be in the range 0..1")

    def create(self, entity: T) -> T:
        """Insert a new entity."""
        self._validate(entity)
        model_cls = type(entity)
        config = MODEL_CONFIG[model_cls]
        fields = config["fields"]
        table = config["table"]
        
        values = [self._to_db_value(getattr(entity, f)) for f in fields]
        placeholders = ", ".join("?" for _ in fields)
        columns = ", ".join(fields)
        
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        self.conn.execute(sql, values)
        self.conn.commit()
        return entity

    def get(self, model_cls: Type[T], entity_id: str) -> Optional[T]:
        """Retrieve an entity by ID."""
        config = MODEL_CONFIG[model_cls]
        table = config["table"]
        
        sql = f"SELECT * FROM {table} WHERE id = ?"
        cursor = self.conn.execute(sql, (entity_id,))
        row = cursor.fetchone()
        
        if row is None:
            return None
        return self._from_db_row(model_cls, row)

    def list_all(self, model_cls: Type[T]) -> List[T]:
        """List all entities of a type."""
        config = MODEL_CONFIG[model_cls]
        table = config["table"]
        
        sql = f"SELECT * FROM {table} ORDER BY created_at DESC"
        cursor = self.conn.execute(sql)
        return [self._from_db_row(model_cls, row) for row in cursor.fetchall()]

    def update(self, entity: T) -> T:
        """Update an existing entity."""
        model_cls = type(entity)
        config = MODEL_CONFIG[model_cls]
        fields = config["fields"]
        table = config["table"]
        
        # Update timestamp
        entity.updated_at = datetime.utcnow().isoformat()
        
        # Build SET clause excluding id
        update_fields = [f for f in fields if f != "id"]
        set_clause = ", ".join(f"{f} = ?" for f in update_fields)
        values = [self._to_db_value(getattr(entity, f)) for f in update_fields]
        values.append(entity.id)
        
        sql = f"UPDATE {table} SET {set_clause} WHERE id = ?"
        self.conn.execute(sql, values)
        self.conn.commit()
        return entity

    def delete(self, model_cls: Type[T], entity_id: str) -> bool:
        """Delete an entity by ID. Returns True if deleted."""
        config = MODEL_CONFIG[model_cls]
        table = config["table"]
        
        sql = f"DELETE FROM {table} WHERE id = ?"
        cursor = self.conn.execute(sql, (entity_id,))
        self.conn.commit()
        return cursor.rowcount > 0
