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
