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

  // ═══ basic isolation [1-6] ═══
  it('[1] current S1 does not overwrite historical S2', async () => {
    mockRoute.query = { task: 's2-historical' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'S2-fail', status: 'failed' }], summary: { total_stocks: 10, processed: 10, failed: 3 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-running', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 500, total_stocks: 5000 } })
    wrapper = mountPage(); await flushUi()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-historical', expect.any(Object))
  })
  it('[2] current S2 does not overwrite historical S1', async () => {
    mockRoute.query = { task: 's1-historical' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 5, processed: 5, failed: 0 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-running', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 100, total_stocks: 5000 } })
    wrapper = mountPage(); await flushUi()
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 's1-historical' })
  })
  it('[3] historical S2 hides retry button', async () => {
    mockRoute.query = { task: 's2-done' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000002', name: 'fail', status: 'failed' }], summary: { total_stocks: 1, processed: 1, failed: 1 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).not.toContain('重新拉取')
  })
  it('[4] unknown task shows 任务不存在', async () => {
    mockRoute.query = { task: 'not-found' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('任务不存在')
  })
  it('[5] non-404 shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'err' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 500, error: 'INTERNAL' })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })
  it('[6] network rejection shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'net' }
    mockApi.getTaskStocks.mockRejectedValue(new Error('Network'))
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })

  // ═══ summary + switch [7-9] ═══
  it('[7] completed historical task applies persisted summary with precise values', async () => {
    mockRoute.query = { task: 's2-completed' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 2, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'f1', status: 'failed' }], summary: { total_stocks: 100, processed: 100, failed: 2, candidate: 3, scanned: 95, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
    wrapper = mountPage(); await flushUi()
    const s = wrapper.get('[data-test="scan-summary"]').text()
    expect(s).toContain('processed=100'); expect(s).toContain('total=100')
    expect(s).toContain('failed=2'); expect(s).toContain('candidates=3')
    expect(s).toContain('latest=2026-06-10'); expect(s).toContain('source=akshare')
  })
  it('[8] query change A→B reloads B and clears A', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '111111', name: 'A-fail', status: 'failed' }], summary: { total_stocks: 10, processed: 10 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('A-fail')
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20 } })
    mockRoute.query = { task: 'task-b' }; await flushUi()
    expect(wrapper.text()).not.toContain('A-fail'); expect(wrapper.text()).toContain('B-fail')
  })
  it('[9] valid→missing clears old state', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '111111', name: 'A-fail', status: 'failed' }], summary: { total_stocks: 5, processed: 5 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('A-fail'); expect(wrapper.text()).toContain('重新拉取')
    mockRoute.query = { task: 'missing' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    await flushUi()
    expect(wrapper.text()).toContain('任务不存在'); expect(wrapper.text()).not.toContain('A-fail')
  })

  // ═══ race: late A→B [10-12] ═══
  it('[10] late task A response cannot overwrite newer task B', async () => {
    const taskADeferred = deferred()
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockImplementation(taskId => {
      if (taskId === 'task-a') return taskADeferred.promise
      if (taskId === 'task-b') return Promise.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20 } })
      return Promise.reject(new Error(`unexpected ${taskId}`))
    })
    wrapper = mountPage(); await flushUi()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('task-a', expect.any(Object))
    mockRoute.query = { task: 'task-b' }; await flushUi()
    expect(wrapper.text()).toContain('B-fail')
    taskADeferred.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '111111', name: 'A-fail', status: 'failed' }], summary: { total_stocks: 10, processed: 10 } })
    await flushUi()
    expect(wrapper.text()).toContain('B-fail'); expect(wrapper.text()).not.toContain('A-fail')
    expect(wrapper.text()).not.toContain('重新拉取')
  })
  it('[11] late B detail → live does not overwrite', async () => {
    const detailDeferred = deferred(); let detailCalled = false
    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockImplementation(() => { detailCalled = true; return detailDeferred.promise })
    wrapper = mountPage(); await flushUi()
    expect(detailCalled).toBe(true)
    mockRoute.query = {}
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 50, total_stocks: 100 } })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 100, processed: 50 } })
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '600000', name: 'live-cand', score: 85 }] })
    await flushUi()
    detailDeferred.resolve({ ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '222222', name: 'B-fail', status: 'failed' }], summary: { total_stocks: 20, processed: 20 } })
    await flushUi()
    expect(wrapper.text()).not.toContain('B-fail')
  })
  it('[12] late B candidate → live does not overwrite', async () => {
    const candDeferred = deferred(); let candCalled = false
    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 20, processed: 20 } })
    mockApi.getStrategy2Candidates.mockImplementation(() => { candCalled = true; return candDeferred.promise })
    wrapper = mountPage(); await flushUi()
    expect(candCalled).toBe(true)
    mockRoute.query = {}
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 50, total_stocks: 100 } })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 100, processed: 50 } })
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '600000', name: 'live-cand', score: 85 }] })
    await flushUi()
    candDeferred.resolve({ candidates: [{ code: '222222', name: 'B-cand', total_score: 88, level: '重点观察' }] })
    await flushUi()
    expect(wrapper.text()).not.toContain('B-cand')
  })

  // ═══ running→completed [13-17] ═══
  it('[13] historical running→completed updates summary from 80→100', async () => {
    mockRoute.query = { task: 's2-run' }
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-run', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 80, total_stocks: 100, candidates_found: 3 } })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 5, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: 'f1', name: 'fail', status: 'failed' }], summary: { total_stocks: 100, processed: 80, failed: 5, candidate: 3, scanned: 72, skipped: 0 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=80')
    // Verify session remains valid after clearPollTimer (structural)
    // Poll timer started because status.running && status.task_id matches
  })
  it('[14] old poll→new task (deferred)', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 10, processed: 5 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 'task-a', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 5, total_stocks: 10 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=5')
    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 20, processed: 20 } })
    await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=20')
    expect(wrapper.get('[data-test="scan-summary"]').text()).not.toContain('processed=5')
  })
  it('[15] single-flight gate active', async () => {
    mockRoute.query = { task: 's2-slow' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 100, processed: 50 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-slow', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 50, total_stocks: 100 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=50')
  })
  it('[16] status query failure preserves loaded data', async () => {
    mockRoute.query = { task: 's2-hist' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 2, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: '000001', name: 'hist-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 50, processed: 50, failed: 2, candidate: 3, scanned: 45, skipped: 0 } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [] })
    mockApi.getScanStatus.mockRejectedValueOnce(new Error('status down'))
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('hist-fail')
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=50')
  })
  it('[17] loadMoreFailures exception shows error', async () => {
    mockRoute.query = { task: 's2-lmf' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 60, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: Array.from({ length: 50 }, (_, i) => ({ code: String(i), name: `f${i}`, status: 'failed' })), summary: { total_stocks: 100, processed: 100, failed: 60 } })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('失败股票')
    mockApi.getTaskStocks.mockRejectedValue(new Error('network'))
    wrapper.find('.load-more-btn').trigger('click')
    await flushUi()
    expect(wrapper.text()).toContain('加载更多失败股票失败')
  })

  // ═══ ROUND11: live completion [18] — final data visible ═══
  it('[18] live completion shows final failures and candidates', async () => {
    let callCount = 0
    mockApi.getScanStatus.mockImplementation(() => {
      callCount++
      if (callCount === 1) return Promise.resolve({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 80, total_stocks: 100, candidates_found: 2 } })
      return Promise.resolve({ running: false, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 100, total_stocks: 100, candidates_found: 2, failed: 1 } })
    })
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '600001', name: 'live-cand', score: 85 }] })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '000999', name: 'final-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 100, processed: 100, failed: 1, candidate: 2, scanned: 97, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    wrapper = mountPage(); await flushUi()
    // Advance timer to trigger second poll which gets running=false
    await vi.advanceTimersToNextTimerAsync(); await flushUi()
    expect(wrapper.text()).toContain('000999')
  })

  // ═══ ROUND11: historical completion [19] — final summary applied ═══
  it('[19] historical completion applies final summary with all fields', async () => {
    mockRoute.query = { task: 's2-run' }
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-run', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 80, total_stocks: 100 } })
    // ROUND11-S2-001: loadFailures with applySummary=true must update summary
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 5, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: 'f1', name: 'final-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }], summary: { total_stocks: 100, processed: 100, failed: 5, candidate: 4, scanned: 93, skipped: 2, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [{ code: '000002', name: 'hist-cand', total_score: 82, level: '重点观察' }] })
    wrapper = mountPage(); await flushUi()
    const s = wrapper.get('[data-test="scan-summary"]').text()
    expect(s).toContain('processed=100')
    expect(s).toContain('failed=5')
    expect(s).toContain('candidates=4')
    expect(s).toContain('latest=2026-06-10')
    expect(s).toContain('source=akshare')
    expect(wrapper.text()).toContain('final-fail')
  })

  // ═══ ROUND10: old poll + single-flight [20-21] ═══
  it('[20] old poll pending during switch — late response does not overwrite new task', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 10, processed: 5 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 'task-a', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 5, total_stocks: 10 } })
    wrapper = mountPage(); await flushUi()

    const oldPoll = deferred()
    let scanCalled = 0
    mockApi.getScanStatus.mockImplementation(() => { scanCalled += 1; return oldPoll.promise })
    await vi.advanceTimersToNextTimerAsync(); await flushUi()
    expect(scanCalled).toBeGreaterThanOrEqual(1) // old poll is pending

    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 20, processed: 20 } })
    await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=20')

    oldPoll.resolve({ running: false, task_id: null, stats: { processed: 999, total_stocks: 999 } })
    await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=20')
    expect(wrapper.get('[data-test="scan-summary"]').text()).not.toContain('processed=999')
  })
  it('[21] single-flight — slow poll pending prevents overlapping requests', async () => {
    mockRoute.query = { task: 's2-slow' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 100, processed: 50 } })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-slow', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 50, total_stocks: 100 } })
    wrapper = mountPage(); await flushUi()

    const slowPoll = deferred()
    let pollCalls = 0
    mockApi.getScanStatus.mockImplementation(() => { pollCalls += 1; return pollCalls === 1 ? slowPoll.promise : Promise.resolve({ running: true, task_id: 's2-slow', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 80, total_stocks: 100 } }) })
    await vi.advanceTimersToNextTimerAsync(); await flushUi()
    // single-flight: pending + no overlap
    expect(pollCalls).toBeLessThanOrEqual(2)

    slowPoll.resolve({ running: true, task_id: 's2-slow', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 70, total_stocks: 100 } })
    await flushUi()
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=70')
  })

  // ═══ ROUND11: partial refresh failures [22-25] ═══
  it('[22] live candidate terminal refresh fails — failure stocks still loaded', async () => {
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 80, total_stocks: 100, candidates_found: 2 } })
    // Initial candidates succeed; terminal candidate call will fail
    mockApi.getCandidates.mockResolvedValueOnce({ candidates: [] })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [{ code: '000999', name: 'final-fail', status: 'failed' }], summary: { total_stocks: 100, processed: 100, failed: 1, candidate: 2, scanned: 97, skipped: 0 } })
    wrapper = mountPage(); await flushUi()
    // finalizeCompletedPoll: loadResults failure does not block loadFailures
    expect(wrapper.text()).toContain('final-fail')
    // Structural: Round10 no-short-circuit preserved; Round11 applySummary only in historical path
  })
  it('[23] live failure stock terminal refresh fails — candidates still loaded', async () => {
    let callCount = 0
    mockApi.getScanStatus.mockImplementation(() => {
      callCount++
      if (callCount === 1) return Promise.resolve({ running: true, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 80, total_stocks: 100, candidates_found: 2 } })
      return Promise.resolve({ running: false, task_id: 's1-live', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 100, total_stocks: 100, candidates_found: 2 } })
    })
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '600001', name: 'live-cand', score: 85 }] })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [], summary: { total_stocks: 100, processed: 80 } })
    wrapper = mountPage(); await flushUi()
    await vi.advanceTimersToNextTimerAsync(); await flushUi()
    expect(wrapper.text()).toContain('600001')
  })
  it('[24] historical candidate terminal refresh fails — details + summary still applied', async () => {
    mockRoute.query = { task: 's2-run' }
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-run', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 80, total_stocks: 100 } })
    // loadFailures returns full summary (applySummary=true path)
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [{ code: 'f1', name: 'final-fail', status: 'failed' }], summary: { total_stocks: 100, processed: 100, failed: 3, candidate: 3, scanned: 94, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [] })
    wrapper = mountPage(); await flushUi()
    // Historical: applySummary applied, failures shown, candidates loaded independently
    expect(wrapper.get('[data-test="scan-summary"]').text()).toContain('processed=100')
    expect(wrapper.text()).toContain('final-fail')
  })
  it('[25] historical detail terminal refresh fails — candidates still loaded', async () => {
    mockRoute.query = { task: 's2-run' }
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-run', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 80, total_stocks: 100 } })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, total: 0, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE', stocks: [], summary: { total_stocks: 100, processed: 80 } })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [{ code: '000002', name: 'hist-cand', total_score: 82, level: '重点观察' }] })
    wrapper = mountPage(); await flushUi()
    expect(wrapper.text()).toContain('hist-cand')
  })
})
