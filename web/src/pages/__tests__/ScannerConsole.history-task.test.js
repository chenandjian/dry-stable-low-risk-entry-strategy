import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'

const mockRoute = reactive({ query: {}, path: '/' })
const mockRouter = { push: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => mockRouter,
}))

const mockApi = {
  startScan: vi.fn(), startStrategy2Scan: vi.fn(),
  getScanStatus: vi.fn(), getCandidates: vi.fn(),
  getTaskStocks: vi.fn(), retryFailedStocks: vi.fn(),
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
  return mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
}

describe('ScannerConsole history task context', () => {
  let wrapper

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockRoute.query = {}
    defaults()
  })

  afterEach(() => {
    vi.useRealTimers()
    if (wrapper) wrapper.unmount()
    wrapper = null
  })

  // ══ basic isolation ══

  it('current S1 does not overwrite historical S2', async () => {
    mockRoute.query = { task: 's2-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000001', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 10, processed: 10, failed: 3, candidate: 2, scanned: 5, skipped: 0 },
    })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's1-running', strategyType: 'STRATEGY_1_CUP_HANDLE', stats: { processed: 500, total_stocks: 5000 } })
    wrapper = mountPage()
    await nextTick(); await nextTick()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-historical', expect.any(Object))
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalled()
  })

  it('current S2 does not overwrite historical S1', async () => {
    mockRoute.query = { task: 's1-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [],
      summary: { total_stocks: 5, processed: 5, failed: 0 },
    })
    mockApi.getScanStatus.mockResolvedValue({ running: true, task_id: 's2-running', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE', stats: { processed: 100, total_stocks: 5000 } })
    wrapper = mountPage()
    await nextTick(); await nextTick()
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 's1-historical' })
  })

  it('historical S2 hides retry button', async () => {
    mockRoute.query = { task: 's2-done' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000002', name: 'fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 1, processed: 1, failed: 1 },
    })
    wrapper = mountPage()
    await nextTick(); await nextTick(); await nextTick()
    expect(wrapper.text()).not.toContain('重新拉取')
  })

  it('unknown task shows 任务不存在', async () => {
    mockRoute.query = { task: 'not-found' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    wrapper = mountPage()
    await nextTick(); await nextTick()
    expect(wrapper.text()).toContain('任务不存在')
  })

  it('non-404 error shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'server-error' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 500, error: 'INTERNAL_ERROR' })
    wrapper = mountPage()
    await nextTick(); await nextTick()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })

  it('network rejection shows 历史任务加载失败', async () => {
    mockRoute.query = { task: 'net-fail' }
    mockApi.getTaskStocks.mockRejectedValue(new Error('Network Error'))
    wrapper = mountPage()
    await nextTick(); await nextTick()
    expect(wrapper.text()).toContain('历史任务加载失败')
  })

  // ══ completed historical task ══

  it('completed historical task applies persisted summary on initial load', async () => {
    mockRoute.query = { task: 's2-completed' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 2, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000001', name: 'f1', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 100, processed: 100, failed: 2, candidate: 3, scanned: 95, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' },
    })
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })

    wrapper = mountPage()
    await nextTick(); await nextTick(); await nextTick()

    expect(mockApi.getStrategy2Candidates).toHaveBeenCalled()
    // Summary applied: failed count should show
    expect(wrapper.text()).toContain('失败股票')
  })

  // ══ running → completed ══

  it('historical running task refreshes final summary after completion', async () => {
    mockRoute.query = { task: 's2-run' }
    // Initial: running
    mockApi.getScanStatus.mockResolvedValueOnce({
      running: true, task_id: 's2-run', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stats: { processed: 80, total_stocks: 100 },
    })
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 5, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: 'f1', name: 'fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 100, processed: 80, failed: 5, candidate: 3, scanned: 72, skipped: 0 },
    })

    wrapper = mountPage()
    await nextTick(); await nextTick()

    // Poll fires: completed + mismatch
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 5, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: 'f1', name: 'fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 100, processed: 100, failed: 5, candidate: 3, scanned: 92, skipped: 0, latest_trade_date: '2026-06-10' },
    })

    await vi.advanceTimersByTimeAsync(1000)
    await nextTick(); await nextTick(); await nextTick()

    // Task stocks called at least twice
    expect(mockApi.getTaskStocks.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  // ══ task A → task B ══

  it('query change from task A to task B reloads B and clears A', async () => {
    // Task A: Strategy1 with failures
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 2, strategy_type: 'STRATEGY_1_CUP_HANDLE',
      stocks: [{ code: '111111', name: 'A-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 10, processed: 10, failed: 2, candidate: 0, scanned: 8, skipped: 0 },
    })
    mockApi.getCandidates.mockResolvedValue({ candidates: [{ code: '111111', name: 'A-candidate', score: 85 }], total: 1 })

    wrapper = mountPage()
    await nextTick(); await nextTick(); await nextTick()
    // A loaded with retry button and A failure
    expect(wrapper.text()).toContain('重新拉取')
    expect(wrapper.text()).toContain('A-fail')

    // Switch to Task B: Strategy2
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '222222', name: 'B-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 20, processed: 20, failed: 1, candidate: 5, scanned: 14, skipped: 0 },
    })
    mockRoute.query = { task: 'task-b' }
    await nextTick(); await nextTick(); await nextTick()

    // A's data gone, B's data present
    expect(wrapper.text()).not.toContain('A-fail')
    expect(wrapper.text()).not.toContain('重新拉取')
    expect(wrapper.text()).toContain('B-fail')
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalledWith('task-b')
  })

  // ══ valid → missing ══

  it('query change from valid to missing clears old state', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE',
      stocks: [{ code: '111111', name: 'A-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 5, processed: 5, failed: 1 },
    })

    wrapper = mountPage()
    await nextTick(); await nextTick(); await nextTick()
    expect(wrapper.text()).toContain('重新拉取')
    expect(wrapper.text()).toContain('A-fail')

    // Switch to missing
    mockRoute.query = { task: 'missing' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    await nextTick(); await nextTick(); await nextTick()

    expect(wrapper.text()).toContain('任务不存在')
    expect(wrapper.text()).not.toContain('重新拉取')
    expect(wrapper.text()).not.toContain('A-fail')
  })

  // ══ error semantics ══

  it('error loading clears old task data', async () => {
    // Load task A successfully first
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_1_CUP_HANDLE',
      stocks: [{ code: '111111', name: 'A-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 5, processed: 5, failed: 1 },
    })
    wrapper = mountPage()
    await nextTick(); await nextTick(); await nextTick()

    // Switch to task B which fails
    mockRoute.query = { task: 'task-b' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 500, error: 'INTERNAL_ERROR' })
    await nextTick(); await nextTick(); await nextTick()

    // Shows error, old data gone
    expect(wrapper.text()).toContain('历史任务加载失败')
    expect(wrapper.text()).not.toContain('A-fail')
  })
})
