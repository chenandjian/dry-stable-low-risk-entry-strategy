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

  it('renders strategy3 formal candidate filter controls', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('正式候选过滤')
    expect(wrapper.text()).toContain('正式候选分数')
    expect(wrapper.text()).toContain('正式最大风险')
    expect(wrapper.text()).toContain('正式最大回撤')
    expect(wrapper.find('[data-test="strategy3-trade-score"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy3-trade-risk"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy3-trade-pullback"]').exists()).toBe(true)
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
    expect(payload.strategy3.trade_candidate_min_score).toBe(88)
    expect(payload.strategy3.trade_max_risk_ratio).toBe(0.04)
    expect(payload.strategy3.trade_max_pullback_pct).toBe(0.16)
    expect(payload.strategy3.min_pullback_from_high).toBe(0.12)
    expect(payload.strategy3.max_pullback_from_high).toBe(0.25)
    expect(payload.strategy3.volume_shrink_ratio).toBe(0.70)
    expect(payload.strategy3.dry_return_5_floor).toBe(0.02)
    expect(payload.strategy3.dry_support_max_test_count).toBe(2)
  })

  it('saves optimized strategy4 defaults when loading an older config without strategy4 section', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.strategy4.hot_topic_top_n).toBe(16)
    expect(payload.strategy4.watch_hot_topic_top_n).toBe(16)
    expect(payload.strategy4.min_hot_topic_score).toBe(65)
    expect(payload.strategy4.min_hot_topic_signal_count).toBe(1)
    expect(payload.strategy4.min_leader_strength_score).toBe(50)
    expect(payload.strategy4.core_leader_strength_score).toBe(50)
    expect(payload.strategy4.min_first_wave_return_10d).toBe(0.10)
    expect(payload.strategy4.min_first_wave_return_20d).toBe(0.15)
    expect(payload.strategy4.min_strong_day_count_10d).toBe(1)
    expect(payload.strategy4.pullback_min_pct).toBe(0.05)
    expect(payload.strategy4.pullback_max_pct).toBe(0.30)
    expect(payload.strategy4.pullback_min_days).toBe(1)
    expect(payload.strategy4.pullback_max_days).toBe(40)
    expect(payload.strategy4.max_risk_ratio).toBe(0.10)
    expect(payload.strategy4.aggressive_max_risk_ratio).toBe(0.10)
    expect(payload.strategy4.min_reward_risk_ratio).toBe(1.5)
    expect(payload.strategy4.core_leader_min_reward_risk_ratio).toBe(1.5)
    expect(payload.strategy4.derived_source.topic_top_n).toBe(30)
    expect(payload.strategy4.derived_source.max_topics_per_day).toBe(34)
    expect(payload.strategy4.derived_source.max_leaders_per_topic).toBe(5)
    expect(payload.strategy4.derived_source.min_topic_hot_score).toBe(50)
    expect(payload.strategy4.derived_source.min_confirmed_topic_hot_score).toBe(60)
    expect(payload.strategy4.tracking.max_calendar_days).toBe(20)
    expect(payload.strategy4.tracking.strong_attention_days).toBe(20)
    expect(payload.strategy4.tracking.golden_second_wave_days).toBe(20)
    expect(payload.strategy4.tracking.allow_extension_days).toBe(20)
  })

  it('renders strategy6 real market filter controls and hides removed sector filter controls', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('最低RS20')
    expect(wrapper.text()).toContain('市场过滤模式')
    expect(wrapper.find('[data-test="strategy6-market-filter-mode"]').element.value).toBe('downgrade')
    expect(wrapper.find('[data-test="strategy6-sector-filter-mode"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('板块新高成员数')
    expect(wrapper.text()).not.toContain('板块过滤模式')
    expect(wrapper.text()).toContain('板块过滤已移除')
    expect(wrapper.text()).not.toContain('真实过滤留到二期接入')
    expect(wrapper.find('[data-test="strategy6-start-age-min"]').element.value).toBe('5')
    expect(wrapper.find('[data-test="strategy6-pattern-mode"]').element.value).toBe('score_only')
    expect(wrapper.find('[data-test="strategy6-pattern-pivot-proximity"]').element.value).toBe('0.05')
    expect(wrapper.find('[data-test="strategy6-breakout-extended-max"]').element.value).toBe('0.08')
    expect(wrapper.find('[data-test="strategy6-stop-atr-multiplier"]').element.value).toBe('0.8')
    expect(wrapper.find('[data-test="strategy6-max-watch-days"]').element.value).toBe('10')
    const strategy6Text = wrapper.find('.strategy6-section').text()
    expect(strategy6Text).toContain('严格过滤')
    expect(strategy6Text).toContain('降级处理')
    expect(strategy6Text).toContain('仅调整评分')
    expect(strategy6Text).not.toContain('strict ·')
    expect(strategy6Text).not.toContain('downgrade ·')
    expect(strategy6Text).not.toContain('score_only ·')
    expect(strategy6Text).not.toContain('READY_CANDIDATE')
    expect(strategy6Text).not.toContain('KEY_CANDIDATE')
    expect(strategy6Text).not.toContain('WATCH_CANDIDATE')
    expect(strategy6Text).not.toContain('Pivot')
  })

  it('saves strategy6 market filter mode without legacy sector filter fields', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="strategy6-market-filter-mode"]').setValue('strict')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.strategy6.market_filter_mode).toBe('strict')
    expect(payload.strategy6).not.toHaveProperty('enable_sector_filter')
    expect(payload.strategy6).not.toHaveProperty('sector_filter_mode')
    expect(payload.strategy6).not.toHaveProperty('sector_min_member_new_high_count')
    expect(payload.strategy6.min_relative_strength_20).toBe(0.10)
    expect(payload.strategy6.start_age_min_days).toBe(5)
    expect(payload.strategy6.pattern_filter_mode).toBe('score_only')
    expect(payload.strategy6.pattern_pivot_proximity_pct).toBe(0.05)
    expect(payload.strategy6.breakout_extended_max_pct).toBe(0.08)
    expect(payload.strategy6.stop_atr_multiplier).toBe(0.8)
    expect(payload.strategy6.max_watch_days).toBe(10)
  })

  it('shows strategy6 validation errors with Chinese business terms', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="strategy6-pattern-pivot-proximity"]').setValue(0)
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('形态距突破枢轴最大下偏')
    expect(wrapper.text()).not.toContain('形态距Pivot最大下偏')
  })

  it('renders and saves nested strategy6 box-tail and compact-kline controls', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('稳定箱体尾部路径')
    expect(wrapper.find('[data-test="strategy6-box-tail-enabled"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy6-box-min-days"]').element.value).toBe('5')
    expect(wrapper.find('[data-test="strategy6-box-max-days"]').element.value).toBe('30')
    expect(wrapper.find('[data-test="strategy6-compact-enabled"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy6-compact-window"]').element.value).toBe('5')

    await wrapper.find('[data-test="strategy6-compact-enabled"]').trigger('click')
    await wrapper.find('[data-test="strategy6-box-width-normal"]').setValue('0.16')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.strategy6.box_tail.enabled).toBe(true)
    expect(payload.strategy6.box_tail.normal_box_width_max).toBe(0.16)
    expect(payload.strategy6.box_tail.compact_kline.enabled).toBe(false)
    expect(payload.strategy6.box_tail.compact_kline.min_overlap_pair_count).toBe(3)
  })
})
