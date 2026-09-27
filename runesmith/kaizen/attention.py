"""Attention allocation between object work and self-improvement.

Runesmith spends most opportunities on objects and keeps a standing share for
improving itself (Kaizen: there is always a next level). When the same failure
signature keeps recurring, it is *struggling*: the subject share rises so the
blockage gets investigated, and falls back once the blockage is gone. Credit is
capped at one due slot, so missed self-work never becomes a burst that starves
object work. Shares follow the commissioning defaults of the Astra
subject-cognition architecture (§5): 15% healthy, 25% suspected, 40% blocked,
20% recovering. They are starting points to be measured, not optimal values.

Struggle also shows as *drift*: the yield slides although no single failure
recurs, for example after a model change or a shift in the objects. A Bernoulli
CUSUM (statistical process control for pass/fail outcomes) watches for it:

- the first ``drift_baseline_n`` uncensored outcomes set Runesmith's own baseline yield p0.
  It is the Wilson lower bound at ``drift_z`` standard errors, so a baseline that happened to
  come out high does not make a normal process look like a drop;
- each later outcome adds the log-likelihood ratio of "yield fell to ``drift_ratio`` × p0"
  against "yield is still p0";
- when the sum reaches ``drift_h``, attention moves to blocked.

The baseline is re-estimated after a subject change is activated, because the process has changed.

The defaults are 30 baseline outcomes, z = 1.5, h = 5 and a ratio of 0.5. Their simulated operating
characteristics (2026-09-24; 1,500 runs per cell) are:
- at most 3.7% false alarms within 200 stable opportunities, at yields from 0.2 to 0.85;
- a drop from 0.6 to 0.15 is always detected, with a median delay of 22 opportunities;
- a halving from 0.6 to 0.3 is detected in 86% of runs within 300 opportunities, median 48.

It is a slow backstop. Acute blockages are caught sooner by the recurring-signature rule.
"""

from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from runesmith import atomic

HEALTHY, SUSPECTED, BLOCKED, RECOVERING, CAPACITY = (
    "HEALTHY", "SUSPECTED_BLOCKAGE", "SUBJECT_BLOCKED", "RECOVERING", "CAPACITY_CONSTRAINED")
SHARE_BP = {HEALTHY: 1500, SUSPECTED: 2500, BLOCKED: 4000, RECOVERING: 2000, CAPACITY: 1500}


@dataclass
class Attention:
    window: int = 10
    suspect_after: int = 2
    block_after: int = 3
    recover_after: int = 3
    censor_after: int = 3
    mode: str = HEALTHY
    credit_bp: int = 0
    recent: deque = field(default_factory=lambda: deque(maxlen=10))
    successes_in_row: int = 0
    censored_in_row: int = 0
    blocking_signature: str | None = None
    transitions: list = field(default_factory=list)
    drift_baseline_n: int = 30
    drift_ratio: float = 0.5
    drift_h: float = 5.0
    drift_z: float = 1.5
    baseline: list = field(default_factory=list)
    p0: float | None = None
    cusum: float = 0.0

    def __post_init__(self) -> None:
        self.recent = deque(self.recent, maxlen=self.window)

    def _drift(self, success: bool) -> str | None:
        """Update the yield chart with one uncensored outcome; returns a reason when drift is signalled."""
        if self.p0 is None:
            self.baseline.append(int(success))
            if len(self.baseline) >= self.drift_baseline_n:
                n, z = len(self.baseline), self.drift_z
                p = sum(self.baseline) / n
                low = (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
                self.p0 = min(max(low, 0.02), 0.98)       # conservative, and never degenerate
            return None
        p0, p1 = self.p0, self.p0 * self.drift_ratio
        llr = math.log(p1 / p0) if success else math.log((1 - p1) / (1 - p0))
        self.cusum = max(0.0, self.cusum + llr)
        if self.cusum >= self.drift_h:
            self.cusum = 0.0
            return f"yield drift: CUSUM reached {self.drift_h} against baseline yield {self.p0:.2f}"
        return None

    def _move(self, mode: str, reason: str) -> None:
        if mode != self.mode:
            self.transitions.append({"from": self.mode, "to": mode, "reason": reason})
            self.mode = mode

    def observe(self, signature: str, *, success: bool, censored: bool = False) -> str:
        """Feed one terminal opportunity; returns the new mode."""
        if censored:
            self.censored_in_row += 1
            if self.censored_in_row >= self.censor_after:
                self._move(CAPACITY, "repeated transport censoring")
            return self.mode
        self.censored_in_row = 0
        if self.mode == CAPACITY:
            self._move(HEALTHY, "transport recovered")
        drift = self._drift(success)
        if drift and self.mode in (HEALTHY, SUSPECTED, RECOVERING):
            self.blocking_signature = "yield_drift"
            self._move(BLOCKED, drift)
        if success:
            self.successes_in_row += 1
            if self.mode == RECOVERING and self.successes_in_row >= self.recover_after:
                self._move(HEALTHY, "blockage absent for consecutive opportunities")
                self.blocking_signature = None
            self.recent.append(None)
            return self.mode
        self.successes_in_row = 0
        self.recent.append(signature)
        repeats = sum(1 for s in self.recent if s == signature)
        if repeats >= self.block_after and self.mode in (HEALTHY, SUSPECTED, RECOVERING):
            self.blocking_signature = signature
            self._move(BLOCKED, f"signature {signature!r} recurred {repeats}x in last {len(self.recent)}")
        elif repeats >= self.suspect_after and self.mode == HEALTHY:
            self._move(SUSPECTED, f"signature {signature!r} recurred {repeats}x")
        return self.mode

    def subject_repaired(self) -> None:
        """A qualified self-change addressed the blockage; watch whether it stays gone."""
        if self.mode in (BLOCKED, SUSPECTED):
            self._move(RECOVERING, "subject change activated")
            self.successes_in_row = 0
        self.baseline, self.p0, self.cusum = [], None, 0.0      # a new process: re-estimate the baseline yield

    def next_lane(self, subject_available: bool = True) -> str:
        """``object`` or ``subject`` for the next opportunity (credit allocator).

        The remainder carries over when a subject slot is taken, so a constant
        share is met exactly; credit is capped at one due slot only while
        subject work is unavailable, so no backlog can later starve objects.
        """
        self.credit_bp += SHARE_BP[self.mode]
        if self.credit_bp >= 10_000 and subject_available:
            self.credit_bp -= 10_000
            return "subject"
        self.credit_bp = min(self.credit_bp, 10_000)
        return "object"

    # -- persistence: struggle and drift are tracked across runs and steward rounds --------
    def save(self, path: Path) -> None:
        state = {k: (list(v) if isinstance(v, deque) else v) for k, v in asdict(self).items()}
        state["recent"] = list(self.recent)
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
        atomic.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "Attention | None":
        if not Path(path).exists():
            return None
        try:
            state = json.loads(Path(path).read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in state.items() if k in known})
        except (ValueError, TypeError, OSError):
            return None                                   # unreadable state: start fresh rather than stop working

    def snapshot(self) -> dict:
        return {"mode": self.mode, "credit_bp": self.credit_bp, "blocking_signature": self.blocking_signature,
                "recent": list(self.recent), "transitions": list(self.transitions),
                "drift": {"baseline_yield": self.p0, "baseline_outcomes": len(self.baseline),
                          "cusum": round(self.cusum, 3), "threshold": self.drift_h}}
