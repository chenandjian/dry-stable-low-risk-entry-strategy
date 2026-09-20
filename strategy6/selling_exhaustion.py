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
    'recent_down_days_min': 2,
    'previous_down_days_min': 3,
    'phase_lookback': 20,
    'phase_pullback_atr_min': 1.0,
    'phase_max_floor_distance_atr': 1.0,
    'phase_max_rise_3_atr': .5,
    'phase_max_rise_1_atr': .5,
    'close_recent_mean_min': .55,
    'close_improvement_min': .10,
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
    if type(cfg['phase_lookback']) is not int or not 5 <= cfg['phase_lookback'] <= 60:
        raise ValueError('phase lookback')
    for key in ('phase_pullback_atr_min', 'phase_max_floor_distance_atr', 'phase_max_rise_3_atr', 'phase_max_rise_1_atr'):
        if isinstance(cfg[key], bool) or not isfinite(cfg[key]) or cfg[key] <= 0:
            raise ValueError(key)
    if len(cfg['score_tables']) != 4:
        raise ValueError('score tables')
    for key in ('close_recent_mean_min', 'close_improvement_min'):
        if isinstance(cfg[key], bool) or not isfinite(cfg[key]) or not 0 <= cfg[key] <= 1:
            raise ValueError(key)
    for i, (table, cap) in enumerate(zip(cfg['score_tables'], (30, 30, 25, 15))):
        if not table or any(len(p) != 2 or any(isinstance(v, bool) or not isfinite(v) for v in p)
                            or not 0 <= p[1] <= cap for p in table):
            raise ValueError('score table')
        if any((a[0] <= b[0] if i in (1, 3) else a[0] >= b[0]) or a[1] < b[1]
               for a, b in zip(table, table[1:])):
            raise ValueError('score order')
    return cfg


def evaluate_selling_exhaustion(rows, config=None):
    result = dict(modelVersion='DOWNSIDE_SELLING_EXHAUSTION_V3', status='DATA_INSUFFICIENT',
                  matched=False, score=None, grade=None, confirmationDays=0, metrics={},
                  phase='UNKNOWN', phaseMetrics={},
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
    phases = _phases(bars, atrs, cfg)
    latest = _with_phase(_at(bars, atrs, len(bars)-1, cfg), phases[-1])
    result.update(latest)
    if result['matched']:
        for i in range(len(bars)-1, 58, -1):
            if not _with_phase(_at(bars, atrs, i, cfg), phases[i])['matched']:
                break
            result['confirmationDays'] += 1
    result['warnings'] = ['日线代理指标，不代表主动卖单统计或买入信号；不判断真实跌停及绝对流动性']
    return result


def _phases(bars, atrs, cfg):
    """Causal episodes; resume only on a new pullback or an original-floor retest."""
    snapshots = []
    phase, floor, floor_date, anchor_atr = 'NO_PULLBACK', None, '', None
    peak_date, start_date, released_at = '', '', 0
    for i, bar in enumerate(bars):
        if i < 15 or not atrs[i-1] or atrs[i-1] <= 0:
            snapshots.append(dict(phase='NO_PULLBACK', phaseMetrics={}, phaseReasons=['尚无有效回调背景']))
            continue
        if phase != 'PULLBACK':
            left = max(0, i-cfg['phase_lookback']+1, released_at)
            peak = max(range(left, i+1), key=lambda j: (bars[j]['close'], j))
            downs = sum(bars[j]['close'] < bars[j-1]['close'] for j in range(peak+1, i+1))
            if downs >= 2 and bars[peak]['close']-bar['close'] >= cfg['phase_pullback_atr_min']*atrs[i-1]:
                phase = 'PULLBACK'
                anchor_atr = atrs[i-1]
                bottom = min(range(peak, i+1), key=lambda j: bars[j]['low'])
                floor, floor_date = bars[bottom]['low'], bars[bottom]['date']
                peak_date, start_date = bars[peak]['date'], bar['date']
            elif phase == 'REBOUNDED':
                scale = min(anchor_atr, atrs[i-1])
                # A retest of the original bottom is not an elevated new floor.
                if (bar['close']-floor <= cfg['phase_max_floor_distance_atr']*scale
                        and bar['close']-bars[i-3]['close'] <= cfg['phase_max_rise_3_atr']*scale
                        and bar['close']-bars[i-1]['close'] <= cfg['phase_max_rise_1_atr']*scale):
                    # Two post-release supportive closes plus all raw gates allow
                    # re-observation without requiring two new down days.
                    supported = (i >= 59 and i-released_at >= 2
                                 and all(r['high'] > r['low'] and
                                         (r['close']-r['low'])/(r['high']-r['low']) >= cfg['normal'][3]
                                         for r in bars[i-1:i+1]))
                    if downs >= 2 or (supported and _at(bars, atrs, i, cfg)['matched']):
                        phase = 'PULLBACK'
                        bottom = min(range(released_at, i+1), key=lambda j: bars[j]['low'])
                        if bars[bottom]['low'] < floor:
                            floor, floor_date = bars[bottom]['low'], bars[bottom]['date']
        if phase == 'PULLBACK' and bar['low'] < floor:
            floor, floor_date = bar['low'], bar['date']
        # Never widen the bottom zone with an old large ATR or today's surge.
        position_atr = min(anchor_atr, atrs[i-1]) if anchor_atr else None
        distance = (bar['close']-floor)/position_atr if position_atr else None
        rise = (bar['close']-bars[i-3]['close'])/position_atr if position_atr else None
        rise_one = (bar['close']-bars[i-1]['close'])/position_atr if position_atr else None
        reasons = []
        if phase == 'PULLBACK':
            if distance > cfg['phase_max_floor_distance_atr']:
                reasons.append(f'离本轮底部{distance:.3f} ATR，超过{cfg["phase_max_floor_distance_atr"]} ATR')
            if rise > cfg['phase_max_rise_3_atr']:
                reasons.append(f'最近3日净上涨{rise:.3f} ATR，超过{cfg["phase_max_rise_3_atr"]} ATR')
            if rise_one > cfg['phase_max_rise_1_atr']:
                reasons.append(f'当日净上涨{rise_one:.3f} ATR，超过{cfg["phase_max_rise_1_atr"]} ATR')
            if reasons:
                phase, released_at = 'REBOUNDED', i
        if phase == 'REBOUNDED' and not reasons:
            reasons = ['本轮已反弹，尚未形成新回调或回踩原底部的证据']
        if phase == 'NO_PULLBACK':
            reasons = [f'尚无有效回调背景：需从近期收盘高点回落至少{cfg["phase_pullback_atr_min"]} ATR且至少2个收跌日']
        snapshots.append(dict(phase=phase, phaseReasons=reasons,
                              phaseMetrics=dict(floorPrice=floor, floorDate=floor_date,
                                                anchorAtr=anchor_atr, positionAtr=position_atr, peakDate=peak_date,
                                                pullbackStartDate=start_date,
                                                floorDistanceAtr=distance, rise3Atr=rise, rise1Atr=rise_one)))
    return snapshots


def _with_phase(result, snapshot):
    result.update(phase=snapshot['phase'], phaseMetrics=snapshot['phaseMetrics'])
    if result['status'] == 'DATA_INVALID':
        return result
    if snapshot['phase'] != 'PULLBACK':
        result['matched'] = False
        if snapshot['phase'] == 'REBOUNDED':
            result['status'] = 'REBOUNDED'
        elif result['status'] != 'SAMPLE_INSUFFICIENT':
            result['status'] = 'NO_PULLBACK'
        result['failReasons'] += snapshot['phaseReasons']
    return result


def _at(bars, atrs, end, cfg):
    base = dict(matched=False, score=None, grade=None, metrics={}, reasons=[], failReasons=[])
    recent = bars[end-4:end+1]
    atr = atrs[end]
    if not atr or atr <= 0 or any(r['high'] == r['low'] for r in recent):
        return {**base, 'status': 'DATA_INVALID', 'failReasons': ['ATR无效或最近5日存在一字K线，无法判定承接']}
    recent_down = [i for i in range(end-4, end+1) if bars[i]['close'] < bars[i-1]['close']]
    previous_down = [i for i in range(end-19, end-4) if bars[i]['close'] < bars[i-1]['close']]
    if not recent_down or len(previous_down) < cfg['previous_down_days_min']:
        return {**base, 'status': 'SAMPLE_INSUFFICIENT', 'failReasons': ['下跌日样本不足'],
                'metrics': dict(recentDownDays5=len(recent_down), previousDownDays=len(previous_down))}
    volume = mean(bars[i]['volume'] for i in recent_down) / mean(bars[i]['volume'] for i in previous_down)
    move = mean(1-bars[i]['close']/bars[i-1]['close'] for i in recent_down) / mean(1-bars[i]['close']/bars[i-1]['close'] for i in previous_down)
    low = (min(r['low'] for r in bars[end-2:end+1]) - min(r['low'] for r in bars[end-7:end-2])) / atr
    close = mean((r['close']-r['low'])/(r['high']-r['low']) for r in recent)
    positions = [(r['close']-r['low'])/(r['high']-r['low']) for r in recent]
    close_recent, close_previous = mean(positions[-3:]), mean(positions[:2])
    improving = (close_recent >= max(cfg['normal'][3], cfg['close_recent_mean_min'])
                 and close_recent-close_previous >= cfg['close_improvement_min']
                 and all(p >= cfg['normal'][3] for p in positions[-2:]))
    close_path = ('FIVE_DAY_MEAN' if close >= cfg['normal'][3] else
                  'RECENT_IMPROVEMENT' if improving else 'NONE')
    depths = [max(0, min(r['low'] for r in bars[i-5:i])-bars[i]['low']) / atrs[i]
              if atrs[i] and atrs[i] > 0 else 0 for i in range(end-4, end+1)]
    count, depth = sum(d > 0 for d in depths), max(depths)
    current_count, current_depth = sum(d > 0 for d in depths[-3:]), max(depths[-3:])
    values = [volume, low, move, close]
    def passes(limits):
        return [volume <= limits[0], low >= limits[1], move <= limits[2], close >= limits[3]]
    checks = passes(cfg['normal']) + [current_count <= cfg['new_low_count_max'], current_depth <= cfg['new_low_depth_atr_max'], len(recent_down) >= cfg['recent_down_days_min']]
    checks[3] = close_path != 'NONE'
    matched = all(checks)
    status = 'NOT_CONFIRMED' if len(recent_down) >= cfg['recent_down_days_min'] else 'SAMPLE_INSUFFICIENT'
    if matched:
        status = 'NORMAL'
        if all(passes(cfg['strong'])) and current_count <= 1:
            status = 'STRONG'
        if all(passes(cfg['ultra'])) and current_count == 0:
            status = 'ULTRA'
    components = [next((points for limit, points in table if (value >= limit if i in (1, 3) else value <= limit)), 0)
                  for i, (value, table) in enumerate(zip(values, cfg['score_tables']))]
    score = sum(components)
    labels = [f'下跌量比 {volume:.3f}（要求≤{cfg["normal"][0]}）',
              f'低点变化 {low:.3f} ATR（要求≥{cfg["normal"][1]}）',
              f'跌幅比 {move:.3f}（要求≤{cfg["normal"][2]}）',
              f'收盘位置 {close:.3f}（要求≥{cfg["normal"][3]}）',
              f'最近3日新低次数 {current_count}（要求≤{cfg["new_low_count_max"]}）',
              f'最近3日最大刺破 {current_depth:.3f} ATR（要求≤{cfg["new_low_depth_atr_max"]}）',
              f'最近5日下跌样本 {len(recent_down)}（要求≥{cfg["recent_down_days_min"]}）']
    if close_path == 'RECENT_IMPROVEMENT':
        labels[3] = f'近期承接改善：近3日收盘位置{close_recent:.3f}，较前2日提高{close_recent-close_previous:.3f}，最近2日均达标（仅普通确认，不加分）'
    return dict(status=status, matched=matched, score=score,
                grade=next((g for floor, g in [(90, 'S'), (80, 'A+'), (70, 'A'), (60, 'B'), (50, 'C')] if score >= floor), 'NONE'),
                componentScores=components,
                reasons=[s for s, ok in zip(labels, checks) if ok],
                failReasons=[s for s, ok in zip(labels, checks) if not ok],
                metrics=dict(downVolumeDecay=volume, lowShiftAtr=low, downMoveDecay=move,
                             closePositionMean5=close, newLowCount5=count, newLowDepthAtr=depth,
                             closePositionMean3=close_recent, closePositionPrevious2=close_previous,
                             closePositionImprovement=close_recent-close_previous, closeSupportPath=close_path,
                             newLowCount3=current_count, newLowDepthAtr3=current_depth,
                             recentDownDays5=len(recent_down), previousDownDays=len(previous_down),
                             downVolumeRatio5=sum(bars[i]['volume'] for i in recent_down)/sum(r['volume'] for r in recent),
                             downVolumeMedianDecay=median(bars[i]['volume'] for i in recent_down)/median(bars[i]['volume'] for i in previous_down),
                             atr14=atr))
