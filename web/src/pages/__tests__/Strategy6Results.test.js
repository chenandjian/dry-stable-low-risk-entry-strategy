import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy6Tasks: vi.fn(),
  getStrategy6Candidates: vi.fn(),
  getStrategy6MarketSnapshot: vi.fn(),
  getStrategy6Lifecycle: vi.fn(),
  downloadStrategy6Report: vi.fn(),
}

vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy6Results from '../Strategy6Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function installDownloadMocks() {
  const originalUrl = globalThis.URL
  const createObjectURL = vi.fn(() => 'blob:strategy6')
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

describe('Strategy6Results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy6Tasks.mockResolvedValue({ tasks: [{ id: 's6-task', status: 'completed', candidates: 3 }] })
    api.getStrategy6Candidates.mockResolvedValue({
      candidates: [
        {
          code: '000001',
          name: '平安银行',
          candidate_type: 'READY_CANDIDATE',
          classification: 'ready',
          lifecycle_status: 'BUY_ZONE',
          total_score: 91,
          score_model_version: 'S6_QUALITY_V2',
          entry_archetype: 'SUPPORT_PULLBACK',
          start_event_quality_score: 17,
          setup_quality_score: 21,
          setup_quality_reasons: ['gain_retention=0.820'],
          setup_quality_risk_tags: [],
          support_reaction_score: 8,
          support_reaction_reasons: ['SUPPORT_TEST_RECOVERED'],
          support_reaction_risk_tags: [],
          path_evidence_score: 13,
          tail_segmentation_status: 'DYNAMIC_CONTRACTION',
          tail_segmentation_score: 4,
          current_price: 12.34,
          start_type: 'VOLUME_LIMIT_UP',
          start_grade: 'S',
          start_low: 11.2,
          days_since_start: 5,
          support_status: 'MA10_SUPPORT',
          key_support_price: 11.8,
          prior_key_support_price: 11.6,
          buy_zone_low: 11.8,
          buy_zone_high: 12.2,
          stop_loss_price: 11.45,
          target_price_1: 13.2,
          target_price_2: 14.8,
          target_price_3: 16.5,
          risk_reward_ratio_2: 3.4,
          volume_ratio_5_20: 0.52,
          relative_strength_20: 0.18,
          market_status: 'MARKET_WEAK',
          first_pool_date: '2026-07-01',
          pool_age_trading_days: 6,
          enable_market_filter: true,
          market_filter_mode: 'downgrade',
          risk_tags: [],
          warn_tags: ['NEAR_120D_PRESSURE'],
          evaluation_date: '2026-07-09',
          strategy_version: '4.0.0',
          phase_status: 'PHASE_VALID',
          consolidation_start_date: '2026-06-20',
          tail_start_date: '2026-07-03',
          pattern_type: 'VCP',
          pivot_source: 'VCP_LAST_CONTRACTION',
          tactical_support_price: 11.9,
          support_cluster_sources: ['MA10', 'PATTERN_LOW'],
          objective_target_1: 13.2,
          objective_target_2: 14.8,
          objective_rr_1: 1.8,
          objective_rr_2: 3.4,
          execution_target_1_5r: 13.68,
          execution_target_2r: 14.43,
          execution_target_2_5r: 15.18,
          execution_target_3_5r: 16.68,
          valid_from_date: '2026-07-10',
          valid_until_date: '2026-07-14',
          suggested_limit_price: 12.2,
          execution_notes: ['NEXT_TRADING_DAY_ONLY', 'T1_STOP_UNAVAILABLE_ON_BUY_DAY'],
          pattern_score_component: 18,
          tail_score: 19,
          objective_rr_score: 9,
          relative_strength_risk_score: 8,
          tail_avg_volume: 500000,
          pre_tail_avg_volume_20: 1000000,
          tail_volume_ratio: 0.5,
          original_tail_pass: false,
          original_tail_score: 12,
          box_tail_enabled: true,
          box_tail_pass: true,
          box_tail_score: 18,
          box_status: 'BOX_SUPPORT_READY',
          tail_pass: true,
          tail_path: 'BOX',
          box_start_date: '2026-06-25',
          box_end_date: '2026-07-09',
          box_days: 11,
          box_high: 12.5,
          box_low: 11.8,
          box_width: 0.0593,
          box_position: 0.35,
          box_low_test_count: 2,
          box_high_test_count: 2,
          box_volume_contraction_ratio: 0.65,
          box_center_shift: 0.0083,
          compact_kline_enabled: true,
          compact_kline_pass: true,
          compact_kline_score: 9,
          box_quality_score: 27,
          box_quality_tag: 'BOX_COMPACT_READY',
          avg_body_ratio_5: 0.016,
          compact_close_range_5: 0.028,
          kline_overlap_pair_count: 3,
          atr_contraction_ratio: 0.60,
          brooks_tail_enabled: true,
          brooks_tail_pass: true,
          brooks_tail_score: 19,
          brooks_tail_premium: true,
          brooks_status: 'BROOKS_SUPPORT_READY',
          brooks_trade_ready: true,
          brooks_trade_trigger_type: 'BROOKS_SUPPORT_READY',
          brooks_trigger_valid_until: '2026-07-14',
          tail_paths: ['BOX', 'BROOKS'],
          tail_path_summary: 'MULTI',
          tail_primary_path: 'BROOKS',
          passed_path_count: 2,
          multi_path_confirmed: true,
          brooks_result: {
            bull_context_pass: true,
            selling_pressure_exhausted: true,
            price_stable_pass: true,
            volume_dry_pass: true,
            support_not_broken: true,
            setup_pass: true,
            context: {
              context_type: 'BULL_CONTEXT',
              passed: true,
              watch_only: false,
              reasons: ['brooks:bull_context'],
              risk_tags: [],
            },
            selling_pressure: {
              exhausted: true,
              strong_bear_bar_count: 0,
              bear_follow_through_count: 0,
              reasons: ['brooks:selling_pressure_exhausted'],
              risk_tags: [],
            },
            structure: {
              micro_double_bottom: true,
              failed_bear_breakout: false,
              second_entry_long_ready: true,
              second_entry_signal_date: '2026-07-09',
              second_entry_trigger_price: 12.40,
              setup_types: ['MICRO_DOUBLE_BOTTOM', 'SECOND_ENTRY_LONG_READY'],
              reasons: ['brooks:micro_double_bottom'],
              risk_tags: [],
            },
            compact_structure: {
              structure_type: 'COMPACT_ORDERLY',
              direction_change_count: 2,
              long_shadow_bar_count: 0,
              barb_wire_risk: false,
              reasons: ['brooks:compact_orderly'],
              risk_tags: [],
            },
            trade_trigger: {
              ready: true,
              trigger_type: 'BROOKS_SUPPORT_READY',
              trigger_valid_until: '2026-07-14',
              reasons: ['brooks:second_entry_triggered'],
              risk_tags: [],
            },
            reasons: ['brooks:score_pass'],
            reject_reasons: [],
            risk_tags: [],
          },
        },
        {
          code: '000002',
          name: '万科A',
          candidate_type: 'KEY_CANDIDATE',
          classification: 'key',
          lifecycle_status: 'READY',
          total_score: 82,
          current_price: 8.88,
          start_type: 'NORMAL_STRONG_BREAKOUT',
          start_grade: 'A',
          support_status: 'MA20_SUPPORT',
          key_support_price: 8.4,
          buy_zone_low: 8.4,
          buy_zone_high: 8.65,
          stop_loss_price: 8.1,
          target_price_2: 10.2,
          risk_reward_ratio_2: 2.2,
          volume_ratio_5_20: 0.66,
          tail_avg_volume: 0,
          pre_tail_avg_volume_20: 0,
          tail_volume_ratio: 0,
          tail_path: 'NONE',
          risk_tags: ['UPPER_PRESSURE'],
          warn_tags: [],
        },
        {
          code: '000003',
          name: '观察股',
          candidate_type: 'WATCH_CANDIDATE',
          classification: 'watch',
          lifecycle_status: 'SETUP_FORMING',
          total_score: 68,
          support_status: 'MA50_TESTING',
          risk_reward_ratio_2: 1.6,
        },
      ],
    })
    api.getStrategy6MarketSnapshot.mockResolvedValue({
      snapshot: {
        market_status: 'MARKET_STRONG',
        market_reasons: ['above_ma20=2', 'ma20_above_ma50=1', 'risk_count=0'],
        indexes: [
          {
            symbol: 'sh000001',
            name: '上证指数',
            latest_date: '2026-07-09',
            latest_close: 3200.5,
            ma20: 3150.2,
            ma50: 3100.1,
            return_20: 0.035,
            above_ma20: true,
            ma20_above_ma50: true,
            volume_down_risk: false,
            rows_count: 80,
            source: 'sina',
            fetched_at: '2026-07-09 15:20:00',
            data_status: 'FRESH',
          },
        ],
      },
    })
    api.getStrategy6Lifecycle.mockResolvedValue({
      lifecycle: [{
        code: '600001', name: '退出样本', lifecycle_status: 'FAILED',
        exit_reason: 'SUPPORT_FAILED', cooldown_until_date: '2026-07-23',
        first_seen_date: '2026-07-01', days_in_pool: 8, reentry_count: 1,
        blocked: true,
      }],
    })
    api.downloadStrategy6Report.mockResolvedValue(new Blob(['xlsx-bytes'], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders strategy6 ready, key and watch candidates with trade plan fields', async () => {
    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-task' } },
        },
      },
    })
    await flushUi()

    expect(api.getStrategy6Candidates).toHaveBeenCalledWith('s6-task')
    expect(wrapper.text()).toContain('策略6')
    expect(wrapper.text()).toContain('就绪候选')
    expect(wrapper.text()).toContain('重点候选')
    expect(wrapper.text()).toContain('观察候选')
    expect(wrapper.text()).not.toContain('READY_CANDIDATE')
    expect(wrapper.text()).not.toContain('KEY_CANDIDATE')
    expect(wrapper.text()).not.toContain('WATCH_CANDIDATE')
    expect(wrapper.text()).toContain('放量涨停启动 / S')
    expect(wrapper.text()).toContain('MA10支撑')
    expect(wrapper.text()).toContain('11.80 / 11.60')
    expect(wrapper.text()).toContain('启动后5日')
    expect(wrapper.text()).toContain('启动日低点')
    expect(wrapper.text()).toContain('11.80 - 12.20')
    expect(wrapper.text()).toContain('止损')
    expect(wrapper.text()).toContain('RR2')
    expect(wrapper.text()).toContain('3.40')
    expect(wrapper.text()).toContain('买入区间')
    expect(wrapper.text()).toContain('市场偏弱')
    expect(wrapper.text()).toContain('RS20 18.00%')
    expect(wrapper.text()).toContain('市场过滤数据')
    expect(wrapper.text()).toContain('上证指数')
    expect(wrapper.text()).toContain('3200.50')
    expect(wrapper.text()).toContain('MA20')
    expect(wrapper.text()).toContain('数据状态')
    expect(wrapper.text()).toContain('新鲜')
    expect(wrapper.text()).toContain('新浪')
    expect(wrapper.text()).toContain('2026-07-09 15:20:00')
    expect(wrapper.text()).not.toContain('板块过滤')
    expect(wrapper.text()).toContain('首次入池 2026-07-01')
    expect(wrapper.text()).toContain('池龄 6日')
    expect(wrapper.text()).toContain('接近120日压力位')
    expect(wrapper.text()).toContain('VCP')
    expect(wrapper.text()).toContain('客观目标')
    expect(wrapper.text()).toContain('执行R目标')
    expect(wrapper.text()).toContain('尾部路径')
    expect(wrapper.text()).toContain('稳定箱体路径')
    expect(wrapper.text()).toContain('多路径确认')
    expect(wrapper.text()).toContain('主路径 Brooks价格行为')
    expect(wrapper.text()).toContain('Brooks价格行为证据')
    expect(wrapper.text()).toContain('上涨背景')
    expect(wrapper.text()).toContain('卖压衰竭')
    expect(wrapper.text()).toContain('微型双底')
    expect(wrapper.text()).toContain('有序紧密结构')
    expect(wrapper.text()).toContain('交易触发已确认')
    expect(wrapper.text()).toContain('二次入场突破触发')
    expect(wrapper.text()).toContain('12.40')
    expect(wrapper.text()).toContain('箱体下沿支撑就绪')
    expect(wrapper.text()).toContain('箱体K线紧密就绪')
    expect(wrapper.text()).toContain('11.80 - 12.50')
    expect(wrapper.text()).toContain('下沿测试2次')
    expect(wrapper.text()).toContain('紧密排列')
    expect(wrapper.text()).toContain('支撑低吸')
    expect(wrapper.text()).toContain('整理质量 21')
    expect(wrapper.text()).toContain('支撑反应 8')
    expect(wrapper.text()).toContain('启动质量 17')
    expect(wrapper.text()).toContain('路径证据 13')
    expect(wrapper.text()).toContain('动态收缩尾段')
    expect(wrapper.text()).toContain('未形成尾段（V5/V20 0.660）')
    expect(wrapper.vm.tailVolumeDisplay({
      tail_avg_volume: 0,
      pre_tail_avg_volume_20: 0,
      tail_volume_ratio: 0,
      volume_ratio_5_20: null,
    })).toBe('未形成尾段')
    expect(wrapper.text()).toContain('2026-07-10 至 2026-07-14')
    expect(wrapper.text()).toContain('仅限下一交易日执行')
    expect(wrapper.text()).toContain('4.0.0')
    expect(api.getStrategy6Lifecycle).toHaveBeenCalledWith('s6-task')
    expect(wrapper.text()).toContain('生命周期退出/冷却审计')
    expect(wrapper.text()).toContain('退出样本')
    expect(wrapper.text()).toContain('支撑失效')
  })

  it('renders an independent VCP observation section without removing trade groups', async () => {
    api.getStrategy6Candidates.mockResolvedValue({ candidates: [
      {
        code: '002156', name: '通富微电', candidate_type: 'KEY_CANDIDATE',
        lifecycle_status: 'READY', total_score: 82, current_price: 78.71,
        vcp_observation_eligible: true, vcp_lifecycle_status: 'VCP_EXTENDED',
        vcp_contraction_count: 2, vcp_pivot_price: 68.21, vcp_structure_low: 65.61,
        vcp_distance_to_pivot_pct: 0.154, vcp_breakout_date: '2026-07-09',
        vcp_contractions: [
          { peak_date: '2026-06-30', low_date: '2026-07-03', amplitude: 0.1459, avg_volume: 138603150 },
          { peak_date: '2026-07-07', low_date: '2026-07-08', amplitude: 0.0381, avg_volume: 120261046 },
        ],
        vcp_observation_reasons: ['VCP_RANGE_CONTRACTING', 'VCP_VOLUME_CONTRACTING'],
        vcp_observation_risk_tags: ['VCP_PRICE_EXTENDED'],
      },
      {
        code: '300001', name: '观察样本', candidate_type: 'REJECTED',
        classification: 'observation', lifecycle_status: 'FAILED', total_score: 51,
        vcp_observation_eligible: true, vcp_lifecycle_status: 'VCP_NEAR_PIVOT',
        vcp_contraction_count: 3, vcp_pivot_price: 12.5, vcp_structure_low: 11.8,
        vcp_distance_to_pivot_pct: -0.012, vcp_observation_risk_tags: [],
      },
      {
        code: '300002', name: '失效样本', candidate_type: 'REJECTED',
        classification: 'observation', entry_archetype: 'WAIT_BREAKOUT',
        vcp_observation_eligible: false, vcp_lifecycle_status: 'VCP_INVALID',
        vcp_invalidation_reason: 'VCP_STRUCTURE_LOW_BROKEN',
        vcp_exit_audit: true,
      },
      {
        code: '300003', name: '伪退出样本', candidate_type: 'REJECTED',
        classification: 'observation', vcp_observation_eligible: false,
        vcp_lifecycle_status: 'VCP_INVALID', vcp_exit_audit: false,
      },
      {
        code: '600001', name: '旧任务样本', candidate_type: 'WATCH_CANDIDATE',
        lifecycle_status: 'SETUP_FORMING', total_score: 65,
      },
    ] })

    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()

    const text = wrapper.text()
    expect(text.indexOf('市场过滤数据')).toBeLessThan(text.indexOf('重点候选'))
    expect(text.indexOf('重点候选')).toBeLessThan(text.indexOf('观察候选'))
    expect(text.indexOf('观察候选')).toBeLessThan(text.indexOf('VCP形态候选'))
    expect(wrapper.find('[data-test="vcp-row-002156"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="vcp-row-300001"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="vcp-row-300002"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="vcp-row-600001"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="candidate-row-002156"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="candidate-row-300001"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="candidate-row-300002"]').exists()).toBe(false)
    expect(text).toContain('候选数 2')
    expect(text).toContain('VCP观察退出审计')
    expect(text).toContain('失效样本')
    expect(text).not.toContain('伪退出样本')
    expect(text).toContain('VCP结构低点被跌破')
    expect(text).toContain('突破后过度延伸')
    expect(text).toContain('接近VCP支点')
    expect(text).toContain('VCP价格偏离支点过远')
    expect(text).toContain('68.21')
    expect(text).toContain('65.61')
    expect(text).toContain('15.40%')

    await wrapper.find('[data-test="vcp-row-002156"]').trigger('click')
    expect(wrapper.text()).toContain('VCP生命周期')
    expect(wrapper.text()).toContain('2026-07-09')
    expect(wrapper.text()).toContain('VCP收缩证据')
    expect(wrapper.text()).toContain('第1段 2026-06-30 至 2026-07-03')
    expect(wrapper.text()).toContain('振幅 14.59%')
    expect(wrapper.text()).toContain('VCP振幅依次收缩')
  })

  it('explains that historical pre-V4.3 tasks require a rescan for VCP observations', async () => {
    api.getStrategy6Candidates.mockResolvedValue({ candidates: [{
      code: '000001', name: '旧任务样本', candidate_type: 'KEY_CANDIDATE',
      strategy_version: '4.2.0', total_score: 82,
      vcp_observation_eligible: false, vcp_lifecycle_status: 'VCP_NONE',
    }] })

    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-20260715-173615' } } } },
    })
    await flushUi()

    expect(wrapper.text()).toContain('VCP形态候选')
    expect(wrapper.text()).toContain('该任务由策略6 4.2.0生成，尚未计算VCP观察数据，请重新扫描策略6')
  })

  it('shows unknown instead of fake zero quality scores for legacy tasks', async () => {
    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()

    await wrapper.find('[data-test="candidate-row-000002"]').trigger('click')

    expect(wrapper.find('[data-test="detail-quality-v2"]').text()).toContain('--')
    expect(wrapper.find('[data-test="detail-entry-archetype"]').text()).toContain('--')
    expect(wrapper.find('[data-test="detail-quality-v2"]').text()).not.toContain('整理质量 0')
  })

  it('masks immediate-buy semantics for Brooks-only B-grade, barb-wire and untriggered candidates', async () => {
    api.getStrategy6Candidates.mockResolvedValue({
      candidates: [
        {
          code: '000010', name: 'B级等待', candidate_type: 'READY_CANDIDATE', lifecycle_status: 'BUY_ZONE',
          start_grade: 'B', buy_zone_low: 8.01, buy_zone_high: 8.18, suggestion: '立即买入',
          execution_notes: ['NEXT_TRADING_DAY_ONLY'],
          brooks_tail_enabled: true, brooks_tail_pass: true, brooks_tail_score: 15,
          brooks_tail_premium: false, brooks_status: 'SECOND_ENTRY_LONG_READY', brooks_trade_ready: true,
          brooks_trade_trigger_type: 'BROOKS_SUPPORT_READY', tail_paths: ['BROOKS'],
          tail_path_summary: 'BROOKS', tail_primary_path: 'BROOKS', passed_path_count: 1,
          multi_path_confirmed: false, tail_path: 'NONE',
          brooks_result: {
            context: { context_type: 'WEAK_BULL_CONTEXT', watch_only: true },
            compact_structure: { structure_type: 'COMPACT_ORDERLY', barb_wire_risk: false },
            structure: { setup_types: ['SECOND_ENTRY_LONG_READY'] },
            trade_trigger: { ready: true, trigger_type: 'BROOKS_SUPPORT_READY', trigger_valid_until: '2026-07-15' },
            reasons: [], reject_reasons: [], risk_tags: ['BROOKS_GRADE_B_WATCH_ONLY'],
          },
        },
        {
          code: '000012', name: '铁丝网等待', candidate_type: 'READY_CANDIDATE', lifecycle_status: 'BUY_ZONE',
          start_grade: 'A', buy_zone_low: 9.01, buy_zone_high: 9.18, suggestion: '立即买入',
          brooks_tail_enabled: true, brooks_tail_pass: true, brooks_trade_ready: true,
          brooks_trade_trigger_type: 'BROOKS_SUPPORT_READY', tail_paths: ['BROOKS'],
          tail_path_summary: 'BROOKS', tail_primary_path: 'BROOKS', tail_path: 'NONE',
          brooks_result: {
            context: { context_type: 'BULL_CONTEXT', watch_only: false },
            compact_structure: { structure_type: 'BARB_WIRE', barb_wire_risk: true },
            trade_trigger: { ready: true, trigger_type: 'BROOKS_SUPPORT_READY' },
          },
        },
        {
          code: '000013', name: '信号未触发', candidate_type: 'READY_CANDIDATE', lifecycle_status: 'BUY_ZONE',
          start_grade: 'A', buy_zone_low: 10.01, buy_zone_high: 10.18, suggestion: '立即买入',
          brooks_tail_enabled: true, brooks_tail_pass: true, brooks_trade_ready: false,
          tail_paths: ['BROOKS'], tail_path_summary: 'BROOKS', tail_primary_path: 'BROOKS', tail_path: 'NONE',
          brooks_result: { context: { context_type: 'BULL_CONTEXT' }, compact_structure: { structure_type: 'COMPACT_ORDERLY' }, trade_trigger: { ready: false } },
        },
        {
          code: '000011', name: '旧路径就绪', candidate_type: 'READY_CANDIDATE', lifecycle_status: 'BUY_ZONE',
          tail_path: 'ORIGINAL', original_tail_pass: true, buy_zone_low: 7.01, buy_zone_high: 7.18,
        },
      ],
    })

    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()

    for (const code of ['000010', '000012', '000013']) {
      expect(wrapper.find(`[data-test="candidate-buy-zone-${code}"]`).text()).toBe('等待触发')
      expect(wrapper.find(`[data-test="candidate-type-${code}"]`).text()).toBe('观察候选')
      expect(wrapper.find(`[data-test="candidate-lifecycle-${code}"]`).text()).toBe('观察/等待触发')
    }
    expect(wrapper.text()).toContain('执行区间/状态')
    expect(wrapper.text()).not.toContain('仅限下一交易日执行')
    expect(wrapper.text()).not.toContain('8.01 - 8.18')
    expect(wrapper.text()).not.toContain('9.01 - 9.18')
    expect(wrapper.text()).not.toContain('10.01 - 10.18')
    expect(wrapper.find('[data-test="detail-execution-zone"]').text()).toContain('等待触发')
    expect(wrapper.find('[data-test="detail-suggestion"]').text()).toContain('观察/等待触发')

    await wrapper.find('[data-test="candidate-row-000011"]').trigger('click')
    expect(wrapper.find('[data-test="candidate-buy-zone-000011"]').text()).toContain('7.01 - 7.18')
    expect(wrapper.find('[data-test="detail-execution-zone"]').text()).toContain('7.01 - 7.18')
    expect(wrapper.text()).toContain('未启用或旧任务无数据')
    expect(wrapper.text()).not.toContain('undefined')
  })

  it('prefers authoritative production Brooks trigger prices and only falls back for legacy tasks', async () => {
    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: {} } } },
    })

    expect(wrapper.vm.brooksTriggerPrice({
      brooks_trigger_price: 10.31,
      brooks_result: {
        trade_trigger: { trigger_type: 'BROOKS_FAILED_BREAKOUT_READY', trigger_price: 10.21 },
        structure: { second_entry_trigger_price: 9.99 },
      },
    })).toBe(10.31)
    expect(wrapper.vm.brooksTriggerPrice({
      brooks_result: {
        trade_trigger: { trigger_type: 'BROOKS_FAILED_BREAKOUT_READY', trigger_price: 11.22 },
        structure: { second_entry_trigger_price: 9.99 },
      },
    })).toBe(11.22)
    expect(wrapper.vm.brooksTriggerPrice({
      brooks_result: {
        trade_trigger: { trigger_type: 'BROOKS_SUPPORT_READY' },
        structure: { second_entry_trigger_price: 9.99 },
      },
    })).toBe(9.99)
    expect(wrapper.vm.brooksTriggerValidUntil({
      brooks_trigger_valid_until: '2026-07-20',
      brooks_result: { trade_trigger: { trigger_valid_until: '2026-07-19' } },
    })).toBe('2026-07-20')
  })

  it('loads all candidates for a URL task even when task list is stale', async () => {
    api.getStrategy6Tasks.mockResolvedValue({ tasks: [{ id: 's6-other', status: 'completed', candidates: 1 }] })
    const candidates = Array.from({ length: 9 }, (_, idx) => ({
      code: `300${String(idx).padStart(3, '0')}`,
      name: `强VCP${idx}`,
      candidate_type: idx < 2 ? 'READY_CANDIDATE' : idx < 6 ? 'KEY_CANDIDATE' : 'WATCH_CANDIDATE',
      classification: idx < 2 ? 'ready' : idx < 6 ? 'key' : 'watch',
      lifecycle_status: 'READY',
      total_score: 90 - idx,
      start_type: 'VOLUME_LIMIT_UP',
      start_grade: 'A',
      support_status: 'MA20_SUPPORT',
      key_support_price: 10 + idx,
      risk_reward_ratio_2: 2.5,
    }))
    api.getStrategy6Candidates.mockResolvedValue({ candidates })

    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-20260709-001' } },
        },
      },
    })
    await flushUi()

    expect(api.getStrategy6Candidates).toHaveBeenCalledWith('s6-20260709-001')
    expect(api.getStrategy6MarketSnapshot).toHaveBeenCalledWith('s6-20260709-001')
    expect(wrapper.text()).toContain('候选数 9')
    expect(wrapper.text()).toContain('就绪 2')
    expect(wrapper.text()).toContain('重点 4')
    expect(wrapper.text()).toContain('观察 3')
    expect(wrapper.findAll('.candidate-table tbody tr')).toHaveLength(9)
  })

  it('keeps candidates visible when only the market snapshot fails', async () => {
    api.getStrategy6MarketSnapshot.mockRejectedValue(new Error('snapshot unavailable'))

    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()

    expect(wrapper.text()).toContain('就绪候选')
    expect(wrapper.findAll('.candidate-table tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('市场指数快照加载失败')
    expect(wrapper.text()).not.toContain('策略6候选加载失败')
  })

  it('translates incomplete market snapshot reasons', async () => {
    api.getStrategy6MarketSnapshot.mockResolvedValue({
      snapshot: {
        market_status: 'UNKNOWN',
        market_reasons: ['MARKET_DATA_PARTIAL', 'observed_indexes=1'],
        indexes: [],
      },
    })

    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()

    expect(wrapper.text()).toContain('市场指数数据不完整')
    expect(wrapper.text()).toContain('有效指数数量=1')
    expect(wrapper.text()).not.toContain('MARKET_DATA_PARTIAL')
    expect(wrapper.text()).not.toContain('observed_indexes=1')
  })

  it('exports strategy6 candidates with market, lifecycle and trade plan fields', async () => {
    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-task' } },
        },
      },
    })
    await flushUi()
    const mocks = installDownloadMocks()

    const button = wrapper.find('[data-test="export-candidates"]')
    expect(button.exists()).toBe(true)
    await button.trigger('click')

    expect(mocks.click).toHaveBeenCalled()
    const blob = mocks.createObjectURL.mock.calls[0][0]
    const csv = await blob.text()
    expect(csv).toContain('代码,名称,板块,候选类型,候选类型原始值,生命周期,生命周期原始值,首次入池,池龄交易日')
    expect(csv).toContain('市场状态,市场状态原始值,RS20')
    expect(csv).not.toContain('板块状态')
    expect(csv).not.toContain('板块RS10')
    expect(csv).toContain('启动日低点,启动后天数')
    expect(csv).toContain('关键支撑,前置支撑')
    expect(csv).toContain('阶段状态,阶段状态原始值,形态类型,形态类型原始值')
    expect(csv).toContain('评分模型版本,入场类型,入场类型原始值,启动事件质量分,整理质量分,支撑反应分,路径证据分')
    expect(csv).toContain('尾段划分,尾段划分原始值,尾段划分分数')
    expect(csv).toContain('S6_QUALITY_V2,支撑低吸,SUPPORT_PULLBACK,17,21,8,13')
    expect(csv).toContain('客观目标1,客观目标2,客观RR1,客观RR2')
    expect(csv).toContain('权威路径汇总,权威路径汇总原始值,主路径,主路径原始值,通过路径')
    expect(csv).toContain('Brooks状态,Brooks状态原始值,Brooks交易状态,Brooks触发类型,Brooks触发类型原始值')
    expect(csv).toContain('多路径,MULTI,Brooks价格行为,BROOKS')
    expect(csv).toContain('2,是,是,是,19,是,支撑位触发确认,BROOKS_SUPPORT_READY,交易触发已确认,二次入场突破触发,BROOKS_SUPPORT_READY')
    expect(csv).toContain('稳定箱体路径|Brooks价格行为')
    expect(csv).toContain('BOX|BROOKS')
    expect(csv).toContain('上涨背景,卖压衰竭,价格稳定,量能萎缩,支撑未破')
    expect(csv).toContain('2026-07-14,通过,通过,通过,通过,通过,上涨背景,BULL_CONTEXT')
    expect(csv).toContain('1.5R目标,2R目标,2.5R目标,3.5R目标')
    expect(csv).toContain('000001,平安银行,,就绪候选,READY_CANDIDATE,买入区间,BUY_ZONE,2026-07-01,6')
    expect(csv).toContain('降级处理,downgrade,市场偏弱,MARKET_WEAK,18.00%,12.34')
    expect(csv).toContain('接近120日压力位,NEAR_120D_PRESSURE')
    expect(csv).toContain('VCP观察资格,VCP状态,VCP状态原始值,VCP起点,VCP形态开始,VCP形态结束,VCP收缩次数')
    expect(csv).toContain('VCP支点,VCP结构低点,距VCP支点,VCP突破日期,VCP突破后天数')
  })

  it('exports Brooks-only waiting candidates without READY or immediate-buy semantics', async () => {
    api.getStrategy6Candidates.mockResolvedValue({ candidates: [
      {
        code: '000021', name: 'Brooks等待', candidate_type: 'READY_CANDIDATE',
        lifecycle_status: 'READY', start_grade: 'B', tail_paths: ['BROOKS'],
        brooks_tail_pass: true, brooks_trade_ready: true,
        suggested_buy_price: 10.10, buy_zone_low: 10.01, buy_zone_high: 10.18,
        suggestion: '低吸候选',
      },
      {
        code: '000023', name: 'Brooks密集区', candidate_type: 'READY_CANDIDATE',
        lifecycle_status: 'READY', start_grade: 'A', tail_paths: ['BROOKS'],
        brooks_tail_pass: true, brooks_trade_ready: true,
        brooks_result: { compact_structure: { structure_type: 'BARB_WIRE' } },
        suggested_buy_price: 11.10, buy_zone_low: 11.01, buy_zone_high: 11.18,
        suggestion: '低吸候选',
      },
      {
        code: '000024', name: 'Brooks未触发', candidate_type: 'READY_CANDIDATE',
        lifecycle_status: 'READY', start_grade: 'A', tail_paths: ['BROOKS'],
        brooks_tail_pass: true, brooks_trade_ready: false,
        suggested_buy_price: 12.10, buy_zone_low: 12.01, buy_zone_high: 12.18,
        suggestion: '低吸候选',
      },
      {
        code: '000022', name: '原路径就绪', candidate_type: 'READY_CANDIDATE',
        lifecycle_status: 'READY', tail_paths: ['ORIGINAL'], original_tail_pass: true,
        suggested_buy_price: 8.10, buy_zone_low: 8.01, buy_zone_high: 8.18,
      },
    ] })
    const wrapper = mount(Strategy6Results, {
      global: { mocks: { $route: { query: { task: 's6-task' } } } },
    })
    await flushUi()
    const mocks = installDownloadMocks()

    await wrapper.find('[data-test="export-candidates"]').trigger('click')

    const csv = await mocks.createObjectURL.mock.calls[0][0].text()
    const rows = csv.split('\n')
    const waitingRows = ['000021', '000023', '000024'].map(code => rows.find(row => row.startsWith(`${code},`)))
    const legacyRow = csv.split('\n').find(row => row.startsWith('000022,'))
    for (const waitingRow of waitingRows) {
      expect(waitingRow).toContain('观察候选,WATCH_CANDIDATE,观察/等待触发,SETUP_FORMING')
      expect(waitingRow).not.toContain('READY')
      expect(waitingRow).not.toContain('WAIT_TRIGGER')
      expect(waitingRow).not.toContain('低吸候选')
      expect(waitingRow).not.toMatch(/10\.01|10\.18|11\.01|11\.18|12\.01|12\.18/)
      expect(waitingRow).toMatch(/观察\/等待触发,[^,]*$/)
    }
    expect(legacyRow).toContain('就绪候选,READY_CANDIDATE')
    expect(legacyRow).toContain('8.10,8.01,8.18')
  })

  it('exports strategy6 daily report as excel from backend report endpoint', async () => {
    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-task' } },
        },
      },
    })
    await flushUi()
    const mocks = installDownloadMocks()

    const button = wrapper.find('[data-test="export-excel-report"]')
    expect(button.exists()).toBe(true)
    await button.trigger('click')

    expect(api.downloadStrategy6Report).toHaveBeenCalledWith('s6-task')
    expect(mocks.click).toHaveBeenCalled()
    const anchor = document.createElement.mock.results.find(result => result.value.tagName === 'A').value
    expect(anchor.download).toBe('strategy6-report-s6-task.xlsx')
    const blob = mocks.createObjectURL.mock.calls[0][0]
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
  })
})
