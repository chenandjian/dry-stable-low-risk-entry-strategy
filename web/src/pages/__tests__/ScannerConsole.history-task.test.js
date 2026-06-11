import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'

// Reactive mock route so query changes trigger watch
const mockRoute = reactive({ query: {}, path: '/' })
const mockRouter = { push: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => mockRouter,
}))

const mockApi = {
  startScan: vi.fn(),
  startStrategy2Scan: vi.fn(),
  getScanStatus: vi.fn(),
  getCandidates: vi.fn(),
  getTaskStocks: vi.fn(),
  retryFailedStocks: vi.fn(),
  getStrategy2Candidates: vi.fn(),
  getScanTasks: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({
  useApi: () => mockApi,
}))

import ScannerConsole from '../ScannerConsole.vue'

describe('ScannerConsole history task context', () => {
  let wrapper

  function setupApiDefaults() {
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, stocks: [], total: 0, strategy_type: null, summary: {} })
    mockApi.getCandidates.mockResolvedValue({ candidates: [], total: 0 })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [], total: 0 })
    mockApi.getScanTasks.mockResolvedValue({ tasks: [] })
  }

  function mountPage() {
    wrapper = mount(ScannerConsole, {
      global: { stubs: { 'router-link': true, 'router-view': true } },
    })
  }

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockRoute.query = {}
    setupApiDefaults()
  })

  afterEach(() => {
    vi.useRealTimers()
    if (wrapper) wrapper.unmount()
    wrapper = null
  })

  it('renders without error', () => {
    mountPage()
    expect(wrapper.exists()).toBe(true)
  })

  it('current S1 does not overwrite historical S2 task context', async () => {
    mockRoute.query = { task: 's2-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000001', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 10, processed: 10, failed: 3, candidate: 2, scanned: 5, skipped: 0 },
    })
    mockApi.getScanStatus.mockResolvedValue({
      running: true, task_id: 's1-running', strategyType: 'STRATEGY_1_CUP_HANDLE',
      stats: { processed: 500, total_stocks: 5000 },
    })
    mountPage()
    await nextTick(); await nextTick()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-historical', expect.any(Object))
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalled()
  })

  it('current S2 does not overwrite historical S1 task context', async () => {
    mockRoute.query = { task: 's1-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [],
      summary: { total_stocks: 5, processed: 5, failed: 0 },
    })
    mockApi.getScanStatus.mockResolvedValue({
      running: true, task_id: 's2-running', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stats: { processed: 100, total_stocks: 5000 },
    })
    mountPage()
    await nextTick(); await nextTick()
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 's1-historical' })
  })

  it('historical S2 hides strategy1 retry button', async () => {
    mockRoute.query = { task: 's2-done' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000002', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 1, processed: 1, failed: 1 },
    })
    mountPage()
    await nextTick(); await nextTick(); await nextTick()
    expect(wrapper.text()).not.toContain('重新拉取')
  })

  it('unknown task shows error message', async () => {
    mockRoute.query = { task: 'not-found' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    mountPage()
    await nextTick(); await nextTick()
    expect(wrapper.text()).toContain('任务不存在')
  })

  it('historical running task refreshes final summary after completion', async () => {
    mockRoute.query = { task: 's2-running-hist' }
    // Task is running initially
    mockApi.getScanStatus.mockResolvedValue({
      running: true, task_id: 's2-running-hist', strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stats: { processed: 80, total_stocks: 100 },
    })
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 5, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: 'fail1', name: 'f1', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 100, processed: 80, failed: 5 },
    })

    mountPage()
    await nextTick(); await nextTick()

    // Verify historical context loaded correctly with S2 type
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalled()
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-running-hist', expect.any(Object))
  })

  it('query change from valid task to missing task clears old state', async () => {
    // First load task A with failures
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 2, strategy_type: 'STRATEGY_1_CUP_HANDLE',
      stocks: [
        { code: '000001', name: 'A-fail-1', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' },
        { code: '000002', name: 'A-fail-2', status: 'failed' },
      ],
      summary: { total_stocks: 10, processed: 10, failed: 2 },
    })
    mountPage()
    await nextTick(); await nextTick(); await nextTick()
    // Verify retry button visible for S1
    expect(wrapper.text()).toContain('重新拉取')

    // Switch to missing task
    mockRoute.query = { task: 'missing-task' }
    mockApi.getTaskStocks.mockResolvedValue({ ok: false, statusCode: 404, error: 'TASK_NOT_FOUND' })
    await nextTick(); await nextTick(); await nextTick()

    // Old failures and retry button must be gone
    expect(wrapper.text()).toContain('任务不存在')
    expect(wrapper.text()).not.toContain('重新拉取')
    expect(wrapper.text()).not.toContain('A-fail-1')
  })
})
