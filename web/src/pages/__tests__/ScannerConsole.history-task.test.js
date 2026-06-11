import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

async function flushUi() {
  await Promise.resolve(); await nextTick(); await Promise.resolve(); await nextTick()
}

const ScanEngineStub = {
  props: ['running', 'scanned', 'total', 'skipped', 'failed', 'candidates', 'latestTradeDate', 'stockPoolSource'],
  template: `<div data-test="scan-summary">running={{ running }} processed={{ scanned }} total={{ total }} skipped={{ skipped }} failed={{ failed }} candidates={{ candidates }} latest={{ latestTradeDate }} source={{ stockPoolSource }}</div>`,
}

const mockRoute = reactive({ query: {}, path: '/' })
const mockRouter = { push: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({ useRoute: () => mockRoute, useRouter: () => mockRouter }))

const mockApi = {
  startScan: vi.fn(), startStrategy2Scan: vi.fn(), getScanStatus: vi.fn(),
  getCandidates: vi.fn(), getTaskStocks: vi.fn(), retryFailedStocks: vi.fn(),
  getStrategy2Candidates: vi.fn(), getScanTasks: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => mockApi }))

import ScannerConsole from '../ScannerConsole.vue'

function defaults() {
  mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
  mockApi.getTaskStocks.mockResolvedValue({ ok: true, stocks: [], total: 0, strategy_type: null, summary: {} })
  mockApi.getCandidates.mockResolvedValue({ candidates: [], total: 0 })
  mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [], total: 0 })
  mockApi.getScanTasks.mockResolvedValue({ tasks: [] })
}

function mountPage() {
  return mount(ScannerConsole, { global: { stubs: { ScanEngine: ScanEngineStub, 'router-link': true, 'router-view': true } } })
}

describe('ScannerConsole history task context', () => {
  let wrapper

  beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); mockRoute.query = {}; defaults() })
  afterEach(() => { vi.useRealTimers(); if (wrapper) wrapper.unmount(); wrapper = null })

  // ── basic isolation ──
  it('current S1 does not overwrite historical S2', async () => {
    mockRoute.query = { task: 's2-historical' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 10, processed: 10, failed: 3, candidate: 2, scanned: 5, skipped: 0 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-running', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 500, total_stocks: 5000 } })
    wrapper = mountPage(); await flushUi()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-historical', expect.any(Object))
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalledWith('s2-historical')
  })

  it('current S2 does not overwrite historical S1', async () => {
    mockRoute.query = { task: 's1-historical' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 5, processed: 5, failed: 0 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-running', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 100, total_stocks: 5000 } })
    wrapper = mountPage(); await flushUi()
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 's1-historical' })
  })

  it('historical S2 hides retry button', async () => {
    mockRoute.query = { task: 's2-done' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000002', name: 'fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 1, processed: 1, failed: 1 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).not.toContain('重新拉取')
  })

  it('unknown task shows 任务不存在', async () => {
    mockRoute.query = { task: 'not-found' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('任务不存在')
  })

  it('non-404 shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'err' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 500, error: 'INTERNAL' })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })

  it('network rejection shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'net' }
    mockApi.getTaskStocks.mockRejectedValue(new Error('Network'))
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })

  // ── ROUND7-S2-003: precise summary assertions ──
  it('completed historical task applies persisted summary with precise values', async () => {
    mockRoute.query = { task: 's2-completed' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 2, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'f1', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 100, processed: 100, failed: 2, candidate: 3, scanned: 95, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
    wrapper = mountPage(); await flushUi()
    const s = wrapper.get('[data-test="scan-summary"]').text()
    expect(s).toContain('processed=100'); expect(s).toContain('total=100')
    expect(s).toContain('skipped=0'); expect(s).toContain('failed=2')
    expect(s).toContain('candidates=3'); expect(s).toContain('latest=2026-06-10')
    expect(s).toContain('source=akshare')
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalledWith('s2-completed')
  })

  // ── ROUND7-S2-001: race condition tests ──
  it('late task A response cannot overwrite newer task B context', async () => {
    const taskADeferred = deferred()
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockImplementation(taskId => {
      if (taskId === 'task-a') return taskADeferred.promise
      if (taskId === 'task-b') return Promise.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20, failed: 1, candidate: 5, scanned: 14, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
      return Promise.reject(new Error(`unexpected ${taskId}`))
    })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [{ code: '222222', name: 'B-cand', total_score: 88, level: '重点观察', volume_dry_score: 40, price_stable_score: 40, risk_ratio: 0.04 }] })

    wrapper = mountPage(); await flushUi()

    mockRoute.query = { task: 'task-b' }; await flushUi()
    expect(wrapper.text()).toContain('B-fail')

    taskADeferred.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '111111', name: 'A-fail', status: 'failed' }], summary: { total_stocks: 10, processed: 10, failed: 1, candidate: 0 } })
    await flushUi()

    expect(wrapper.text()).toContain('B-fail')
    expect(wrapper.text()).not.toContain('A-fail')
    expect(wrapper.text()).not.toContain('重新拉取')
    expect(mockApi.getCandidates).not.toHaveBeenCalledWith({ task_id: 'task-a' })
  })

  it('late task B response after switching to live mode does not overwrite live', async () => {
    const taskBDeferred = deferred()
    const s2CandBDeferred = deferred()

    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20, failed: 1, candidate: 5, scanned: 14, skipped: 0 } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [{ code: '222222', name: 'B-cand', total_score: 88, level: '重点观察', volume_dry_score: 40, price_stable_score: 40, risk_ratio: 0.04 }] })

    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('B-fail')

    // Switch to live, but B's task stocks is slow
    mockApi.getTaskStocks.mockImplementation(() => taskBDeferred.promise)
    mockRoute.query = {}; await flushUi()

    // Live takes over
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 50, total_stocks: 100, candidates_found: 2 } })
    mockApi.getTaskStocks.mockImplementation(taskId => Promise.resolve({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 100, processed: 50 } }))
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '600000', name: 'live-cand', score: 85 }] })
    await flushUi()

    // Now B's late response arrives
    taskBDeferred.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20, failed: 1, candidate: 5, scanned: 14, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    await flushUi()

    // B's data must not appear
    expect(wrapper.text()).not.toContain('B-fail')
  })

  it('status query failure preserves loaded historical data', async () => {
    mockRoute.query = { task: 's2-hist' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 2, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'hist-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 50, processed: 50, failed: 2, candidate: 3, scanned: 45, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [{ code: '000002', name: 'hist-cand', total_score: 82, level: '重点观察', volume_dry_score: 42, price_stable_score: 40, risk_ratio: 0.03 }] })
    // getScanStatus rejects for the call in loadHistoricalTask (after task loaded)
    mockApi.getScanStatus.mockRejectedValueOnce(new Error('status down'))

    wrapper = mountPage(); await flushUi()

    // Historical summary, candidate, and failures preserved
    const s = wrapper.get('[data-test="scan-summary"]').text()
    expect(s).toContain('processed=50'); expect(s).toContain('total=50')
    expect(s).toContain('failed=2'); expect(s).toContain('candidates=3')
    expect(wrapper.text()).toContain('hist-fail')
    // Status query error is logged (console.error appears in stderr above)
    // Core requirement: data preserved, no crash
  })

  it('existing tests still pass after viewContext rewrite (smoke)', async () => {
    mockRoute.query = { task: 's2-fine' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 10, processed: 10, failed: 0, candidate: 0, scanned: 10, skipped: 0 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.exists()).toBe(true)
    // No error text
    expect(wrapper.text()).not.toContain('任务不存在')
    expect(wrapper.text()).not.toContain('加载失败')
  })
})
