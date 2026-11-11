"""TickFlow's mixed US equity pool, not a certified common-stock directory."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from .daily_data import _create_free_sdk
from .instruments import provider_symbol


def refresh_universe(repository, *, sdk=None):
    owned = sdk is None
    try:
        sdk = sdk or _create_free_sdk()
        raw = sdk.universes.get('US_Equity')
    finally:
        if owned and sdk is not None:
            sdk.close()
    if not isinstance(raw, dict) or raw.get('id') != 'US_Equity' or raw.get('region') != 'US':
        raise ValueError('unexpected US universe identity')
    values = raw.get('symbols')
    if not isinstance(values, list) or not values or len(values) > 50000 or any(not isinstance(s, str) for s in values):
        raise ValueError('empty or invalid universe; previous snapshot preserved')
    count = raw.get('symbol_count')
    if isinstance(count, bool) or count != len(values):
        raise ValueError('inconsistent universe count')
    unique_values = list(dict.fromkeys(values))
    symbols, rejected = [], []
    for value in unique_values:
        try:
            if not value.endswith('.US') or provider_symbol(value) != value:
                raise ValueError('not a canonical US provider symbol')
            symbols.append(value)
        except ValueError as exc:
            rejected.append({'symbol': value, 'reason': str(exc)})
    if not symbols:
        raise ValueError('universe contains no usable US symbols')
    snapshot = {'snapshot_id': uuid4().hex, 'source': 'tickflow_free', 'universe_id': 'US_Equity',
                'fetched_at': datetime.now(timezone.utc).isoformat(), 'provider_count': count,
                'usable_count': len(symbols), 'symbols': symbols, 'rejected': rejected,
                'duplicate_count': count - len(unique_values),
                'security_classification': 'PROVIDER_POOL_MIXED_UNVERIFIED',
                'warnings': ['POOL_MAY_INCLUDE_ETF_ADR_PREFERRED_WARRANTS', 'NOT_CERTIFIED_COMMON_STOCK_UNIVERSE'],
                'data_hash': hashlib.sha256(json.dumps(values).encode()).hexdigest()}
    repository.save_universe(snapshot)
    return snapshot


def universe_summary(snapshot):
    if snapshot is None:
        return None
    return {**{key: value for key, value in snapshot.items() if key not in {'symbols', 'rejected'}},
            'rejected_count': len(snapshot['rejected']), 'preview': snapshot['symbols'][:10]}
