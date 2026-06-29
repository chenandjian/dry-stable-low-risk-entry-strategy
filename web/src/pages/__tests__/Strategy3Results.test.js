import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
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

function installDownloadMocks() {
  const originalUrl = globalThis.URL
  const createObjectURL = vi.fn(() => 'blob:strategy3')
  const revokeObjectURL = vi.fn()
  const click = vi.fn()
  vi.stubGlobal('URL', { ...originalUrl, createObjectURL, revokeObjectURL })
  const originalCreateElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(tag => {
    const el = originalCreateElement(tag)
    if (tag === 'a') vi.spyOn(el, 'click').mockImplementation(click)
    return el
  })
  return { createObjectURL, click }
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
        range_5: 0.026,
        range_10: 0.061,
        range_20: 0.118,
        range_compression_ok: 1,
        close_range_5: 0.018,
        direction_efficiency_5: 0.22,
        max_up_5: 0.021,
        max_down_5: -0.018,
        avg_close_position_5: 0.52,
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
        trade_quality_score: 92,
        volume_dry_score: 18,
        price_stability_score: 17,
        cannot_fall_score: 16,
        balance_powerless_score: 14,
        support_distance_pct: 0.025,
        key_support_distance_pct: 0.03,
        target_price: 12,
        target_room_pct: 0.20,
        estimated_rr: 2.2,
        trade_state: 'LOW_ABSORB',
        trade_state_label: '低吸',
        trigger_reasons: ['volume:extreme_dry', 'support:near_tactical_support'],
        risk_warnings: ['risk:rr_not_enough_for_low_absorb'],
        invalid_conditions: [],
        target_1: 12,
        evaluation_date: '2026-06-25',
      }],
    })
    api.getTaskStocks.mockResolvedValue({ ok: true, total: 0, stocks: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
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
    expect(wrapper.text()).toContain('交易状态')
    expect(wrapper.text()).toContain('低吸')
    expect(wrapper.text()).toContain('交易质量')
    expect(wrapper.text()).toContain('92')
    expect(wrapper.text()).toContain('预估RR')
    expect(wrapper.text()).toContain('2.20')
    expect(wrapper.text()).toContain('战术支撑/Key支撑/止损/目标')
    expect(wrapper.text()).toContain('9.50 / 9.70 / 9.31 / 12.00')
    expect(wrapper.text()).toContain('2026-06-25')

    await wrapper.find('tbody tr').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('量干跌不动质量')
    expect(wrapper.text()).toContain('5日涨跌')
    expect(wrapper.text()).toContain('支撑测试')
    expect(wrapper.text()).toContain('ATR5/20')
    expect(wrapper.text()).toContain('极致价稳 V3')
    expect(wrapper.text()).toContain('方向效率')
    expect(wrapper.text()).toContain('最大上涨/下跌')
    expect(wrapper.text()).toContain('压缩序列')
    expect(wrapper.text()).toContain('支撑区 V2')
    expect(wrapper.text()).toContain('关键支撑区')
    expect(wrapper.text()).toContain('交易质量过滤层')
    expect(wrapper.text()).toContain('量干/价稳/跌不动/无力')
    expect(wrapper.text()).toContain('18 / 17 / 16 / 14')
    expect(wrapper.text()).toContain('距战术支撑')
    expect(wrapper.text()).toContain('2.50%')
    expect(wrapper.text()).toContain('目标空间')
    expect(wrapper.text()).toContain('20.00%')
    expect(wrapper.text()).toContain('触发原因')
    expect(wrapper.text()).toContain('volume:extreme_dry')
    expect(wrapper.text()).toContain('风险提示')
    expect(wrapper.text()).toContain('risk:rr_not_enough_for_low_absorb')
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

  it('exports the current strategy3 candidate list as csv', async () => {
    const wrapper = mountPage({ task: 's3-task' })
    await flushUi()
    const mocks = installDownloadMocks()

    const button = wrapper.find('[data-test="export-candidates"]')
    expect(button.exists()).toBe(true)
    expect(button.text()).toContain('一键导出列表')
    await button.trigger('click')

    expect(mocks.click).toHaveBeenCalled()
    const blob = mocks.createObjectURL.mock.calls[0][0]
    const csv = await blob.text()
    expect(csv).toContain('代码,名称,总分,等级')
    expect(csv).toContain('000001,平安银行,88,核心候选')
    expect(csv).toContain('9.50,9.70,9.31,12.00')
    expect(csv).toContain('低吸,92,2.20,18,17,16,14')
    expect(csv).toContain('22.00%,2.10%,-1.80%,0.52,6.10%,11.80%,是')
  })
})
