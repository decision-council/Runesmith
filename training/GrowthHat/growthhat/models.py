"""Data models for GrowthHat entities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class EvidenceType(Enum):
    """Distinguishes how evidence was obtained."""
    MEASURED = "measured"      # Actual data from tests/analytics
    PROPOSED = "proposed"      # Planned experiment not yet run
    ASSUMED = "assumed"        # Working assumption without hard data


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


@dataclass
class Source:
    """A research source (interview, survey, article, analytics, etc.)."""
    id: str = field(default_factory=_new_id)
    name: str = ""
    source_type: str = ""  # e.g. interview, survey, article, analytics
    url: Optional[str] = None
    notes: str = ""
    evidence_type: EvidenceType = EvidenceType.ASSUMED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Audience:
    """A target audience segment."""
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    needs: str = ""  # What they need
    objections: str = ""  # Common objections
    discovery_channels: str = ""  # Where they find products
    evidence_type: EvidenceType = EvidenceType.ASSUMED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Offer:
    """A product offer or value proposition."""
    id: str = field(default_factory=_new_id)
    name: str = ""
    description: str = ""
    value_proposition: str = ""
    audience_id: Optional[str] = None  # FK to Audience
    evidence_type: EvidenceType = EvidenceType.ASSUMED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Hypothesis:
    """A testable hypothesis about audience/offer fit."""
    id: str = field(default_factory=_new_id)
    statement: str = ""  # The hypothesis statement
    audience_id: Optional[str] = None
    offer_id: Optional[str] = None
    source_id: Optional[str] = None  # Source that inspired it
    rationale: str = ""
    evidence_type: EvidenceType = EvidenceType.PROPOSED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Test:
    """A planned or executed test of a hypothesis."""
    id: str = field(default_factory=_new_id)
    hypothesis_id: str = ""
    name: str = ""
    method: str = ""  # How the test is conducted
    success_criteria: str = ""
    status: str = "planned"  # planned, running, completed, abandoned
    evidence_type: EvidenceType = EvidenceType.PROPOSED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Outcome:
    """The result of a test."""
    id: str = field(default_factory=_new_id)
    test_id: str = ""
    result: str = ""  # What happened
    metrics: str = ""  # Quantitative results if any
    interpretation: str = ""
    supports_hypothesis: Optional[bool] = None
    confidence: Optional[float] = None  # 0..1, None = unknown
    evidence_type: EvidenceType = EvidenceType.MEASURED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


@dataclass
class Recommendation:
    """An actionable recommendation with traceability."""
    id: str = field(default_factory=_new_id)
    title: str = ""
    description: str = ""
    action: str = ""  # What to do
    reasoning: str = ""  # Why
    uncertainty_level: str = "medium"  # low, medium, high
    source_ids: str = ""  # Comma-separated source IDs
    hypothesis_id: Optional[str] = None
    outcome_id: Optional[str] = None
    evidence_type: EvidenceType = EvidenceType.ASSUMED
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
