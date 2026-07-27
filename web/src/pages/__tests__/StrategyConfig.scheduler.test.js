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

function brooksTailConfig() {
  return {
    enabled: true,
    mode: 'independent_path',
    context: {
      allowed_start_grades: ['S', 'A'], allow_grade_b_watch_only: true,
      close_below_ma20_atr_tolerance: 0.5, require_ma20_above_ma50: false,
      require_ma20_slope_positive: true, ma20_slope_window_days: 10,
      lower_high_low_window_days: 10, max_lower_high_low_sequence: 2,
    },
    selling_pressure: {
      window_days: 7, strong_bear_body_ratio_min: 0.03,
      strong_bear_close_position_max: 0.25, max_strong_bear_bar_count: 1,
      bear_follow_through_close_position_max: 0.35, max_bear_follow_through_count: 1,
      max_consecutive_bear_bars: 2, require_bear_body_contracting: false,
    },
    price_stability: {
      compact_window_days: 5, close_range_max: 0.08, premium_close_range_max: 0.05,
      atr_contraction_max: 0.8, premium_atr_contraction_max: 0.65,
      avg_body_ratio_max: 0.025, max_body_ratio_max: 0.04,
      max_lower_low_count: 1, low_similarity_tolerance: 0.02,
    },
    volume_dry: {
      tail_window_days: 5, baseline_window_days: 20, tail_volume_ratio_max: 0.75,
      premium_tail_volume_ratio_max: 0.6, require_volume_slope_negative: false,
      reject_high_volume_decline: true,
    },
    support: {
      support_distance_atr: 0.8, support_distance_pct: 0.03,
      effective_break_pct: 0.03, consecutive_close_break_days: 2,
    },
    second_entry: {
      enabled: true, min_separation_days: 2, max_separation_days: 15,
      low_similarity_tolerance: 0.02, signal_bar_close_position_min: 0.55,
      signal_bar_max_body_ratio: 0.03,
    },
    failed_breakout: {
      enabled: true, recovery_days: 2, max_break_distance_atr: 0.8,
      require_reclaim_support: true,
    },
    compact_structure: {
      enabled: true, middle_zone_low: 0.35, middle_zone_high: 0.7,
      max_direction_changes: 3, max_long_shadow_bar_count: 2,
      long_shadow_ratio_min: 0.45,
    },
    trade_trigger: {
      enabled: true, trigger_valid_days: 3, max_trigger_distance_atr: 1.5,
      breakout_follow_through_days: 2,
    },
    scoring: {
      context_points: 4, selling_pressure_points: 6, price_stability_points: 4,
      volume_dry_points: 2, setup_points: 4, pass_score_min: 14,
      premium_score_min: 17,
    },
  }
}

function strategy6InputByLabel(wrapper, label) {
  const param = wrapper.findAll('.strategy6-section .param').filter(node => node.find('label').text() === label).at(-1)
  if (!param) throw new Error(`missing Strategy6 input label: ${label}`)
  return param.find('input')
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
        acquisition_mode: 'tickflow',
        tickflow_access_mode: 'free',
        tickflow_api_key: '',
        tickflow_api_key_configured: true,
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
      strategy6: {
        brooks_tail: brooksTailConfig(),
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

  it('renders and saves an explicit manual market data acquisition mode', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('日线数据获取模式')
    expect(wrapper.text()).toContain('TickFlow 批量模式')
    expect(wrapper.text()).toContain('传统多数据源模式')
    expect(wrapper.find('[data-test="acquisition-mode-tickflow"]').element.checked).toBe(true)

    await wrapper.find('[data-test="acquisition-mode-legacy"]').setValue()
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.data.acquisition_mode).toBe('legacy_multi_source')
  })

  it('defaults to explicit free TickFlow mode and keeps a configured key unused', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.find('[data-test="tickflow-access-free"]').element.checked).toBe(true)
    expect(wrapper.find('[data-test="tickflow-access-authenticated"]').element.checked).toBe(false)
    expect(wrapper.find('[data-test="tickflow-api-key"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已保存的 Key 会保留，但当前不会使用')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.data.tickflow_access_mode).toBe('free')
    expect(payload.data).not.toHaveProperty('tickflow_api_key')
    expect(payload.data).not.toHaveProperty('tickflow_api_key_configured')
  })

  it('shows key controls only in authenticated mode and submits a trimmed replacement', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="tickflow-access-authenticated"]').setValue()
    await flushUi()
    const input = wrapper.find('[data-test="tickflow-api-key"]')
    expect(wrapper.text()).toContain('TickFlow API Key')
    expect(wrapper.text()).toContain('已配置')
    expect(input.attributes('type')).toBe('password')
    await wrapper.find('[data-test="tickflow-api-key-visible"]').trigger('click')
    expect(input.attributes('type')).toBe('text')
    await input.setValue(' future-format-key ')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const payload = api.updateConfig.mock.calls[0][0]
    expect(payload.data.tickflow_access_mode).toBe('authenticated')
    expect(payload.data.tickflow_api_key).toBe('future-format-key')
    expect(input.element.value).toBe('')
    expect(wrapper.text()).toContain('已配置')
  })

  it('renders strategy6 real market filter controls and hides removed sector filter controls', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('最低RS20')
    expect(wrapper.text()).toContain('市场过滤模式')
    expect(wrapper.find('[data-test="strategy6-market-filter-mode"]').element.value).toBe('downgrade')
    expect(wrapper.find('[data-test="strategy6-decision-profile"]').text()).toContain('正式原始链')
    expect(wrapper.find('[data-test="strategy6-decision-profile"]').text()).toContain('仅用于研究')
    expect(wrapper.find('[data-test="strategy6-sector-filter-mode"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('板块新高成员数')
    expect(wrapper.text()).not.toContain('板块过滤模式')
    expect(wrapper.text()).toContain('板块过滤已移除')
    expect(wrapper.text()).not.toContain('真实过滤留到二期接入')
    expect(wrapper.find('[data-test="strategy6-start-age-min"]').element.value).toBe('5')
    expect(wrapper.find('[data-test="strategy6-pattern-mode"]').element.value).toBe('score_only')
    expect(wrapper.find('[data-test="strategy6-pattern-pivot-proximity"]').element.value).toBe('0.05')
    expect(wrapper.find('[data-test="strategy6-breakout-extended-max"]').element.value).toBe('0.08')
    expect(wrapper.find('[data-test="strategy6-vcp-first-max-range"]').element.value).toBe('0.32')
    expect(wrapper.find('[data-test="strategy6-vcp-rebound-min"]').element.value).toBe('0.03')
    expect(wrapper.find('[data-test="strategy6-vcp-rebound-confirm-days"]').element.value).toBe('2')
    expect(wrapper.find('[data-test="strategy6-vcp-low-warning-ratio"]').element.value).toBe('0.99')
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
    expect(payload.strategy6.decision_profile).toBe('formal_original')
    expect(payload.strategy6).not.toHaveProperty('enable_sector_filter')
    expect(payload.strategy6).not.toHaveProperty('sector_filter_mode')
    expect(payload.strategy6).not.toHaveProperty('sector_min_member_new_high_count')
    expect(payload.strategy6.min_relative_strength_20).toBe(0.10)
    expect(payload.strategy6.start_age_min_days).toBe(5)
    expect(payload.strategy6.pattern_filter_mode).toBe('score_only')
    expect(payload.strategy6.pattern_pivot_proximity_pct).toBe(0.05)
    expect(payload.strategy6.breakout_extended_max_pct).toBe(0.08)
    expect(payload.strategy6.vcp_first_contraction_max_range).toBe(0.32)
    expect(payload.strategy6.vcp_rebound_min_pct).toBe(0.03)
    expect(payload.strategy6.vcp_rebound_confirm_days).toBe(2)
    expect(payload.strategy6.vcp_low_warning_ratio).toBe(0.99)
    expect(payload.strategy6.vcp_history_max_start_loss_pct).toBe(0.15)
    expect(payload.strategy6.vcp_history_max_drawdown_pct).toBe(0.20)
    expect(payload.strategy6.vcp_history_bearish_trend_days).toBe(5)
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

  it('shows editable strategy6 VCP history continuity thresholds', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.find('[data-test="strategy6-vcp-history-max-start-loss"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy6-vcp-history-max-drawdown"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy6-vcp-history-bearish-days"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('历史候选至VCP起点最大跌幅')
    expect(wrapper.text()).toContain('历史资格最大回撤')
    expect(wrapper.text()).toContain('历史资格空头失效天数')
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

  it('renders and saves the complete Brooks configuration returned by backend defaults', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    expect(wrapper.text()).toContain('Brooks价格行为第三路径')
    expect(wrapper.text()).toContain('上涨背景')
    expect(wrapper.text()).toContain('卖压衰竭')
    expect(wrapper.text()).toContain('价格稳定与量干')
    expect(wrapper.text()).toContain('结构识别')
    expect(wrapper.text()).toContain('交易触发')
    expect(wrapper.text()).toContain('Brooks评分')
    expect(wrapper.find('[data-test="strategy6-brooks-enabled"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="strategy6-brooks-context-window"]').element.value).toBe('10')
    expect(wrapper.find('[data-test="strategy6-brooks-selling-window"]').element.value).toBe('7')
    expect(wrapper.find('[data-test="strategy6-brooks-stability-window"]').element.value).toBe('5')
    expect(wrapper.find('[data-test="strategy6-brooks-trigger-days"]').element.value).toBe('3')
    expect(wrapper.find('[data-test="strategy6-brooks-pass-score"]').element.value).toBe('14')

    await wrapper.find('[data-test="strategy6-brooks-trigger-days"]').setValue('4')
    await wrapper.find('[data-test="strategy6-brooks-pass-score"]').setValue('15')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    const saved = api.updateConfig.mock.calls[0][0].strategy6.brooks_tail
    expect(saved.trade_trigger.trigger_valid_days).toBe(4)
    expect(saved.scoring.pass_score_min).toBe(15)
    expect(saved.context.allowed_start_grades).toEqual(['S', 'A'])
    expect(saved.failed_breakout.require_reclaim_support).toBe(true)
    expect(saved.scoring).toEqual({
      context_points: 4, selling_pressure_points: 6, price_stability_points: 4,
      volume_dry_points: 2, setup_points: 4, pass_score_min: 15,
      premium_score_min: 17,
    })
  })

  it('rejects invalid Brooks relationships with Chinese business messages', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await wrapper.find('[data-test="strategy6-brooks-pass-score"]').setValue('19')
    await wrapper.find('[data-test="strategy6-brooks-premium-score"]').setValue('17')
    await wrapper.find('[data-test="strategy6-brooks-volume-premium"]').setValue('0.8')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    expect(api.updateConfig).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Brooks通过分不能高于优质分')
    expect(wrapper.text()).toContain('Brooks优质量干比不能高于普通量干比')
    expect(wrapper.text()).not.toContain('pass_score_min')
  })

  it('rejects out-of-range values for every editable Brooks numeric control', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()
    const cases = [
      ['MA20斜率窗口', 10, 1, 'MA20斜率窗口需在 2-60'],
      ['高低点序列窗口', 10, 4, '高低点序列窗口需在 5-60'],
      ['最大下移序列数', 2, 11, '最大下移序列数需在 0-10'],
      ['跌破MA20 ATR容差', 0.5, 3.1, '跌破MA20 ATR容差需在 0-3'],
      ['卖压观察窗口', 7, 2, '观察窗口需在 3-30'],
      ['最多强空方K线', 1, 8, '最大强空方K线数不能超过观察窗口'],
      ['最多空方跟进', 1, 8, '最大空方跟进数不能超过观察窗口'],
      ['最多连续阴线', 2, 8, '最大连续阴线数不能超过观察窗口'],
      ['稳定判断窗口', 5, 2, '价格稳定: 窗口需在 3-10'],
      ['收盘区间上限', 0.08, 2.1, '收盘区间上限需在 0-2'],
      ['优质收盘区间', 0.05, 2.1, '优质收盘区间需在 0-2'],
      ['尾部量比上限', 0.75, 0, '普通量干比需在 (0,2]'],
      ['优质量干比', 0.6, 0, '优质量干比需在 (0,2]'],
      ['量能基准窗口', 20, 9, '基准窗口需在 10-60'],
      ['二次低点最短间隔', 2, 16, '最短低点间隔需在 1-15'],
      ['二次低点最长间隔', 15, 31, '最长低点间隔需在 2-30'],
      ['假跌破收回天数', 2, 6, '收回天数需在 1-5'],
      ['紧密区下界', 0.35, -0.1, '紧密区下界需在 0-1'],
      ['紧密区上界', 0.7, 1.1, '紧密区上界需在 0-1'],
      ['最多方向变化', 3, 11, '方向变化次数需在 0-10'],
      ['最多长影线K线', 2, 11, '长影线K线数需在 0-10'],
      ['触发有效交易日', 3, 0, '有效交易日需在 1-10'],
      ['最大触发距离 ATR', 1.5, 5.1, '最大距离需在 0-5 ATR'],
      ['突破跟进天数', 2, 6, '突破跟进天数需在 1-5'],
      ['背景分', 4, 21, '各分项需在 0-20'],
      ['卖压衰竭分', 6, 21, '各分项需在 0-20'],
      ['价格稳定分', 4, 21, '各分项需在 0-20'],
      ['量干分', 2, 21, '各分项需在 0-20'],
      ['结构分', 4, 21, '各分项需在 0-20'],
      ['Brooks通过分', 14, 21, '通过分和优质分需在 0-20'],
      ['Brooks优质分', 17, 21, '通过分和优质分需在 0-20'],
    ]

    for (const [label, validValue, invalidValue, message] of cases) {
      const input = strategy6InputByLabel(wrapper, label)
      await input.setValue(invalidValue)
      api.updateConfig.mockClear()
      await wrapper.find('.btn-save').trigger('click')
      await flushUi()
      expect(api.updateConfig, label).not.toHaveBeenCalled()
      expect(wrapper.find('.error-msg').text(), label).toContain(message)
      await input.setValue(validValue)
    }
  })

  it('rejects Brooks cross-field relationships before saving', async () => {
    const wrapper = mount(StrategyConfig)
    await flushUi()

    await strategy6InputByLabel(wrapper, '优质收盘区间').setValue('0.09')
    await strategy6InputByLabel(wrapper, '二次低点最短间隔').setValue('10')
    await strategy6InputByLabel(wrapper, '二次低点最长间隔').setValue('8')
    await strategy6InputByLabel(wrapper, '紧密区下界').setValue('0.8')
    await strategy6InputByLabel(wrapper, '紧密区上界').setValue('0.7')
    await wrapper.find('.btn-save').trigger('click')
    await flushUi()

    expect(api.updateConfig).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('优质收盘区间不能高于普通区间')
    expect(wrapper.text()).toContain('最短低点间隔不能高于最长间隔')
    expect(wrapper.text()).toContain('紧密区下界不能高于上界')
  })
})
