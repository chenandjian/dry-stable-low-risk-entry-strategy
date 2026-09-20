"""Independent daily selling-exhaustion diagnosis, never a strategy gate."""
from math import isfinite
from statistics import mean, median


DEFAULTS = {
    # volume decay, low shift in ATR, move decay, close position
    'normal': [.80, -.30, .80, .45],
    'strong': [.70, -.15, .70, .55],
    'ultra': [.60, 0, .60, .60],
    'new_low_count_max': 1,
    'new_low_depth_atr_max': .30,
    'recent_down_days_min': 1,
    'previous_down_days_min': 3,
    'score_tables': [
        [[.50, 30], [.60, 27], [.70, 24], [.80, 20], [.90, 12], [1, 5]],
        [[.30, 30], [.10, 28], [0, 25], [-.10, 22], [-.20, 18], [-.30, 14], [-.50, 6]],
        [[.50, 25], [.60, 23], [.70, 20], [.80, 17], [.90, 10], [1, 5]],
        [[.70, 15], [.60, 13], [.55, 11], [.50, 9], [.45, 7], [.35, 3]],
    ],
}


def _config(config):
    cfg = {**DEFAULTS, **(config or {})}
    for key in ('normal', 'strong', 'ultra'):
        values = cfg[key]
        if len(values) != 4 or any(isinstance(v, bool) or not isfinite(v) for v in values):
            raise ValueError(key)
        if values[0] < 0 or values[2] < 0 or not 0 <= values[3] <= 1:
            raise ValueError(key)
    for weak, strong in [('normal', 'strong'), ('strong', 'ultra')]:
        a, b = cfg[weak], cfg[strong]
        if b[0] > a[0] or b[1] < a[1] or b[2] > a[2] or b[3] < a[3]:
            raise ValueError('strength order')
    for key, lo, hi in [('new_low_count_max', 0, 5), ('recent_down_days_min', 1, 5),
                        ('previous_down_days_min', 1, 15)]:
        if type(cfg[key]) is not int or not lo <= cfg[key] <= hi:
            raise ValueError(key)
    if isinstance(cfg['new_low_depth_atr_max'], bool) or not isfinite(cfg['new_low_depth_atr_max']) or cfg['new_low_depth_atr_max'] < 0:
        raise ValueError('depth')
    if len(cfg['score_tables']) != 4:
        raise ValueError('score tables')
    for i, (table, cap) in enumerate(zip(cfg['score_tables'], (30, 30, 25, 15))):
        if not table or any(len(p) != 2 or any(isinstance(v, bool) or not isfinite(v) for v in p)
                            or not 0 <= p[1] <= cap for p in table):
            raise ValueError('score table')
        if any((a[0] <= b[0] if i in (1, 3) else a[0] >= b[0]) or a[1] < b[1]
               for a, b in zip(table, table[1:])):
            raise ValueError('score order')
    return cfg


def evaluate_selling_exhaustion(rows, config=None):
    result = dict(modelVersion='DOWNSIDE_SELLING_EXHAUSTION_V1', status='DATA_INSUFFICIENT',
                  matched=False, score=None, grade=None, confirmationDays=0, metrics={},
                  componentScores=[], reasons=[], failReasons=[], warnings=[],
                  evaluationDate=rows[-1].get('date', '') if rows else '')
    try:
        cfg = _config(config)
    except (TypeError, ValueError, KeyError):
        return {**result, 'status': 'CONFIG_INVALID', 'failReasons': ['卖压衰竭配置无效']}
    if len(rows) < 60:
        return {**result, 'failReasons': ['至少需要60根历史日线']}
    try:
        bars = [{**r, **{k: float(r[k]) for k in ('open', 'high', 'low', 'close', 'volume')}} for r in rows]
        for r in bars:
            if any(not isfinite(r[k]) or r[k] <= 0 for k in ('open', 'high', 'low', 'close', 'volume')):
                raise ValueError('OHLC或成交量无效')
            if not r['low'] <= min(r['open'], r['close']) <= max(r['open'], r['close']) <= r['high']:
                raise ValueError('OHLC关系无效')
        if any(a['date'] >= b['date'] for a, b in zip(bars, bars[1:])):
            raise ValueError('日期必须严格递增')
    except (TypeError, ValueError, KeyError) as exc:
        return {**result, 'status': 'DATA_INVALID', 'failReasons': [str(exc)]}
    # Wilder ATR seeded by the first 14 true ranges with a known previous close.
    trs = [max(b['high'] - b['low'], abs(b['high'] - a['close']), abs(b['low'] - a['close']))
           for a, b in zip(bars, bars[1:])]
    atrs = [None] * len(bars)
    atrs[14] = mean(trs[:14])
    for i in range(15, len(bars)):
        atrs[i] = (atrs[i-1] * 13 + trs[i-1]) / 14
    latest = _at(bars, atrs, len(bars)-1, cfg)
    result.update(latest)
    if result['matched']:
        for i in range(len(bars)-1, 58, -1):
            if not _at(bars, atrs, i, cfg)['matched']:
                break
            result['confirmationDays'] += 1
    result['warnings'] = ['日线代理指标，不代表主动卖单统计或买入信号；不判断真实跌停及绝对流动性']
    return result


def _at(bars, atrs, end, cfg):
    base = dict(matched=False, score=None, grade=None, metrics={}, reasons=[], failReasons=[])
    recent = bars[end-4:end+1]
    atr = atrs[end]
    if not atr or atr <= 0 or any(r['high'] == r['low'] for r in recent):
        return {**base, 'status': 'DATA_INVALID', 'failReasons': ['ATR无效或最近5日存在一字K线，无法判定承接']}
    recent_down = [i for i in range(end-4, end+1) if bars[i]['close'] < bars[i-1]['close']]
    previous_down = [i for i in range(end-19, end-4) if bars[i]['close'] < bars[i-1]['close']]
    if len(recent_down) < cfg['recent_down_days_min'] or len(previous_down) < cfg['previous_down_days_min']:
        return {**base, 'status': 'SAMPLE_INSUFFICIENT', 'failReasons': ['下跌日样本不足'],
                'metrics': dict(recentDownDays5=len(recent_down), previousDownDays=len(previous_down))}
    volume = mean(bars[i]['volume'] for i in recent_down) / mean(bars[i]['volume'] for i in previous_down)
    move = mean(1-bars[i]['close']/bars[i-1]['close'] for i in recent_down) / mean(1-bars[i]['close']/bars[i-1]['close'] for i in previous_down)
    low = (min(r['low'] for r in bars[end-2:end+1]) - min(r['low'] for r in bars[end-7:end-2])) / atr
    close = mean((r['close']-r['low'])/(r['high']-r['low']) for r in recent)
    depths = [max(0, min(r['low'] for r in bars[i-5:i])-bars[i]['low']) / atrs[i]
              if atrs[i] and atrs[i] > 0 else 0 for i in range(end-4, end+1)]
    count, depth = sum(d > 0 for d in depths), max(depths)
    values = [volume, low, move, close]
    def passes(limits):
        return [volume <= limits[0], low >= limits[1], move <= limits[2], close >= limits[3]]
    checks = passes(cfg['normal']) + [count <= cfg['new_low_count_max'], depth <= cfg['new_low_depth_atr_max']]
    matched = all(checks)
    status = 'NOT_CONFIRMED'
    if matched:
        status = 'NORMAL'
        if all(passes(cfg['strong'])) and count <= 1:
            status = 'STRONG'
        if all(passes(cfg['ultra'])) and count == 0:
            status = 'ULTRA'
    components = [next((points for limit, points in table if (value >= limit if i in (1, 3) else value <= limit)), 0)
                  for i, (value, table) in enumerate(zip(values, cfg['score_tables']))]
    score = sum(components)
    labels = [f'下跌量比 {volume:.3f}（要求≤{cfg["normal"][0]}）',
              f'低点变化 {low:.3f} ATR（要求≥{cfg["normal"][1]}）',
              f'跌幅比 {move:.3f}（要求≤{cfg["normal"][2]}）',
              f'收盘位置 {close:.3f}（要求≥{cfg["normal"][3]}）',
              f'5日新低次数 {count}（要求≤{cfg["new_low_count_max"]}）',
              f'最大刺破 {depth:.3f} ATR（要求≤{cfg["new_low_depth_atr_max"]}）']
    return dict(status=status, matched=matched, score=score,
                grade=next((g for floor, g in [(90, 'S'), (80, 'A+'), (70, 'A'), (60, 'B'), (50, 'C')] if score >= floor), 'NONE'),
                componentScores=components,
                reasons=[s for s, ok in zip(labels, checks) if ok],
                failReasons=[s for s, ok in zip(labels, checks) if not ok],
                metrics=dict(downVolumeDecay=volume, lowShiftAtr=low, downMoveDecay=move,
                             closePositionMean5=close, newLowCount5=count, newLowDepthAtr=depth,
                             recentDownDays5=len(recent_down), previousDownDays=len(previous_down),
                             downVolumeRatio5=sum(bars[i]['volume'] for i in recent_down)/sum(r['volume'] for r in recent),
                             downVolumeMedianDecay=median(bars[i]['volume'] for i in recent_down)/median(bars[i]['volume'] for i in previous_down),
                             atr14=atr))
