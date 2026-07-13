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
    expect(wrapper.text()).toContain('READY_CANDIDATE')
    expect(wrapper.text()).toContain('KEY_CANDIDATE')
    expect(wrapper.text()).toContain('WATCH_CANDIDATE')
    expect(wrapper.text()).toContain('VOLUME_LIMIT_UP / S')
    expect(wrapper.text()).toContain('MA10_SUPPORT')
    expect(wrapper.text()).toContain('11.80 / 11.60')
    expect(wrapper.text()).toContain('启动后5日')
    expect(wrapper.text()).toContain('启动日低点')
    expect(wrapper.text()).toContain('11.80 - 12.20')
    expect(wrapper.text()).toContain('止损')
    expect(wrapper.text()).toContain('RR2')
    expect(wrapper.text()).toContain('3.40')
    expect(wrapper.text()).toContain('BUY_ZONE')
    expect(wrapper.text()).toContain('MARKET_WEAK')
    expect(wrapper.text()).toContain('RS20 18.00%')
    expect(wrapper.text()).toContain('市场过滤数据')
    expect(wrapper.text()).toContain('上证指数')
    expect(wrapper.text()).toContain('3200.50')
    expect(wrapper.text()).toContain('MA20')
    expect(wrapper.text()).toContain('数据状态')
    expect(wrapper.text()).toContain('新鲜')
    expect(wrapper.text()).toContain('sina')
    expect(wrapper.text()).toContain('2026-07-09 15:20:00')
    expect(wrapper.text()).not.toContain('板块过滤')
    expect(wrapper.text()).toContain('首次入池 2026-07-01')
    expect(wrapper.text()).toContain('池龄 6日')
    expect(wrapper.text()).toContain('NEAR_120D_PRESSURE')
    expect(wrapper.text()).toContain('VCP')
    expect(wrapper.text()).toContain('客观目标')
    expect(wrapper.text()).toContain('执行R目标')
    expect(wrapper.text()).toContain('尾部路径')
    expect(wrapper.text()).toContain('BOX')
    expect(wrapper.text()).toContain('BOX_SUPPORT_READY')
    expect(wrapper.text()).toContain('BOX_COMPACT_READY')
    expect(wrapper.text()).toContain('11.80 - 12.50')
    expect(wrapper.text()).toContain('下沿测试2次')
    expect(wrapper.text()).toContain('紧密排列')
    expect(wrapper.text()).toContain('未形成尾段（V5/V20 0.660）')
    expect(wrapper.vm.tailVolumeDisplay({
      tail_avg_volume: 0,
      pre_tail_avg_volume_20: 0,
      tail_volume_ratio: 0,
      volume_ratio_5_20: null,
    })).toBe('未形成尾段')
    expect(wrapper.text()).toContain('2026-07-10 至 2026-07-14')
    expect(wrapper.text()).toContain('NEXT_TRADING_DAY_ONLY')
    expect(wrapper.text()).toContain('4.0.0')
    expect(api.getStrategy6Lifecycle).toHaveBeenCalledWith('s6-task')
    expect(wrapper.text()).toContain('生命周期退出/冷却审计')
    expect(wrapper.text()).toContain('退出样本')
    expect(wrapper.text()).toContain('SUPPORT_FAILED')
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

    expect(wrapper.text()).toContain('READY_CANDIDATE')
    expect(wrapper.findAll('.candidate-table tbody tr')).toHaveLength(3)
    expect(wrapper.text()).toContain('市场指数快照加载失败')
    expect(wrapper.text()).not.toContain('策略6候选加载失败')
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
    expect(csv).toContain('代码,名称,板块,候选类型,生命周期,首次入池,池龄交易日')
    expect(csv).toContain('市场状态,RS20')
    expect(csv).not.toContain('板块状态')
    expect(csv).not.toContain('板块RS10')
    expect(csv).toContain('启动日低点,启动后天数')
    expect(csv).toContain('Key支撑,前置支撑')
    expect(csv).toContain('策略版本,阶段状态,形态类型')
    expect(csv).toContain('客观目标1,客观目标2,客观RR1,客观RR2')
    expect(csv).toContain('1.5R目标,2R目标,2.5R目标,3.5R目标')
    expect(csv).toContain('000001,平安银行,,READY_CANDIDATE,BUY_ZONE,2026-07-01,6')
    expect(csv).toContain('downgrade,MARKET_WEAK,18.00%,12.34')
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
