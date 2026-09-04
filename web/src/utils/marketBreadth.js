const validNumber = value => typeof value === 'number' && Number.isFinite(value)
const DEFAULT_BROAD_INDEXES = ['sh000001', 'sz399001', 'sz399006', 'hs300']

export function calcBreadthRate(upCount, downCount) {
  const up = Number(upCount)
  const down = Number(downCount)
  if (!Number.isFinite(up) || !Number.isFinite(down) || up < 0 || down < 0 || up + down === 0) return null
  return up / (up + down)
}

export function calcCompositeIndexChange(indexes, symbols = DEFAULT_BROAD_INDEXES, minimumAvailable = 2) {
  const returns = symbols
    .map(symbol => indexes?.[symbol]?.dailyReturn)
    .filter(validNumber)
  if (returns.length < minimumAvailable) return null
  return returns.reduce((total, value) => total + value, 0) / returns.length
}

export function getBreadthLevel(rate) {
  if (!validNumber(rate)) return { key: 'INSUFFICIENT_DATA', label: '数据不足', className: 'neutral' }
  if (rate >= 0.70) return { key: 'EXTREME_STRONG', label: '极强', className: 'extreme-strong' }
  if (rate >= 0.55) return { key: 'STRONG', label: '偏强', className: 'strong' }
  if (rate >= 0.45) return { key: 'NEUTRAL', label: '均衡', className: 'neutral' }
  if (rate >= 0.30) return { key: 'WEAK', label: '偏弱', className: 'weak' }
  return { key: 'EXTREME_WEAK', label: '极弱', className: 'extreme-weak' }
}

export function getBreadthTrend(delta) {
  if (!validNumber(delta)) return { key: 'INSUFFICIENT_DATA', label: '数据不足', direction: 'flat' }
  if (delta >= 0.05) return { key: 'CLEAR_STRENGTHENING', label: '明显转强', direction: 'up' }
  if (delta >= 0.02) return { key: 'MILD_STRENGTHENING', label: '温和转强', direction: 'up' }
  if (delta <= -0.05) return { key: 'CLEAR_WEAKENING', label: '明显转弱', direction: 'down' }
  if (delta <= -0.02) return { key: 'MILD_WEAKENING', label: '温和转弱', direction: 'down' }
  return { key: 'STABLE', label: '横盘 / 稳定', direction: 'flat' }
}

export function getIndexState(indexChange) {
  if (!validNumber(indexChange)) return { key: 'UNKNOWN', label: '数据不足' }
  if (indexChange >= 0.005) return { key: 'STRONG', label: '偏强' }
  if (indexChange <= -0.005) return { key: 'WEAK', label: '偏弱' }
  return { key: 'NEUTRAL', label: '中性' }
}

export function getMarketRelation(indexChange, breadthRate) {
  const indexState = getIndexState(indexChange)
  const stockState = getBreadthLevel(breadthRate)
  const base = { indexState, stockState }
  if (!validNumber(indexChange) || !validNumber(breadthRate)) {
    return { ...base, key: 'INSUFFICIENT_DATA', label: '数据不足', description: '指数或市场宽度数据不足' }
  }
  if (indexChange >= 0.005 && breadthRate >= 0.60) {
    return { ...base, key: 'STRONG_RESONANCE', label: '强势共振', description: '指数和多数股票同时上涨' }
  }
  if (indexChange >= 0.003 && breadthRate < 0.45) {
    return { ...base, key: 'INDEX_FALSE_STRENGTH', label: '指数虚强', description: '指数上涨，但多数股票偏弱' }
  }
  if (indexChange <= -0.003 && breadthRate > 0.55) {
    return { ...base, key: 'STOCKS_STRONGER', label: '个股强于指数', description: '指数下跌，但多数股票表现较强' }
  }
  if (indexChange <= -0.005 && breadthRate <= 0.40) {
    return { ...base, key: 'WEAK_RESONANCE', label: '弱势共振', description: '指数与多数股票同步走弱' }
  }
  return { ...base, key: 'NEUTRAL', label: '中性', description: '指数与市场宽度未出现明显共振或背离' }
}

function average(values) {
  const available = values.filter(validNumber)
  if (!available.length) return null
  return available.reduce((total, value) => total + value, 0) / available.length
}

export function enrichBreadthRows(rows) {
  const enriched = rows.map(row => ({
    ...row,
    breadthRate: calcBreadthRate(row.upCount, row.downCount),
  }))
  return enriched.map((row, index) => {
    const breadthMA5 = average(enriched.slice(Math.max(0, index - 4), index + 1).map(item => item.breadthRate))
    const previousMA5 = index >= 5
      ? average(enriched.slice(Math.max(0, index - 9), index - 4).map(item => item.breadthRate))
      : null
    const breadthTrendDelta = validNumber(breadthMA5) && validNumber(previousMA5)
      ? breadthMA5 - previousMA5
      : null
    return {
      ...row,
      breadthMA5,
      breadthTrendDelta,
      breadthLevel: getBreadthLevel(row.breadthRate),
      breadthTrend: getBreadthTrend(breadthTrendDelta),
    }
  })
}

export function calcBreadthPercentile(values, currentValue, lookback = 120) {
  if (!validNumber(currentValue)) return null
  const available = values.filter(validNumber).slice(-Math.max(1, lookback))
  if (!available.length) return null
  return available.filter(value => value <= currentValue).length / available.length
}

export function countBreadthLevels(rows, lookback = 20) {
  const counts = { EXTREME_STRONG: 0, STRONG: 0, NEUTRAL: 0, WEAK: 0, EXTREME_WEAK: 0 }
  rows.slice(-Math.max(1, lookback)).forEach(row => {
    const key = row.breadthLevel?.key || getBreadthLevel(row.breadthRate).key
    if (key in counts) counts[key] += 1
  })
  return counts
}

export function summarizeRecentBreadth(rows, indexSymbol, count = 5) {
  const recent = rows.slice(-Math.max(1, count))
  if (!recent.length) return null
  const indexReturns = recent
    .map(row => row.indexes?.[indexSymbol]?.dailyReturn)
    .filter(validNumber)
  const indexCumulativeReturn = indexReturns.length
    ? indexReturns.reduce((result, value) => result * (1 + value), 1) - 1
    : null
  const first = recent[0]
  const last = recent[recent.length - 1]
  return {
    tradingDays: recent.length,
    indexCumulativeReturn,
    averageBreadthRate: average(recent.map(row => row.breadthRate)),
    startBreadthRate: first.breadthRate,
    endBreadthRate: last.breadthRate,
    startBreadthMA5: first.breadthMA5,
    endBreadthMA5: last.breadthMA5,
    breadthTrend: last.breadthTrend,
  }
}

export function buildMarketConclusion(row, relation) {
  if (!row) return '市场宽度数据不足。'
  if (relation?.key === 'INDEX_FALSE_STRENGTH') return '指数表现偏强，但多数个股偏弱，赚钱效应不足。'
  if (relation?.key === 'STOCKS_STRONGER') return '指数承压，但多数个股相对更强，市场宽度占优。'
  if (relation?.key === 'STRONG_RESONANCE') return '指数与多数个股同步走强，市场赚钱效应较好。'
  if (relation?.key === 'WEAK_RESONANCE') return '指数与多数个股同步走弱，当前环境偏谨慎。'
  if (row.breadthTrend?.direction === 'down') return '市场宽度持续走弱，个股赚钱效应下降。'
  if (row.breadthTrend?.direction === 'up') return '市场宽度正在改善，个股赚钱效应回升。'
  return `市场宽度处于${row.breadthLevel?.label || '未知'}状态，近期变化相对稳定。`
}
