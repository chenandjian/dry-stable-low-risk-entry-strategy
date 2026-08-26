import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = { evaluateStrategy6Batch: vi.fn() }
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
        },
        {
          code: '601857', name: '中国石油', evaluationDate: '2026-08-25',
          totalScore: 90, tailScore: 0, tailQualityScore: 16, tailPass: false,
          candidateType: 'REJECTED', tailVolumeRatio: 0.82,
          volumeSlope10: 0.01, closeRange5: 0.04, return5: -0.01,
          tailReasons: [], tailRejects: ['TAIL_VOLUME_NOT_DRY'],
          rejectReasons: ['TAIL_VOLUME_NOT_DRY'],
          scoreBreakdown: { strongStart: 20, pattern: 20, support: 20, tail: 0, objectiveRiskReward: 10, relativeStrengthRisk: 10 },
        },
      ],
      errors: [{ code: '000000', name: '', error: 'KLINE_NOT_FOUND', message: '本地没有K线数据' }],
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
})
