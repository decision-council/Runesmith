# GrowthHat

Evidence-driven audience/offer/journey research workbench for HatOS.

## Overview

GrowthHat helps you:
- Record research sources (interviews, surveys, analytics, articles)
- Define audience segments and offers
- Track hypotheses linking audiences, offers, and sources
- Plan and record test outcomes
- Generate traceable recommendations with uncertainty levels

All evidence is tagged with its type: **measured**, **proposed**, or **assumed**.

## Installation

No external dependencies required. Uses Python standard library only.

```bash
# Ensure you're in the GrowthHat directory
cd GrowthHat
```

## Running Tests

```bash
python -m unittest discover -s tests -v
```

Or run the test file directly:

```bash
python -m unittest tests.test_repository -v
```

## Quick Start (Python)

```python
from growthhat import Repository, Source, Audience, Hypothesis, EvidenceType

# Create a repository (in-memory or file-backed)
repo = Repository(":memory:")  # or Repository("growthhat.db")

# Record a source
source = Source(
    name="Customer Interview - Jane",
    source_type="interview",
    notes="Key pain point: manual data entry",
    evidence_type=EvidenceType.MEASURED
)
repo.create(source)

# Define an audience
audience = Audience(
    name="Solo Consultants",
    needs="Time savings, automation",
    objections="Learning curve, cost",
    evidence_type=EvidenceType.ASSUMED
)
repo.create(audience)

# Create a hypothesis
hypothesis = Hypothesis(
    statement="Solo consultants will pay for automation that saves 5+ hrs/week",
    audience_id=audience.id,
    source_id=source.id,
    evidence_type=EvidenceType.PROPOSED
)
repo.create(hypothesis)

# Retrieve and update
retrieved = repo.get(Hypothesis, hypothesis.id)
print(f"Hypothesis: {retrieved.statement}")

# List all sources
for s in repo.list_all(Source):
    print(f"- {s.name} ({s.evidence_type.value})")

repo.close()
```

## Entity Types

| Entity | Purpose |
|--------|----------|
| Source | Research inputs (interviews, surveys, articles, analytics) |
| Audience | Target customer segments |
| Offer | Value propositions and products |
| Hypothesis | Testable claims linking audiences/offers/sources |
| Test | Planned or executed experiments |
| Outcome | Results of tests |
| Recommendation | Actionable advice with traceability |

## Evidence Types

- **measured**: Actual data from tests, analytics, or direct observation
- **proposed**: Planned experiments not yet executed
- **assumed**: Working assumptions without hard data

## File Structure

```
GrowthHat/
├── growthhat/
│   ├── __init__.py      # Package exports
│   ├── models.py        # Dataclasses for all entities
│   ├── schema.py        # SQLite schema definition
│   └── repository.py    # CRUD operations
├── tests/
│   ├── __init__.py
│   └── test_repository.py
└── README.md
```
