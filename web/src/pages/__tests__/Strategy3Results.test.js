import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy3Tasks: vi.fn(),
  getStrategy3Candidates: vi.fn(),
  getTaskStocks: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy3Results from '../Strategy3Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function mountPage(query = {}) {
  return mount(Strategy3Results, {
    global: {
      mocks: { $route: { query } },
      stubs: { RouterLink: true },
    },
  })
}

describe('Strategy3Results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy3Tasks.mockResolvedValue({
      ok: true,
      tasks: [{ id: 's3-task', status: 'completed', candidates: 1, strategy_type: 'STRATEGY_3_STRONG_PULLBACK_SECOND_BREAKOUT' }],
    })
    api.getStrategy3Candidates.mockResolvedValue({
      ok: true,
      candidates: [{
        code: '000001',
        name: '平安银行',
        total_score: 88,
        level: '核心候选',
        trend_score: 25,
        pullback_score: 20,
        volume_stability_score: 18,
        second_breakout_score: 12,
        risk_reward_score: 13,
        v3: 500000,
        v5: 600000,
        v10: 800000,
        v20: 1000000,
        volume_ratio_5_20: 0.6,
        return_5: 0.02,
        no_new_low: 1,
        support_price_10: 9.7,
        support_test_count: 3,
        support_valid: 1,
        bear_body_shrink: 1,
        lower_shadow_count: 2,
        down_volume_ratio_5: 0.42,
        atr_ratio_5_20: 0.68,
        has_big_down_volume: 0,
        pullback_pct: 0.15,
        risk_ratio: 0.05,
        rr1: 2.1,
        support_price: 9.5,
        stop_loss: 9.31,
        tactical_support: 9.5,
        tactical_stop_loss: 9.31,
        tactical_risk_ratio: 0.05,
        tactical_rr1: 2.1,
        structural_support: 8.8,
        structural_stop_loss: 8.62,
        structural_risk_ratio: 0.138,
        support_quality: 'ma20',
        short_support: 9.8,
        short_support_zone_low: 9.65,
        short_support_zone_high: 9.95,
        key_support: 9.7,
        key_support_zone_low: 9.5,
        key_support_zone_high: 9.9,
        strong_support: 9.2,
        strong_support_zone_low: 9.05,
        strong_support_zone_high: 9.35,
        support_status: 'VALID',
        break_status: 'NOT_BROKEN',
        nearest_support_distance: 0.03,
        support_sources: ['min_close_10', 'ma20'],
        target_1: 12,
        evaluation_date: '2026-06-25',
      }],
    })
    api.getTaskStocks.mockResolvedValue({ ok: true, total: 0, stocks: [] })
  })

  it('renders strategy3 candidate fields from route task', async () => {
    const wrapper = mountPage({ task: 's3-task' })
    await flushUi()

    expect(api.getStrategy3Candidates).toHaveBeenCalledWith('s3-task')
    expect(wrapper.text()).toContain('强势回踩二次启动')
    expect(wrapper.text()).toContain('000001')
    expect(wrapper.text()).toContain('核心候选')
    expect(wrapper.text()).toContain('趋势')
    expect(wrapper.text()).toContain('回踩幅度')
    expect(wrapper.text()).toContain('战术风险比')
    expect(wrapper.text()).toContain('结构风险比')
    expect(wrapper.text()).toContain('RR1')
    expect(wrapper.text()).toContain('2026-06-25')

    await wrapper.find('tbody tr').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('量干跌不动质量')
    expect(wrapper.text()).toContain('5日涨跌')
    expect(wrapper.text()).toContain('支撑测试')
    expect(wrapper.text()).toContain('ATR5/20')
    expect(wrapper.text()).toContain('支撑区 V2')
    expect(wrapper.text()).toContain('关键支撑区')
    expect(wrapper.text()).toContain('VALID')
    expect(wrapper.text()).toContain('min_close_10')
  })

  it('keeps existing candidates when refresh fails', async () => {
    const wrapper = mountPage({ task: 's3-task' })
    await flushUi()
    expect(wrapper.text()).toContain('000001')

    api.getStrategy3Candidates.mockRejectedValueOnce(new Error('network'))
    await wrapper.find('select').trigger('change')
    await flushUi()

    expect(wrapper.text()).toContain('策略3候选加载失败')
    expect(wrapper.text()).toContain('000001')
  })
})
