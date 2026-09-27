"""Qualify reported gateway usage; never infer a bill or apply today's prices.

Failed format/provider attempts can consume tokens. When attempt history exists,
aggregate tokens must agree with it. Aggregate-only estimates are labelled as
reported metadata without that cross-check.
"""
from __future__ import annotations

import math

MAX_ATTEMPTS = 256


def nonnegative_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0 <= value <= 2**53 - 1 and math.isfinite(value))


def token_count(value):
    return nonnegative_number(value) and int(value) == value


def qualify_usage(meta):
    meta = meta if isinstance(meta, dict) else {}
    raw = meta.get('attempts', [])
    valid_list = isinstance(raw, list) and len(raw) <= MAX_ATTEMPTS
    attempts = raw if valid_list else []
    aggregate = {f: int(meta[f]) if token_count(meta.get(f)) else None
                 for f in ('tokens_in', 'tokens_out')}
    price = meta.get('est_usd') if nonnegative_number(meta.get('est_usd')) else None
    result = {'tokens_in': None, 'tokens_out': None, 'observed_tokens_in': None,
        'observed_tokens_out': None, 'attempts': len(raw) if 'attempts' in meta and isinstance(raw, list) else None,
        'token_complete_attempts': 0, 'token_basis': 'unknown', 'est_usd': None,
        'reported_est_usd': price, 'cost_status': 'tokens_incomplete'}
    if not meta:
        result['attempts'] = None
        return result
    if not valid_list:
        return result
    if attempts:
        result['token_basis'] = 'attempts'
        result['token_complete_attempts'] = sum(isinstance(a, dict) and
            all(token_count(a.get(f)) for f in aggregate) for a in attempts)
        for field in aggregate:
            values = [a[field] for a in attempts if isinstance(a, dict) and token_count(a.get(field))]
            total = sum(values)
            # Known zero requires a reported zero, not an empty/missing field.
            result['observed_' + field] = total if values and token_count(total) else None
            if len(values) == len(attempts) and token_count(total):
                result[field] = total
    else:
        result.update(aggregate)
        result['observed_tokens_in'] = aggregate['tokens_in']
        result['observed_tokens_out'] = aggregate['tokens_out']
        result['token_basis'] = 'aggregate_only'
    complete = all(result[f] is not None for f in aggregate)
    if complete and any(aggregate[f] != result[f] for f in aggregate):
        result['cost_status'] = 'aggregate_mismatch'
    elif complete and price is not None:
        result.update(est_usd=price, cost_status='reported_attempt_reconciled' if attempts else 'reported_aggregate_only')
    elif complete:
        result['cost_status'] = 'not_reported'
    if meta.get('cached') is True:
        # Cache receipts may repeat the original generation's counters. Without
        # an explicit billing contract these cannot be assigned to this request.
        result.update(tokens_in=None, tokens_out=None, est_usd=None,
                      token_basis='cached_report', cost_status='cached_unverified')
    return result
