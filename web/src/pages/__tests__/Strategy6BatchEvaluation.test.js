import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  evaluateStrategy6Batch: vi.fn(),
  getLatestStrategy6TrendSqueezeScreen: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))
const { downloadTradingViewWatchlist } = vi.hoisted(() => ({
  downloadTradingViewWatchlist: vi.fn(),
}))
vi.mock('../../utils/tradingViewExport.js', () => ({ downloadTradingViewWatchlist }))

import Strategy6BatchEvaluation from '../Strategy6BatchEvaluation.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('Strategy6BatchEvaluation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    })
    api.evaluateStrategy6Batch.mockResolvedValue({
      ok: true,
      requestedCount: 3,
      evaluatedCount: 2,
      errorCount: 1,
      results: [
        {
          code: '300604', name: '长川科技', evaluationDate: '2026-08-25',
          totalScore: 82, tailScore: 19, tailQualityScore: 19, tailPass: true,
          candidateType: 'WATCH_CANDIDATE', tailVolumeRatio: 0.55,
          volumeSlope10: -0.02, closeRange5: 0.03, return5: 0.01,
          tailReasons: ['volume:non_overlap_tail_dry', 'price:no_new_low'],
          tailRejects: [], rejectReasons: [],
          scoreBreakdown: { strongStart: 18, pattern: 16, support: 17, tail: 19, objectiveRiskReward: 8, relativeStrengthRisk: 4 },
          strongTrendSqueezePass: true, trendClose: 20, trendLow250: 12,
          trendHigh250: 22, trendCloseToHighRatio: 0.9091,
          trendEma150: 18, trendEma200: 17, trendSqueezeOn: true,
          trendBbLower: 19.2, trendBbUpper: 20.8, trendKcLower: 19, trendKcUpper: 21,
          strongTrendSqueezeReasons: [],
          bodySupportScore: 8, bodySupportStatus: 'BODY_SUPPORT_STRONG',
          bodySupportType: 'FAILED_BREAK_BODY_FLOOR', bodySupportFloorPrice: 19.5,
          bodySupportZoneLow: 19.3, bodySupportZoneHigh: 19.7,
          bodySupportPivotCount: 2, bodySupportIndependentTouchCount: 2,
          bodySupportReasons: ['FAILED_BREAK_BODY_FLOOR'], bodySupportRisks: [],
          latestTurnover: 632000000, turnover5Min: 632000000, latestTurnover5Min: true,
          previous5TurnoverAverage: 1264000000, latestToPrevious5TurnoverRatio: 0.5,
          latestTurnoverBelowPrevious5Avg60: true,
          latestClose: 20, ma5: 20.25, closeBelowMa5: true, closeToMa5Pct: -0.012346,
          latestBarPatterns: [{
            code: 'VALID_BODY_LOW', name: '有效实体低点', matched: true,
            status: 'CONFIRMING', signal_type: 'FAILED_BREAK_RECLAIM',
            evaluation_date: '2026-08-25', body_bottom: 19.45, body_top: 20,
            floor_price: 19.5, zone_low: 19.3, zone_high: 19.7,
            distance_to_floor_pct: -0.0026,
            reasons: ['LATEST_LOW_BREAK_RECLAIMED_BY_BODY'],
            risks: ['REQUIRES_TWO_COMPLETED_BARS_TO_CONFIRM_PIVOT'],
          }, {
            code: 'HAMMER', name: '阳线锤子线', matched: true,
            status: 'DETECTED', signal_type: 'BULLISH_HAMMER',
            evaluation_date: '2026-08-25', body_bottom: 19.8, body_top: 20,
            metrics: {
              body_ratio: 0.2, lower_shadow_to_body: 3.5,
              upper_shadow_to_body: 0.05, range_to_previous_close: 0.05,
              range_to_atr14: 1.2,
            },
            reasons: ['LATEST_BAR_EFFECTIVE_HAMMER'], risks: [],
          }, {
            code: 'INVERTED_HAMMER', name: '阳线倒锤子线', matched: true,
            status: 'DETECTED', signal_type: 'BULLISH_INVERTED_HAMMER',
            evaluation_date: '2026-08-25', body_bottom: 19.8, body_top: 20,
            metrics: {
              body_ratio: 0.2, lower_shadow_to_body: 0.05,
              upper_shadow_to_body: 3.5, range_to_previous_close: 0.05,
              range_to_atr14: 1.2, context_return_5: -0.03, context_ma5: 20.1,
            },
            reasons: ['LATEST_BAR_EFFECTIVE_INVERTED_HAMMER'],
            risks: ['INVERTED_HAMMER_REQUIRES_CONFIRMATION'],
          }],
          klineCollectionPatterns: [{
            code: 'SLOW_ROUNDED_BASE', name: '缓跌圆底', matched: true,
            strongMatched: true, status: 'MATCHED', score: 84, grade: 'A',
            startDate: '2026-08-07', endDate: '2026-08-25', windowDays: 14,
            features: {
              pullbackDepth: 0.098, medianDownPct: 0.012,
              earlySlope: -0.007, middleSlope: -0.003, lateSlope: -0.0005,
              slopeImprovementRatio: 0.61, bottomDays: 5, bottomDwellRatio: 0.36,
              barsAfterLow: 4, afterLowRatio: 0.29,
              earlyRange: 0.09, lateRange: 0.061, rangeContractionRatio: 0.68,
              lateCluster80: 0.047, earlyOverlap: 0.41, lateOverlap: 0.66,
            },
            componentScores: {
              slowPullback: 13, deceleration: 22, bottomWidth: 16,
              afterLow: 8, volatilityContraction: 10, closeClustering: 7,
              overlapImprovement: 4, noVReversal: 4,
            },
            reasons: ['PULLBACK_PACE_GENTLE', 'DECLINE_DECELERATING'],
            warnings: [],
          }],
        },
        {
          code: '601857', name: '中国石油', evaluationDate: '2026-08-25',
          totalScore: 90, tailScore: 0, tailQualityScore: 16, tailPass: false,
          candidateType: 'REJECTED', tailVolumeRatio: 0.82,
          volumeSlope10: 0.01, closeRange5: 0.04, return5: -0.01,
          tailReasons: [], tailRejects: ['TAIL_VOLUME_NOT_DRY'],
          rejectReasons: ['TAIL_VOLUME_NOT_DRY'],
          scoreBreakdown: { strongStart: 20, pattern: 20, support: 20, tail: 0, objectiveRiskReward: 10, relativeStrengthRisk: 10 },
          strongTrendSqueezePass: false, trendClose: 9.5, trendLow250: 8,
          trendHigh250: 15, trendCloseToHighRatio: 0.6333,
          trendEma150: 10, trendEma200: 10.5, trendSqueezeOn: false,
          strongTrendSqueezeReasons: ['CLOSE_LE_10', 'EMA150_LE_EMA200'],
          latestTurnover: 780000000, turnover5Min: 632000000, latestTurnover5Min: false,
          previous5TurnoverAverage: 975000000, latestToPrevious5TurnoverRatio: 0.8,
          latestTurnoverBelowPrevious5Avg60: false,
          latestClose: 9.5, ma5: 9.4, closeBelowMa5: false, closeToMa5Pct: 0.010638,
          latestBarPatterns: [],
          klineCollectionPatterns: [{
            code: 'SLOW_ROUNDED_BASE', name: '缓跌圆底', matched: false,
            strongMatched: false, status: 'NOT_MATCHED', score: 58, grade: 'UNQUALIFIED',
            startDate: '2026-08-12', endDate: '2026-08-25', windowDays: 10,
            features: {}, componentScores: {}, reasons: [], warnings: ['PRIOR_PULLBACK_MISSING'],
          }],
        },
      ],
      errors: [{ code: '000000', name: '', error: 'KLINE_NOT_FOUND', message: '本地没有K线数据' }],
    })
    api.getLatestStrategy6TrendSqueezeScreen.mockResolvedValue({
      taskId: 's6-20260903-153000',
      total: 2,
      stocks: [
        { code: '300604', name: '长川科技' },
        { code: '000001', name: '平安银行' },
      ],
    })
  })

  it('submits deduplicated stock codes and emphasizes tail quality', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-codes"]').setValue('300604\n601857\n300604\n000000')
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    expect(api.evaluateStrategy6Batch).toHaveBeenCalledWith(['300604', '601857', '000000'])
    expect(wrapper.text()).toContain('尾部评分优先')
    expect(wrapper.text()).toContain('长川科技')
    expect(wrapper.text()).toContain('19 / 20')
    expect(wrapper.text()).toContain('计入 0 / 20')
    await wrapper.findAll('.score-row')[0].trigger('click')
    await wrapper.findAll('.score-row')[1].trigger('click')
    expect(wrapper.text()).toContain('量能明显萎缩')
    expect(wrapper.text()).toContain('尾部量能未充分萎缩')
    expect(wrapper.text()).toContain('强势趋势收缩初筛')
    expect(wrapper.text()).toContain('EMA150 18.00')
    expect(wrapper.text()).toContain('股价不高于10元')
    expect(wrapper.text()).toContain('最新交易日K线形态')
    expect(wrapper.text()).toContain('有效实体低点')
    expect(wrapper.text()).toContain('阳线锤子线')
    expect(wrapper.text()).toContain('阳线倒锤子线')
    expect(wrapper.text()).toContain('K线集合形态')
    expect(wrapper.text()).toContain('缓跌圆底 A · 84')
    expect(wrapper.text()).toContain('2026-08-07 至 2026-08-25')
    expect(wrapper.text()).toContain('回撤 9.80%')
    expect(wrapper.text()).toContain('减速 22 / 25')
    expect(wrapper.text()).toContain('此前5日趋势 -3.00%')
    expect(wrapper.text()).toContain('倒锤子线仍需后续交易日确认')
    expect(wrapper.text()).toContain('下影/实体 3.50倍')
    expect(wrapper.text()).toContain('振幅/ATR14 1.20倍')
    expect(wrapper.text()).toContain('假跌破收回')
    expect(wrapper.text()).toContain('5日成交额最低')
    expect(wrapper.text()).toContain('收盘低于MA5')
    expect(wrapper.text()).not.toContain('5日涨跌')
    expect(wrapper.text()).not.toContain('实体支撑底评分')
    expect(wrapper.text()).not.toContain('当前分类')
    expect(wrapper.text()).toContain('本地没有K线数据')
    expect(wrapper.get('[data-test="turnover-min-300604"]').classes()).toContain('requirement-hit')
    expect(wrapper.get('[data-test="below-ma5-300604"]').classes()).toContain('requirement-hit')
    expect(wrapper.get('[data-test="latest-pattern-300604"]').classes()).toContain('requirement-hit')
    expect(wrapper.get('[data-test="turnover-min-601857"]').classes()).not.toContain('requirement-hit')
    expect(wrapper.get('[data-test="below-ma5-601857"]').classes()).not.toContain('requirement-hit')
    expect(wrapper.get('[data-test="latest-pattern-601857"]').classes()).not.toContain('requirement-hit')
    expect(wrapper.get('[data-test="turnover-extreme-300604"]').classes()).toContain('requirement-hit')
    expect(wrapper.text()).toContain('今日/前5日均 50.0%')
  })

  it('rejects invalid input before sending the request', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-codes"]').setValue('300604\nABC')
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    expect(api.evaluateStrategy6Batch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('股票代码必须为6位数字')
  })

  it('recognizes a TradingView CSV stock pool and evaluates only its code column', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    const csv = [
      '商品代码,描述,价格,价格 - 货币,"价格变动 %, 1天"',
      '601857,中国石油,11.32,CNY,0.17',
      '601138,工业富联,65.24,CNY,0.75',
      '600938,中国海油,34.18,CNY,-0.61',
    ].join('\n')

    await wrapper.get('[data-test="batch-codes"]').setValue(csv)
    expect(wrapper.get('[data-test="input-format-hint"]').text()).toContain('CSV 股票池')
    expect(wrapper.get('[data-test="input-format-hint"]').text()).toContain('商品代码')
    expect(wrapper.text()).toContain('已识别 3 只')

    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    expect(api.evaluateStrategy6Batch).toHaveBeenCalledWith(['601857', '601138', '600938'])
  })

  it('copies a result stock code and expands details when the stock row is clicked', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    await wrapper.findAll('.score-row')[0].trigger('click')
    await flushUi()

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('300604')
    expect(wrapper.text()).toContain('已复制')
    expect(wrapper.find('.detail-row').exists()).toBe(true)
  })

  it('exports only the currently filtered rows in TradingView order', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()
    await wrapper.get('[data-test="filter-turnover-min"]').setValue('yes')
    await flushUi()

    await wrapper.get('[data-test="export-tradingview-filtered"]').trigger('click')

    expect(downloadTradingViewWatchlist).toHaveBeenCalledTimes(1)
    const request = downloadTradingViewWatchlist.mock.calls[0][0]
    expect(request.rows.map(row => row.code)).toEqual(['300604'])
    expect(request.filename).toMatch(/^strategy6-batch-filtered-\d{8}-\d{6}\.txt$/)
  })

  it('restores the last entered stock pool after the page is reopened', async () => {
    const first = mount(Strategy6BatchEvaluation)
    await first.get('[data-test="batch-codes"]').setValue('600162\n300604')
    await flushUi()
    first.unmount()

    const reopened = mount(Strategy6BatchEvaluation)

    expect(reopened.get('[data-test="batch-codes"]').element.value).toBe('600162\n300604')
  })

  it('remembers an intentionally cleared stock pool', () => {
    localStorage.setItem('strategy6.batchEvaluation.stockPool.v1', '')

    const wrapper = mount(Strategy6BatchEvaluation)

    expect(wrapper.get('[data-test="batch-codes"]').element.value).toBe('')
  })

  it('imports the latest independent trend squeeze screen and immediately evaluates it', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)

    await wrapper.get('[data-test="import-trend-squeeze-screen"]').trigger('click')
    await flushUi()

    expect(api.getLatestStrategy6TrendSqueezeScreen).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-test="batch-codes"]').element.value).toBe('300604\n000001')
    expect(api.evaluateStrategy6Batch).toHaveBeenCalledWith(['300604', '000001'])
    expect(wrapper.text()).toContain('来源任务 s6-20260903-153000')
    expect(wrapper.text()).toContain('已导入并完成评分 2 只')
    expect(wrapper.text()).toContain('评分结果')
  })

  it('filters each result field like an Excel auto-filter and can clear all filters', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    expect(wrapper.findAll('.score-row')).toHaveLength(2)

    await wrapper.get('[data-test="filter-collection-pattern-status"]').setValue('matched')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('300604')

    await wrapper.get('[data-test="clear-table-filters"]').trigger('click')
    await flushUi()
    await wrapper.get('[data-test="filter-collection-pattern-grade-A"]').setValue(true)
    await wrapper.get('[data-test="filter-collection-pattern-grade-UNQUALIFIED"]').setValue(true)
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(2)

    await wrapper.get('[data-test="filter-collection-pattern-grade-UNQUALIFIED"]').setValue(false)
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('300604')

    await wrapper.get('[data-test="filter-collection-pattern-score-min"]').setValue('85')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(0)

    await wrapper.get('[data-test="clear-table-filters"]').trigger('click')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(2)

    await wrapper.get('[data-test="filter-turnover-min"]').setValue('yes')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('显示 1 / 2')
    expect(wrapper.text()).toContain('300604')
    expect(wrapper.text()).not.toContain('601857')

    await wrapper.get('[data-test="filter-turnover-extreme"]').setValue('yes')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(1)

    await wrapper.get('[data-test="filter-tail-score-min"]').setValue('20')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(0)
    expect(wrapper.text()).toContain('没有符合当前筛选条件的股票')

    await wrapper.get('[data-test="clear-table-filters"]').trigger('click')
    await flushUi()
    expect(wrapper.findAll('.score-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('显示 2 / 2')
  })
})
