import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  evaluateStrategy6Batch: vi.fn(),
  getLatestStrategy6TrendSqueezeScreen: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

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
    expect(wrapper.text()).toContain('本地没有K线数据')
  })

  it('rejects invalid input before sending the request', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-codes"]').setValue('300604\nABC')
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    expect(api.evaluateStrategy6Batch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('股票代码必须为6位数字')
  })

  it('copies a result stock code without expanding the row', async () => {
    const wrapper = mount(Strategy6BatchEvaluation)
    await wrapper.get('[data-test="batch-submit"]').trigger('click')
    await flushUi()

    await wrapper.get('[data-test="copy-code-300604"]').trigger('click')
    await flushUi()

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('300604')
    expect(wrapper.text()).toContain('已复制')
    expect(wrapper.find('.detail-row').exists()).toBe(false)
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
})
