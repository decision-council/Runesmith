"""Reproduce the operating characteristics of the attention drift chart (runesmith/kaizen/attention.py).

Bernoulli CUSUM against "yield fell to ratio x p0", with p0 = the Wilson lower bound of the first n0 outcomes.
Prints the false-alarm share within 200 stable opportunities at several yields, and the detection rate and
median delay for downward shifts. Run: python docs/simulations/drift_cusum.py (about a minute).

Result recorded on 2026-09-24 for the shipped defaults (n0=30, z=1.5, h=5, ratio=0.5):
  false alarms within 200 stable: 1.7% (p=0.2), 1.8% (0.35), 2.7% (0.6), 3.7% (0.85)
  0.6 -> 0.15: detected 100%, median delay 22;  0.6 -> 0.3: 86%, median 48;  0.35 -> 0.1: 90%, median 68
"""
import math
import random


def wilson_low(successes, n, z):
    p = successes / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def first_alarm(p_true, *, n0=30, z=1.5, h=5.0, ratio=0.5, steps=200, p_after=None, seed=0):
    rng = random.Random(seed)
    baseline = [rng.random() < p_true for _ in range(n0)]
    p0 = min(max(wilson_low(sum(baseline), n0, z), 0.02), 0.98)
    p1, s = p0 * ratio, 0.0
    for t in range(steps):
        success = rng.random() < (p_after if p_after is not None else p_true)
        s = max(0.0, s + (math.log(p1 / p0) if success else math.log((1 - p1) / (1 - p0))))
        if s >= h:
            return t
    return None


if __name__ == "__main__":
    runs = 1500
    for p in (0.2, 0.35, 0.6, 0.85):
        alarms = sum(first_alarm(p, seed=s) is not None for s in range(runs)) / runs
        print(f"stable p={p}: false alarm within 200 = {alarms:.1%}")
    for p_true, p_after in ((0.6, 0.15), (0.6, 0.3), (0.35, 0.1)):
        delays = sorted(d for d in (first_alarm(p_true, p_after=p_after, steps=300, seed=s) for s in range(600))
                        if d is not None)
        print(f"{p_true} -> {p_after}: detected {len(delays) / 6:.0f}%, median delay {delays[len(delays) // 2]}")
