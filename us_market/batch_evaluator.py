"""Local-only batch diagnostics with the same engine profile as US research."""
import logging
from datetime import datetime, timezone

from strategy6.batch_evaluator import batch_result, build_batch_summary
from strategy6.engine import StrongVcpTailEngine

from .calendar import evaluation_context
from .history import read_local_history
from .service import ESTIMATION_METHOD, _symbols, research_rows

logger = logging.getLogger(__name__)


def evaluate_us_batch(path, codes, *, as_of=None, now=None):
    codes = _symbols(codes)
    if len(codes) > 200:
        raise ValueError('单次最多评估200只美股')
    if as_of is not None and not isinstance(as_of, str):
        raise ValueError('评估日期必须为 YYYY-MM-DD')
    context = evaluation_context(now or datetime.now(timezone.utc), as_of)
    engine = StrongVcpTailEngine(market_profile='US_RESEARCH_NO_INDEX')
    results, errors = [], []
    messages = {
        'KLINE_NOT_FOUND': '本地没有K线数据，请先到美股研究页获取',
        'MISSING_OR_STALE_HISTORY': '本地日线未覆盖评估日，或获取时间不满足收盘要求',
        'MISSING_TARGET_SESSION': '本地日线缺少指定评估日',
        'EVALUATION_FAILED': '本地数据读取或评分失败',
    }
    for code in codes:
        try:
            history = read_local_history(path, code)
            if not history:
                raise ValueError('KLINE_NOT_FOUND')
            rows = research_rows(history, context)
            meta = history['metadata']
            evaluation = engine.evaluate_at(rows, code=code, rows_normalized=True,
                                            data_source=meta.get('source', ''),
                                            kline_fetched_at=meta.get('fetched_at', ''))
            item = build_batch_summary(evaluation, rows, meta, use_volume=True)
            item.update(latestTurnoverActual=rows[-1]['turnover'],
                        latestTurnoverEstimatedUsd=rows[-1]['turnover_estimated_usd'],
                        turnoverEstimationMethod=ESTIMATION_METHOD)
            results.append(item)
        except Exception as exc:
            reason = str(exc) if isinstance(exc, ValueError) and str(exc) in messages else 'EVALUATION_FAILED'
            if reason == 'EVALUATION_FAILED':
                logger.exception('US batch evaluation failed for %s', code)
            errors.append({'code': code, 'error': reason, 'message': messages[reason]})
    return {
        **batch_result(results, errors), 'requestedCount': len(codes),
        'market': 'US', 'currency': 'USD', 'researchOnly': True,
        'formalScanAllowed': False, 'marketFilterEnabled': False,
        'targetTradeDate': context['target_trade_date'],
        'liveTargetTradeDate': context['live_target_trade_date'],
        'historicalEvaluation': context['historical_evaluation'],
    }
