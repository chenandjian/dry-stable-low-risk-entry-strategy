import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy2BacktestTasks: vi.fn(),
  getStrategy2BacktestTask: vi.fn(),
  getStrategy2BacktestOpportunities: vi.fn(),
  getStrategy2BacktestInsufficientStocks: vi.fn(),
  getStrategy2BacktestStocks: vi.fn(),
  resumeStrategy2Backtest: vi.fn(),
  cancelStrategy2Backtest: vi.fn(),
  retryFailedStrategy2Backtest: vi.fn(),
  getStrategy2BacktestStatus: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy2Backtest from '../Strategy2Backtest.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function task(overrides = {}) {
  return {
    id: 'bt-1',
    status: 'completed_with_errors',
    credibility_status: 'PHASE1_INCOMPLETE',
    backtest_engine_version: 'phase1-v3',
    strategy_engine_version: 'strategy2-v2',
    data_revision_version: 'daily-ohlc-v2',
    data_revision_id: 'abcdef1234567890',
    failed_stocks_count: 1,
    summary: { horizon_stats: {}, funnel: {} },
    ...overrides,
  }
}

describe('Strategy2Backtest task controls', () => {
  let wrapper

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    api.getStrategy2BacktestTasks.mockResolvedValue({ tasks: [], total: 0 })
    api.getStrategy2BacktestOpportunities.mockResolvedValue({ items: [], total: 0 })
    api.getStrategy2BacktestInsufficientStocks.mockResolvedValue({ stocks: [] })
    api.getStrategy2BacktestStocks.mockResolvedValue({
      stocks: [{ code: '000001', name: '失败股', error_code: 'ValueError', error_detail: 'bad row' }],
    })
    api.getStrategy2BacktestStatus.mockResolvedValue({ running: false, taskId: null, stats: {} })
    api.retryFailedStrategy2Backtest.mockResolvedValue({ ok: true })
    api.resumeStrategy2Backtest.mockResolvedValue({ ok: true })
    api.cancelStrategy2Backtest.mockResolvedValue({ ok: true })
  })

  afterEach(() => {
    if (wrapper) wrapper.unmount()
    vi.useRealTimers()
  })

  it('shows credibility, versions, failed stock, and retries failed stocks', async () => {
    api.getStrategy2BacktestTask.mockResolvedValue(task())
    wrapper = mount(Strategy2Backtest)
    await flushUi()
    await wrapper.vm.loadTask('bt-1')
    await flushUi()

    expect(wrapper.text()).toContain('PHASE1_INCOMPLETE')
    expect(wrapper.text()).toContain('phase1-v3')
    expect(wrapper.text()).toContain('失败股')
    expect(wrapper.text()).toContain('bad row')
    const retry = wrapper.findAll('button').find(button => button.text() === '重试失败股票')
    await retry.trigger('click')
    expect(api.retryFailedStrategy2Backtest).toHaveBeenCalledWith('bt-1')
  })

  it('allows interrupted current-version task to resume', async () => {
    api.getStrategy2BacktestTask.mockResolvedValue(task({ status: 'INTERRUPTED', failed_stocks_count: 0 }))
    api.getStrategy2BacktestStocks.mockResolvedValue({ stocks: [] })
    wrapper = mount(Strategy2Backtest)
    await flushUi()
    await wrapper.vm.loadTask('bt-1')
    await flushUi()

    const resume = wrapper.findAll('button').find(button => button.text() === '恢复')
    await resume.trigger('click')
    expect(api.resumeStrategy2Backtest).toHaveBeenCalledWith('bt-1')
  })

  it('does not offer resume for revision-changed tasks', async () => {
    api.getStrategy2BacktestTask.mockResolvedValue(task({ status: 'ENGINE_REVISION_CHANGED', failed_stocks_count: 0 }))
    api.getStrategy2BacktestStocks.mockResolvedValue({ stocks: [] })
    wrapper = mount(Strategy2Backtest)
    await flushUi()
    await wrapper.vm.loadTask('bt-1')
    await flushUi()

    expect(wrapper.text()).toContain('引擎版本变化')
    expect(wrapper.findAll('button').some(button => button.text() === '恢复')).toBe(false)
    expect(wrapper.findAll('button').some(button => button.text() === '重试失败股票')).toBe(false)
  })

  it('restores a running task after page refresh and allows cancellation', async () => {
    api.getStrategy2BacktestStatus.mockResolvedValue({
      running: true, taskId: 'bt-running', stats: { processed_stocks: 2, total_stocks: 10 },
    })
    api.getStrategy2BacktestTask.mockResolvedValue(task({
      id: 'bt-running', status: 'running', failed_stocks_count: 0, summary: null,
    }))
    api.getStrategy2BacktestStocks.mockResolvedValue({ stocks: [] })
    wrapper = mount(Strategy2Backtest)
    await flushUi()

    const cancel = wrapper.findAll('button').find(button => button.text() === '取消')
    await cancel.trigger('click')
    expect(api.cancelStrategy2Backtest).toHaveBeenCalledWith('bt-running')
  })
})
