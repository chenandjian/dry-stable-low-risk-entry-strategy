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
  previewStrategy2BacktestExperiment: vi.fn(),
  getStrategy2BacktestComparison: vi.fn(),
  startStrategy2Backtest: vi.fn(),
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
    api.previewStrategy2BacktestExperiment.mockResolvedValue({ valid: true, normalizedExperiment: { enabled: true } })
    api.getStrategy2BacktestComparison.mockResolvedValue({ comparable: true, baseline: {}, experiment: {}, delta: {} })
    api.startStrategy2Backtest.mockResolvedValue({ ok: true, task_id: 'bt-new', credibilityStatus: 'EXPERIMENTAL' })
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

  it('sends normalized experiment payload when experiment mode is enabled', async () => {
    api.getStrategy2BacktestTask.mockResolvedValue(task())
    wrapper = mount(Strategy2Backtest)
    await flushUi()

    wrapper.vm.experimentEnabled = true
    wrapper.vm.experimentForm.minimumVolumeDryScore = 40
    wrapper.vm.experimentForm.timeExitDays = 5
    wrapper.vm.experimentForm.entryConfirmationType = 'BREAK_RECENT_5D_HIGH'
    wrapper.vm.baselineTaskId = 'baseline-1'
    await wrapper.vm.startBacktest()

    expect(api.startStrategy2Backtest).toHaveBeenCalled()
    const payload = api.startStrategy2Backtest.mock.calls[0][0]
    expect(payload.baselineTaskId).toBe('baseline-1')
    expect(payload.experiment.enabled).toBe(true)
    expect(payload.experiment.minimumVolumeDryScore).toBe(40)
    expect(payload.experiment.timeExitDays).toBe(5)
    expect(payload.experiment.entryConfirmation.type).toBe('BREAK_RECENT_5D_HIGH')
  })

  it('shows experimental badge, snapshot, and comparison result', async () => {
    api.getStrategy2BacktestTask.mockResolvedValue(task({
      credibility_status: 'EXPERIMENTAL',
      baseline_task_id: 'baseline-1',
      experiment_snapshot: JSON.stringify({
        enabled: true,
        minimum_volume_dry_score: 40,
        time_exit_days: 5,
        entry_confirmation: { type: 'BREAK_RECENT_5D_HIGH' },
      }),
      summary: {
        horizon_stats: {},
        funnel: { experiment_filtered_days: 3, entry_confirmation_failed_count: 1, time_exit_count: 2 },
      },
    }))
    wrapper = mount(Strategy2Backtest)
    await flushUi()
    await wrapper.vm.loadTask('bt-1')
    await flushUi()

    expect(wrapper.text()).toContain('EXPERIMENTAL')
    expect(wrapper.text()).toContain('最低量干分')
    expect(wrapper.text()).toContain('baseline-1')
    expect(api.getStrategy2BacktestComparison).toHaveBeenCalledWith('bt-1', 'baseline-1')
  })
})
