import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getKlineHistory: vi.fn(),
  analyzeCleanK: vi.fn(),
  getKlineHealth: vi.fn(),
  refreshKlineData: vi.fn(),
  refreshKlineHealth: vi.fn(),
  startTickFlowFullRefresh: vi.fn(),
  getTickFlowFullRefreshStatus: vi.fn(),
  checkTickFlowFreshness: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import KlineHistory from '../KlineHistory.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function freshResponse(overrides = {}) {
  return {
    code: '000831',
    rows: [{ date: '2026-06-16', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, turnover: 10500 }],
    total: 1,
    page: 1,
    page_size: 50,
    summary: {
      latest_kline_date: '2026-06-16',
      latest_fetch_time: '2026-06-16 15:12:00',
      target_trade_date: '2026-06-16',
      min_fetch_time: '2026-06-16 15:00:00',
      is_fresh: true,
      needs_refetch: false,
      quote_status: 'not_requested',
      reason: '数据已覆盖目标完整交易日',
      ...(overrides.summary || {}),
    },
    ...overrides,
  }
}

function healthResponse(overrides = {}) {
  return {
    summary: {
      target_trade_date: '2026-06-16',
      min_fetch_time: '2026-06-16 15:00:00',
      total: 4,
      fresh: 1,
      no_trade: 1,
      anomaly: 2,
      failed: 1,
      needs_refetch: 2,
    },
    items: [
      {
        code: '000002',
        name: '停牌股份',
        latest_kline_date: '2026-06-15',
        latest_fetch_time: '2026-06-16 15:12:00',
        target_trade_date: '2026-06-16',
        health_status: 'no_trade',
        severity: 'warning',
        needs_refetch: false,
        reason: '股票停牌或无交易，已在目标交易日收盘后确认',
      },
      {
        code: '000003',
        name: '异常股份',
        latest_kline_date: '2026-06-16',
        latest_fetch_time: '2026-06-16 15:12:00',
        target_trade_date: '2026-06-16',
        health_status: 'anomaly',
        severity: 'danger',
        needs_refetch: true,
        reason: '目标交易日存在零成交量平盘K线，需要重新拉取确认',
      },
    ],
    total: 2,
    page: 1,
    page_size: 100,
    ...overrides,
  }
}

describe('KlineHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getKlineHistory.mockResolvedValue(freshResponse())
    api.analyzeCleanK.mockResolvedValue({
      ok: true,
      stockCode: '300888', period: 20,
      startDate: '2026-07-17', endDate: '2026-08-13',
      targetTradeDate: '2026-08-13', latestDataDate: '2026-08-13', dataIsFresh: true,
      isClean: true, cleanKScore: 82.6, cleanLevel: 'CLEAN',
      modelVersion: 'CLEAN_K_V2',
      structureMode: 'BASE_TO_TREND', trendDirection: 'UP', structureScore: 89.3,
      window: {
        isClean: true, score: 82.6, level: 'CLEAN', structure: 'BASE_TO_TREND',
        structureScore: 89.3, direction: 'UP', startDate: '2026-07-17', endDate: '2026-08-13',
      },
      current: {
        isClean: true, score: 88.4, level: 'EXTREMELY_CLEAN', days: 8,
        evaluatedDays: 8, structure: 'TREND_UP', structureScore: 92.1, direction: 'UP',
        startDate: '2026-08-04', endDate: '2026-08-13',
      },
      barStats: {
        directionalExpansionCount: 2, conflictExpansionCount: 1,
        gapReversalExpansionCount: 0, microRangeCount: 2,
        eventBarCount: 0, dirtyExtremeCount: 1,
      },
      segments: [
        { startDate: '2026-07-17', endDate: '2026-07-30', days: 10, structureType: 'BASE', structureScore: 84.2 },
        { startDate: '2026-07-31', endDate: '2026-08-13', days: 10, structureType: 'TREND_UP', structureScore: 92.5 },
      ],
      transitions: ['BASE_TO_TREND'],
      avgBarCleanScore: 84.1, sequenceCleanScore: 82.2,
      trendCleanScore: 72.4, baseCleanScore: 78.6, contractionCleanScore: 89.3,
      rangeRhythmScore: 86.5, extremeControlScore: 91,
      dirtyExtremeCount: 1, eventBarCount: 0, suspendedCount: 0,
      evaluatedBarCount: 20, warmupBarCount: 40, confidence: 0.91,
      reasons: ['最近20日主要表现为有序收缩', '后段日内振幅明显收缩'],
      riskFlags: [],
      barMetrics: [{
        tradeDate: '2026-08-13', atr14Prev: 2.1, intradayRangeAtr: 0.6,
        trueRangeAtr: 0.7, bodyRatio: 0.45, upperWickRatio: 0.2,
        lowerWickRatio: 0.35, barCleanScore: 86.2,
        barStructureType: 'NORMAL_BAR', dirtyExtremeBar: false, eventBar: false,
      }],
    })
    api.getKlineHealth.mockResolvedValue(healthResponse())
    api.refreshKlineData.mockResolvedValue({ ok: true, summary: { health_status: 'fresh' } })
    api.refreshKlineHealth.mockResolvedValue({
      ok: true,
      requested_count: 1,
      succeeded_count: 1,
      failed_count: 0,
      skipped_count: 1,
    })
    api.startTickFlowFullRefresh.mockResolvedValue({
      ok: true,
      task_id: 'tickflow-web-20260721-120000-abc123',
      running: true,
      status: 'running',
      total_stocks: 5000,
      processed: 0,
      succeeded: 0,
      failed: 0,
      parameters: {
        history_days: 1100,
        chunk_size: 100,
        batch_size: 100,
        max_workers: 5,
        adjustment: 'forward_additive',
      },
    })
    api.getTickFlowFullRefreshStatus.mockResolvedValue({
      running: false,
      status: 'idle',
      total_stocks: 0,
      processed: 0,
      succeeded: 0,
      failed: 0,
      parameters: {
        history_days: 1100,
        chunk_size: 100,
        batch_size: 100,
        max_workers: 5,
        adjustment: 'forward_additive',
      },
    })
    api.checkTickFlowFreshness.mockResolvedValue({
      ok: true,
      checked_at: '2026-07-23T16:00:01',
      target_trade_date: '2026-07-23',
      overall_status: 'PARTIAL_FAILURE',
      stock: {
        code: '000655', name: '金岭矿业', remote_latest_date: '2026-07-23',
        local_latest_date: '2026-07-22', target_trade_date: '2026-07-23',
        status: 'FRESH', row_count: 5, elapsed_ms: 120, error: null,
      },
      indexes: [
        { code: 'sh000001', name: '上证指数', remote_latest_date: '2026-07-23', local_latest_date: '2026-07-22', target_trade_date: '2026-07-23', status: 'FRESH', row_count: 5, elapsed_ms: 80, error: null },
        { code: 'sz399001', name: '深证成指', remote_latest_date: '2026-07-22', local_latest_date: '2026-07-22', target_trade_date: '2026-07-23', status: 'STALE', row_count: 5, elapsed_ms: 80, error: null },
        { code: 'sz399006', name: '创业板指', remote_latest_date: null, local_latest_date: '2026-07-22', target_trade_date: '2026-07-23', status: 'FAILED', row_count: 0, elapsed_ms: 80, error: 'request failed' },
        { code: 'hs300', name: '沪深300', remote_latest_date: '2026-07-23', local_latest_date: '2026-07-22', target_trade_date: '2026-07-23', status: 'FRESH', row_count: 5, elapsed_ms: 80, error: null },
      ],
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
  })

  it('renders freshness summary and kline rows', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(api.getKlineHistory).toHaveBeenCalledWith({
      code: '000831',
      start_date: '',
      end_date: '',
      page: 1,
      page_size: 50,
    })
    expect(wrapper.text()).toContain('个股 K 线数据诊断')
    expect(wrapper.text()).toContain('数据最新')
    expect(wrapper.text()).toContain('最新K线日期')
    expect(wrapper.text()).toContain('2026-06-16')
    expect(wrapper.text()).toContain('10.50')
  })

  it('renders market-wide data health cards and problem list', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(api.getKlineHealth).toHaveBeenCalledWith({ status: 'problem', page: 1, page_size: 100 })
    expect(wrapper.text()).toContain('全市场数据健康')
    expect(wrapper.text()).toContain('目标完整交易日')
    expect(wrapper.text()).toContain('1 / 4')
    expect(wrapper.text()).toContain('停牌股份')
    expect(wrapper.text()).toContain('异常股份')
    expect(wrapper.text()).toContain('零成交量平盘K线')
  })

  it('renders stock code as a baidu search link', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    const link = wrapper.find('[data-test="stock-search-000003"]')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('https://www.baidu.com/s?ie=UTF-8&wd=000003')
    expect(link.attributes('target')).toBe('_blank')
  })

  it('loads a stock query from a health problem row', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="inspect-health-row-000003"]').trigger('click')
    await flushUi()

    expect(api.getKlineHistory).toHaveBeenLastCalledWith({
      code: '000003',
      start_date: '',
      end_date: '',
      page: 1,
      page_size: 50,
    })
  })

  it('loads failed-only health problems from the failed summary card', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    const failedCard = wrapper.findAll('button').find((button) => button.text().includes('拉取失败'))
    await failedCard.trigger('click')
    await flushUi()

    expect(api.getKlineHealth).toHaveBeenLastCalledWith({ status: 'failed', page: 1, page_size: 100 })
  })

  it('refreshes one problematic stock from the health row', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="refresh-health-row-000003"]').trigger('click')
    await flushUi()

    expect(api.refreshKlineData).toHaveBeenCalledWith('000003')
    expect(api.getKlineHealth).toHaveBeenLastCalledWith({ status: 'problem', page: 1, page_size: 100 })
    expect(api.getKlineHistory).toHaveBeenLastCalledWith({
      code: '000003',
      start_date: '',
      end_date: '',
      page: 1,
      page_size: 50,
    })
  })

  it('bulk refreshes all refetchable stocks in the current health filter', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="bulk-refresh-health"]').trigger('click')
    await flushUi()

    expect(api.refreshKlineHealth).toHaveBeenCalledWith({ status: 'problem' })
    expect(wrapper.text()).toContain('批量重拉完成：成功 1，失败 0，跳过 1')
    expect(api.getKlineHealth).toHaveBeenLastCalledWith({ status: 'problem', page: 1, page_size: 100 })
  })

  it('analyzes clean K-line structure with stock code and period', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-code"]').setValue('300888')
    await wrapper.find('[data-test="clean-k-period"]').setValue(20)
    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(api.analyzeCleanK).toHaveBeenCalledWith({ stockCode: '300888', period: 20 })
    expect(wrapper.text()).toContain('干净K线分析')
    expect(wrapper.text()).toContain('走势干净')
    expect(wrapper.text()).toContain('82.60')
    expect(wrapper.text()).toContain('最近20日整体干净度')
    expect(wrapper.text()).toContain('当前走势干净度')
    expect(wrapper.text()).toContain('平台 → 上涨趋势')
    expect(wrapper.text()).toContain('连续 8 个交易日')
    expect(wrapper.text()).toContain('方向型扩张 2')
    expect(wrapper.text()).toContain('上涨')
    expect(wrapper.text()).toContain('2026-07-17 至 2026-08-13')
    expect(wrapper.text()).toContain('最近20日主要表现为有序收缩')
    expect(wrapper.text()).toContain('逐根K线诊断')
    expect(wrapper.text()).toContain('普通K线')
  })

  it('rejects invalid clean K-line input without calling the API', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-code"]').setValue('30088')
    await wrapper.find('[data-test="clean-k-period"]').setValue(9)
    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(api.analyzeCleanK).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请输入6位股票代码')
  })

  it('makes clean downtrends explicit instead of presenting them as bullish', async () => {
    api.analyzeCleanK.mockResolvedValue({
      ...await api.analyzeCleanK(),
      ok: true,
      isClean: true,
      structureMode: 'TREND',
      trendDirection: 'DOWN',
      riskFlags: ['CLEAN_DOWNTREND'],
    })
    api.analyzeCleanK.mockClear()
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('下跌')
    expect(wrapper.text()).toContain('K线路径干净，但属于有序下跌')
  })

  it('does not call an unclean downward path clean', async () => {
    const base = await api.analyzeCleanK()
    api.analyzeCleanK.mockResolvedValue({
      ...base,
      ok: true,
      isClean: false,
      structureMode: 'BASE',
      trendDirection: 'DOWN',
      riskFlags: [],
    })
    api.analyzeCleanK.mockClear()
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('价格方向向下，且当前未通过干净度门槛')
    expect(wrapper.text()).not.toContain('K线路径干净，但属于有序下跌')
  })

  it('explains why a high-scoring V2 window still fails its hard gates', async () => {
    const base = await api.analyzeCleanK()
    api.analyzeCleanK.mockResolvedValue({
      ...base,
      ok: true,
      isClean: false,
      cleanKScore: 83.79,
      window: {
        ...base.window,
        isClean: false,
        score: 83.79,
        blockingReasons: ['TOO_MANY_CONFLICT_BARS'],
      },
      current: {
        ...base.current,
        isClean: false,
        days: 0,
        blockingReasons: ['NO_CONFIRMED_CURRENT_BOUNDARY'],
      },
    })
    api.analyzeCleanK.mockClear()
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('83.79')
    expect(wrapper.text()).toContain('冲突型K线超过容忍线')
    expect(wrapper.text()).toContain('未确认当前结构切换边界')
  })

  it('shows a truthful V1 compatibility result when the backend has not reloaded V2', async () => {
    api.analyzeCleanK.mockResolvedValue({
      ok: true,
      stockCode: '300604', period: 20,
      startDate: '2026-07-16', endDate: '2026-08-12',
      targetTradeDate: '2026-08-13', latestDataDate: '2026-08-12', dataIsFresh: false,
      isClean: true, cleanKScore: 83.22, cleanLevel: 'CLEAN',
      structureMode: 'CONTRACTION', trendDirection: 'DOWN', structureScore: 78.13,
      trendCleanScore: 0, baseCleanScore: 60.37, contractionCleanScore: 78.13,
      rangeRhythmScore: 91.65, dirtyExtremeCount: 1,
      eventBarCount: 0, suspendedCount: 0, confidence: 1,
      reasons: ['最近20日主要表现为有序收缩'], riskFlags: ['STALE_LOCAL_DATA'],
      barMetrics: [],
    })
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('走势干净')
    expect(wrapper.text()).toContain('83.22')
    expect(wrapper.text()).toContain('有序收缩')
    expect(wrapper.text()).toContain('后端仍在运行V1，请重启后端以加载V2当前走势分析')
    expect(wrapper.text()).not.toContain('当前尚未形成干净结构')
  })

  it('explains when an incomplete target-date bar was excluded', async () => {
    const base = await api.analyzeCleanK()
    api.analyzeCleanK.mockResolvedValue({
      ...base,
      ok: true,
      dataIsFresh: false,
      targetTradeDate: '2026-08-13',
      latestDataDate: '2026-08-12',
      excludedIncompleteDate: '2026-08-13',
      riskFlags: ['INCOMPLETE_TARGET_BAR_EXCLUDED'],
    })
    api.analyzeCleanK.mockClear()
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="clean-k-analyze"]').trigger('click')
    await flushUi()

    expect(wrapper.text()).toContain('目标日K线在收盘前拉取，已从分析中排除')
  })

  it('checks remote TickFlow freshness for one stock and four indexes', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="tickflow-probe-code"]').setValue('000655')
    await wrapper.find('[data-test="tickflow-freshness-check"]').trigger('click')
    await flushUi()

    expect(api.checkTickFlowFreshness).toHaveBeenCalledWith('000655')
    expect(wrapper.text()).toContain('TickFlow 数据新鲜度测试')
    expect(wrapper.text()).toContain('金岭矿业')
    expect(wrapper.text()).toContain('上证指数')
    expect(wrapper.text()).toContain('深证成指')
    expect(wrapper.text()).toContain('创业板指')
    expect(wrapper.text()).toContain('沪深300')
    expect(wrapper.text()).toContain('最新')
    expect(wrapper.text()).toContain('落后')
    expect(wrapper.text()).toContain('请求失败')
    expect(wrapper.text()).toContain('2026-07-23')
    expect(api.getKlineHistory).toHaveBeenLastCalledWith(expect.objectContaining({ code: '000831' }))
  })

  it('rejects an invalid TickFlow probe code without calling the API', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="tickflow-probe-code"]').setValue('12345')
    await wrapper.find('[data-test="tickflow-freshness-check"]').trigger('click')
    await flushUi()

    expect(api.checkTickFlowFreshness).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请输入6位股票代码')
  })

  it('shows fixed TickFlow full refresh parameters and recovers running progress', async () => {
    api.getTickFlowFullRefreshStatus.mockResolvedValue({
      running: true,
      status: 'running',
      task_id: 'tickflow-web-running',
      total_stocks: 5000,
      processed: 230,
      succeeded: 228,
      failed: 2,
      current_chunk: 3,
      total_chunks: 50,
      total_indexes: 4,
      indexes_processed: 4,
      indexes_failed: 0,
      parameters: {
        history_days: 1100,
        chunk_size: 100,
        batch_size: 100,
        max_workers: 5,
        adjustment: 'forward_additive',
      },
    })

    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(api.getTickFlowFullRefreshStatus).toHaveBeenCalled()
    expect(wrapper.text()).toContain('TickFlow 全市场重新拉取')
    expect(wrapper.text()).toContain('前复权')
    expect(wrapper.text()).toContain('1100 根')
    expect(wrapper.text()).toContain('230 / 5000')
    expect(wrapper.text()).toContain('成功 228，失败 2')
    expect(wrapper.text()).toContain('指数 4 / 4，失败 0')
    expect(wrapper.find('[data-test="tickflow-full-refresh"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('starts a confirmed TickFlow full-market refresh', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="tickflow-full-refresh"]').trigger('click')
    await flushUi()

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('整个股票池'))
    expect(api.startTickFlowFullRefresh).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('0 / 5000')
    wrapper.unmount()
  })

  it('does not start TickFlow refresh when confirmation is canceled', async () => {
    window.confirm.mockReturnValue(false)
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="tickflow-full-refresh"]').trigger('click')

    expect(api.startTickFlowFullRefresh).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('polls to terminal TickFlow status, shows report path, and refreshes health', async () => {
    vi.useFakeTimers()
    api.getTickFlowFullRefreshStatus
      .mockResolvedValueOnce({ running: false, status: 'idle' })
      .mockResolvedValueOnce({
        running: false,
        status: 'completed_with_errors',
        task_id: 'tickflow-web-terminal',
        total_stocks: 5000,
        processed: 5000,
        succeeded: 4997,
        failed: 3,
        report_path: 'data/tickflow/reports/tickflow-web-terminal.md',
        failures: [{ code: '000001', error: 'missing response' }],
      })
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="tickflow-full-refresh"]').trigger('click')
    await flushUi()
    await vi.advanceTimersByTimeAsync(2000)
    await flushUi()

    expect(wrapper.text()).toContain('全量重拉完成，但有失败股票')
    expect(wrapper.text()).toContain('4997，失败 3')
    expect(wrapper.text()).toContain('data/tickflow/reports/tickflow-web-terminal.md')
    expect(wrapper.text()).toContain('000001：missing response')
    expect(api.getKlineHealth).toHaveBeenCalledTimes(2)
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('loads the next page with the current query', async () => {
    api.getKlineHistory
      .mockResolvedValueOnce(freshResponse({ total: 100, page: 1, page_size: 50 }))
      .mockResolvedValueOnce(freshResponse({
        rows: [{ date: '2026-06-15', open: 9, high: 10, low: 8, close: 9.5, volume: 2000, turnover: 19000 }],
        total: 100,
        page: 2,
        page_size: 50,
      }))
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="next-page"]').trigger('click')
    await flushUi()

    expect(api.getKlineHistory).toHaveBeenLastCalledWith({
      code: '000831',
      start_date: '',
      end_date: '',
      page: 2,
      page_size: 50,
    })
    expect(wrapper.text()).toContain('2026-06-15')
    expect(wrapper.text()).toContain('9.50')
  })

  it('shows refetch warning when data is stale', async () => {
    api.getKlineHistory.mockResolvedValue(freshResponse({
      summary: {
        is_fresh: false,
        needs_refetch: true,
        reason: '最近拉取时间早于目标交易日收盘时间，需要重新拉取',
      },
    }))

    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(wrapper.text()).toContain('需要重新拉取')
    expect(wrapper.text()).toContain('最近拉取时间早于目标交易日收盘时间')
  })
})
