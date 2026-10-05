"""Runesmith Core: a model-agnostic runtime that improves objects and itself.

The package has two regions (see docs/ARCHITECTURE.md):

* a small, fixed **kernel** — canonical identity, the append-only ledger,
  instrument routing and budgets, the public signal of objects, confined organ
  execution, and frozen generations; and
* mutable **organs** — policies such as the repair organ, which the Kaizen
  engine may rewrite. An organ runs in a confined child process and reaches the
  world only through the typed cockpit interface the kernel grants it.

Models are replaceable instruments. Competence that survives is held in
evidence-bearing state: organs, tools, memories and calibrated self-knowledge.
"""

__version__ = "1.0.0"
