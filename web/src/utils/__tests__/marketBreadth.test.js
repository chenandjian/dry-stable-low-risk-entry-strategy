import { describe, expect, it } from 'vitest'

import {
  calcBreadthPercentile,
  calcBreadthRate,
  enrichBreadthRows,
  getBreadthLevel,
  getBreadthTrend,
  getMarketRelation,
  summarizeRecentBreadth,
} from '../marketBreadth.js'

describe('market breadth research calculations', () => {
  it('uses only rising and falling stocks in breadth rate', () => {
    expect(calcBreadthRate(1753, 3138)).toBeCloseTo(0.3584, 4)
    expect(calcBreadthRate(50, 50, 999)).toBe(0.5)
    expect(calcBreadthRate(0, 0)).toBeNull()
  })

  it.each([
    [0.75, 'EXTREME_STRONG', '极强'],
    [0.60, 'STRONG', '偏强'],
    [0.50, 'NEUTRAL', '均衡'],
    [0.35, 'WEAK', '偏弱'],
    [0.25, 'EXTREME_WEAK', '极弱'],
  ])('classifies %s breadth as %s', (rate, key, label) => {
    expect(getBreadthLevel(rate)).toMatchObject({ key, label })
  })

  it.each([
    [0.01, 0.75, 'STRONG_RESONANCE', '强势共振'],
    [0.01, 0.35, 'INDEX_FALSE_STRENGTH', '指数虚强'],
    [-0.01, 0.65, 'STOCKS_STRONGER', '个股强于指数'],
    [-0.01, 0.25, 'WEAK_RESONANCE', '弱势共振'],
    [0, 0.50, 'NEUTRAL', '中性'],
  ])('relates index %s and breadth %s as %s', (indexChange, breadthRate, key, label) => {
    expect(getMarketRelation(indexChange, breadthRate)).toMatchObject({ key, label })
  })

  it('calculates partial MA5 and compares today with five trading days ago', () => {
    const rates = [0.60, 0.55, 0.50, 0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15]
    const rows = enrichBreadthRows(rates.map((rate, index) => ({
      date: `2026-01-${String(index + 1).padStart(2, '0')}`,
      upCount: rate * 100,
      downCount: (1 - rate) * 100,
    })))

    expect(rows[0].breadthMA5).toBeCloseTo(0.60)
    expect(rows[4].breadthMA5).toBeCloseTo(0.50)
    expect(rows[9].breadthMA5).toBeCloseTo(0.25)
    expect(rows[9].breadthTrendDelta).toBeCloseTo(-0.25)
    expect(rows[9].breadthTrend).toMatchObject({ key: 'CLEAR_WEAKENING', label: '明显转弱' })
  })

  it('uses percentage-point thresholds for MA5 trend', () => {
    expect(getBreadthTrend(0.06).key).toBe('CLEAR_STRENGTHENING')
    expect(getBreadthTrend(0.03).key).toBe('MILD_STRENGTHENING')
    expect(getBreadthTrend(0.01).key).toBe('STABLE')
    expect(getBreadthTrend(-0.03).key).toBe('MILD_WEAKENING')
    expect(getBreadthTrend(-0.08).key).toBe('CLEAR_WEAKENING')
    expect(getBreadthTrend(null).key).toBe('INSUFFICIENT_DATA')
  })

  it('calculates current percentile from the selected reliable lookback', () => {
    expect(calcBreadthPercentile([0.1, 0.2, 0.3, 0.4], 0.2, 120)).toBe(0.5)
    expect(calcBreadthPercentile([], 0.2, 120)).toBeNull()
  })

  it('summarizes recent breadth and selected index without inventing missing values', () => {
    const rows = enrichBreadthRows([
      [0.50, 0.01], [0.45, -0.01], [0.40, 0.02], [0.35, 0], [0.30, -0.01],
    ].map(([rate, indexReturn], index) => ({
      date: `2026-02-${String(index + 1).padStart(2, '0')}`,
      upCount: rate * 100,
      downCount: (1 - rate) * 100,
      indexes: { sh000001: { dailyReturn: indexReturn } },
    })))

    const summary = summarizeRecentBreadth(rows, 'sh000001', 5)
    expect(summary.averageBreadthRate).toBeCloseTo(0.40)
    expect(summary.indexCumulativeReturn).toBeCloseTo(1.01 * 0.99 * 1.02 * 1 * 0.99 - 1)
    expect(summary.startBreadthRate).toBe(0.50)
    expect(summary.endBreadthRate).toBe(0.30)
  })
})
