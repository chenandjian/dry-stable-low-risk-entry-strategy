import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getConfig: vi.fn(),
  updateConfig: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import StrategyConfig from '../StrategyConfig.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function configResponse() {
  return {
    config: {
      market: {},
      liquidity: {
        min_avg_turnover: 100000000,
        min_stock_price: 10,
        min_listing_days: 500,
      },
      data: {
        scan_window_days: 250,
        backtest_window_days: 250,
        daily_sources: ['sina'],
      },
      cup: { min_duration: 35, max_duration: 180, min_depth: 0.12, max_depth: 0.45, max_lip_deviation: 0.12, min_bottom_roundness: 0.15 },
      handle: { min_duration: 5, max_duration: 30, max_depth: 0.18 },
      breakout: { buffer_pct: 0.02, volume_multiplier: 1.5 },
      decision: { max_risk_percent: 10 },
      volume_dry: { bad_shrink_max_score: 7, low_position_max_score: 7, volume_stall_max_score: 7, big_bear_max_score: 6 },
      price_stable: { close_tightness_strong_pct: 3, support_break_max_score: 5 },
      risk_reward: { atr_stop_multiplier: 1.2 },
      strategy2: {
        enabled: false,
        strategy_window_days: 250,
        minimum_required_days: 250,
        candidate_min_score: 70,
        minimum_volume_dry_score: 40,
        short_term_time_exit_days: 5,
        max_risk_ratio: 0.05,
        support_lookback_days: 10,
        buy_zone_max_premium: 0.03,
        stop_loss_buffer: 0.03,
      },
      scheduler: {
        enabled: false,
        serial_dual_scan: {
          enabled: true,
          cron: '15 15 * * 1-5',
          strategy1_failed_retry_rounds: 3,
        },
      },
    },
  }
}

describe('StrategyConfig scheduler controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getConfig.mockResolvedValue(configResponse())
    api.updateConfig.mockResolvedValue({ status: 'ok' })
  })

  it('renders scheduler controls and saves enabled time as weekday cron', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('定时任务')
    expect(wrapper.text()).toContain('启用定时任务')
    expect(wrapper.text()).toContain('启用串行三策略扫描')
    expect(wrapper.text()).toContain('先执行策略1，完成后再执行策略2和策略3')
    expect(wrapper.text()).toContain('执行时间')
    expect(wrapper.find('[data-test="scheduler-time"]').element.value).toBe('15:15')

    await wrapper.find('[data-test="scheduler-enabled"]').trigger('click')
    await wrapper.find('[data-test="scheduler-time"]').setValue('14:30')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.scheduler.enabled).toBe(true)
    expect(payload.scheduler.serial_dual_scan.enabled).toBe(true)
    expect(payload.scheduler.serial_dual_scan.cron).toBe('30 14 * * 1-5')
  })

  it('rejects invalid scheduler time before saving', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="scheduler-time"]').setValue('25:99')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    expect(api.updateConfig).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('定时任务执行时间格式不正确')
  })

  it('saves disabled serial dual scan switch explicitly', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="serial-dual-scan-enabled"]').trigger('click')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.scheduler.enabled).toBe(false)
    expect(payload.scheduler.serial_dual_scan.enabled).toBe(false)
    expect(payload.scheduler.serial_dual_scan.cron).toBe('15 15 * * 1-5')
  })

  it('saves strategy3 defaults when loading an older config without strategy3 section', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.strategy3.enabled).toBe(true)
    expect(payload.strategy3.strategy_window_days).toBe(250)
    expect(payload.strategy3.minimum_required_days).toBe(180)
    expect(payload.strategy3.candidate_min_score).toBe(75)
    expect(payload.strategy3.core_min_score).toBe(85)
    expect(payload.strategy3.max_risk_ratio).toBe(0.08)
    expect(payload.strategy3.min_pullback_from_high).toBe(0.12)
    expect(payload.strategy3.max_pullback_from_high).toBe(0.25)
    expect(payload.strategy3.volume_shrink_ratio).toBe(0.70)
    expect(payload.strategy3.dry_return_5_floor).toBe(0.02)
    expect(payload.strategy3.dry_support_max_test_count).toBe(2)
  })
})
