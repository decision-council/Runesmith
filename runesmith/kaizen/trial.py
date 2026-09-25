"""Online confirmation: a frozen candidate earns activation on live, fresh opportunities.

While a trial is open, every new object opportunity is assigned to the incumbent
or the candidate by a seeded coin (HMAC of the opportunity key), so neither the
operator nor the organ can choose which work a generation gets. Strict outcomes
accrue per arm; censored opportunities are not counted.

At pre-declared looks (every ``look_every`` completed opportunities per arm) a
one-sided Fisher exact test compares the arms. The significance level is split
evenly across the maximum number of looks (Bonferroni spending), so looking
repeatedly cannot inflate the chance of activating a candidate that is no
better. The trial ends with:

* ``activate``  — candidate better at the look's level: compare-and-swap activation;
* ``reject``    — candidate worse at the look's level (mirrored test), or the
  maximum sample reached without activation: the incumbent stays active.

Every look, with its counts and p-values, is written to the trial state and the
ledger, so the activation decision can be audited and replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def fisher_one_sided(a_success: int, a_total: int, b_success: int, b_total: int) -> float:
    """P(arm A shows at least ``a_success`` successes | margins), i.e. one-sided test for A > B."""
    successes = a_success + b_success
    total = a_total + b_total
    if a_total <= 0 or b_total <= 0 or total <= 0:
        return 1.0
    denominator = math.comb(total, successes)
    upper = min(successes, a_total)
    tail = sum(math.comb(a_total, k) * math.comb(b_total, successes - k)
               for k in range(a_success, upper + 1) if 0 <= successes - k <= b_total)
    return min(1.0, tail / denominator)


@dataclass
class Trial:
    incumbent: str
    candidate: str
    seed: str
    alpha: float = 0.05
    look_every: int = 10
    max_per_arm: int = 60
    min_per_arm: int = 10
    counts: dict = field(default_factory=lambda: {"incumbent": [0, 0], "candidate": [0, 0]})  # [successes, total]
    looks: list = field(default_factory=list)
    decision: str | None = None
    opened_utc: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

    @property
    def max_looks(self) -> int:
        return max(1, math.ceil(self.max_per_arm / self.look_every))

    @property
    def level(self) -> float:
        return self.alpha / self.max_looks

    def assign(self, opportunity_key: str) -> str:
        """Seeded coin per opportunity; an arm that reached ``max_per_arm`` stops taking work."""
        if self.counts["candidate"][1] >= self.max_per_arm:
            return "incumbent"
        if self.counts["incumbent"][1] >= self.max_per_arm:
            return "candidate"
        digest = hmac.new(self.seed.encode(), opportunity_key.encode(), hashlib.sha256).digest()
        return "candidate" if digest[0] & 1 else "incumbent"

    def generation_for(self, arm: str) -> str:
        return self.candidate if arm == "candidate" else self.incumbent

    def record(self, arm: str, success: bool | None) -> str | None:
        """Count one outcome; returns a decision when a look concludes the trial."""
        if self.decision is not None or success is None:
            return self.decision
        slot = self.counts[arm]
        slot[0] += int(bool(success))
        slot[1] += 1
        return self._maybe_look()

    def _maybe_look(self) -> str | None:
        inc_s, inc_n = self.counts["incumbent"]
        cand_s, cand_n = self.counts["candidate"]
        smaller = min(inc_n, cand_n)
        due = smaller >= self.min_per_arm and smaller // self.look_every > len(self.looks)
        exhausted = inc_n >= self.max_per_arm and cand_n >= self.max_per_arm
        if not due and not exhausted:
            return None
        better = fisher_one_sided(cand_s, cand_n, inc_s, inc_n)
        worse = fisher_one_sided(inc_s, inc_n, cand_s, cand_n)
        look = {"look": len(self.looks) + 1, "incumbent": [inc_s, inc_n], "candidate": [cand_s, cand_n],
                "p_candidate_better": round(better, 6), "p_candidate_worse": round(worse, 6), "level": self.level}
        self.looks.append(look)
        if better <= self.level:
            self.decision = "activate"
        elif worse <= self.level:
            self.decision = "reject"
        elif exhausted or len(self.looks) >= self.max_looks:
            self.decision = "reject"          # never activate by default: no evidence, no promotion
        look["decision"] = self.decision
        return self.decision

    # -- persistence --------------------------------------------------------
    def save(self, path: Path) -> None:
        tmp = Path(str(path) + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=1) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: Path) -> "Trial | None":
        if not Path(path).exists():
            return None
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))

    def summary(self) -> dict[str, Any]:
        return {"incumbent": self.incumbent, "candidate": self.candidate, "counts": self.counts,
                "looks": len(self.looks), "decision": self.decision, "level_per_look": self.level}
