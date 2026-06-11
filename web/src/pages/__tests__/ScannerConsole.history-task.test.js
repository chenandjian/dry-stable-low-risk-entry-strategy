import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

// Mock useApi composable
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

// Mock router
const mockRoute = { query: {}, path: '/' }
const mockRouter = { push: vi.fn(), replace: vi.fn() }
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => mockRouter,
}))

// Import after mocks
import ScannerConsole from '../ScannerConsole.vue'

describe('ScannerConsole history task context', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(mockRoute, { query: {}, path: '/' })
    mockApi.getScanStatus.mockResolvedValue({ running: false, task_id: null, stats: {} })
    mockApi.getTaskStocks.mockResolvedValue({ ok: true, stocks: [], total: 0, strategy_type: null, summary: {} })
    mockApi.getCandidates.mockResolvedValue({ candidates: [], total: 0 })
    mockApi.getStrategy2Candidates.mockResolvedValue({ candidates: [], total: 0 })
    mockApi.getScanTasks.mockResolvedValue({ tasks: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders without error', () => {
    const wrapper = mount(ScannerConsole, {
      global: { stubs: { 'router-link': true, 'router-view': true } },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('current S1 does not overwrite historical S2 task context', async () => {
    mockRoute.query = { task: 's2-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 3, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [
        { code: '000001', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED', primary_source: 'baidu', fallback_source: 'tencent', primary_attempts: 2, fallback_attempts: 2, source_errors: '{"baidu":"err","sina":"err","tencent":"err"}' },
      ],
      summary: { total_stocks: 10, processed: 10, failed: 3, candidate: 2, scanned: 5, skipped: 0, latest_trade_date: '2026-06-10', stock_pool_source: 'akshare' },
    })
    mockApi.getScanStatus.mockResolvedValue({
      running: true, task_id: 's1-running',
      strategyType: 'STRATEGY_1_CUP_HANDLE',
      stats: { processed: 500, total_stocks: 5000 },
    })

    mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
    await nextTick()
    await nextTick()

    // S2 task context should not be overwritten by running S1
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('s2-historical', expect.any(Object))
    // Strategy type from historical task endpoint
    expect(mockApi.getStrategy2Candidates).toHaveBeenCalled()
  })

  it('current S2 does not overwrite historical S1 task context', async () => {
    mockRoute.query = { task: 's1-historical' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [],
      summary: { total_stocks: 5, processed: 5, failed: 0 },
    })
    mockApi.getScanStatus.mockResolvedValue({
      running: true, task_id: 's2-running',
      strategyType: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stats: { processed: 100, total_stocks: 5000 },
    })

    mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
    await nextTick()
    await nextTick()

    // S1 candidates called with task_id
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 's1-historical' })
  })

  it('historical S2 hides strategy1 retry button', async () => {
    mockRoute.query = { task: 's2-done' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 1, strategy_type: 'STRATEGY_2_EXTREME_DRY_STABLE',
      stocks: [{ code: '000002', name: 'S2-fail', status: 'failed', status_reason: 'ALL_DATA_SOURCES_FAILED' }],
      summary: { total_stocks: 1, processed: 1, failed: 1 },
    })

    const wrapper = mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
    await nextTick()
    await nextTick()
    await nextTick()

    // Retry button should not exist for strategy2
    expect(wrapper.text()).not.toContain('重新拉取')
  })

  it('unknown task shows error message', async () => {
    mockRoute.query = { task: 'not-found' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: false, statusCode: 404, error: 'TASK_NOT_FOUND',
    })

    const wrapper = mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
    await nextTick()
    await nextTick()

    expect(wrapper.text()).toContain('任务不存在')
  })

  it('query task A loads correct historical context', async () => {
    mockRoute.query = { task: 'task-a' }
    mockApi.getTaskStocks.mockResolvedValue({
      ok: true, total: 0, strategy_type: 'STRATEGY_1_CUP_HANDLE', stocks: [],
      summary: { total_stocks: 5, processed: 5 },
    })

    mount(ScannerConsole, { global: { stubs: { 'router-link': true, 'router-view': true } } })
    await nextTick()
    await nextTick()

    // Should have called getTaskStocks for task-a
    expect(mockApi.getTaskStocks).toHaveBeenCalledWith('task-a', expect.any(Object))
    // S1 mode should call getCandidates with task_id
    expect(mockApi.getCandidates).toHaveBeenCalledWith({ task_id: 'task-a' })
  })
})
