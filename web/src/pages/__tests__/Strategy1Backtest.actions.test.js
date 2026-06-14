import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy1BacktestTasks: vi.fn(),
  getStrategy1BacktestTask: vi.fn(),
  getStrategy1BacktestOpportunities: vi.fn(),
  getStrategy1BacktestSignals: vi.fn(),
  getStrategy1BacktestStocks: vi.fn(),
  getStrategy1BacktestStatus: vi.fn(),
  previewStrategy1BacktestExperiment: vi.fn(),
  getStrategy1BacktestComparison: vi.fn(),
  startStrategy1Backtest: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy1Backtest from '../Strategy1Backtest.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('Strategy1Backtest', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy1BacktestTasks.mockResolvedValue({ tasks: [], total: 0 })
    api.getStrategy1BacktestStatus.mockResolvedValue({ running: false, taskId: null, stats: {} })
    api.getStrategy1BacktestTask.mockResolvedValue({
      task: {
        id: 's1bt-exp',
        status: 'completed',
        credibility_status: 'EXPERIMENTAL',
        baseline_task_id: 's1bt-base',
        experiment_snapshot: JSON.stringify({ enabled: true, minimum_total_score: 75 }),
      },
      summary: { total_opportunities: 1, entered_count: 1 },
    })
    api.getStrategy1BacktestOpportunities.mockResolvedValue({
      opportunities: [{ code: '600000', first_detected_date: '2025-01-02', exit_reason: 'TARGET' }],
      total: 1,
    })
    api.getStrategy1BacktestSignals.mockResolvedValue({ signals: [], total: 0 })
    api.getStrategy1BacktestStocks.mockResolvedValue({ stocks: [], total: 0 })
    api.previewStrategy1BacktestExperiment.mockResolvedValue({
      valid: true,
      normalizedExperiment: { enabled: true, minimum_total_score: 75 },
      credibilityStatus: 'EXPERIMENTAL',
    })
    api.getStrategy1BacktestComparison.mockResolvedValue({
      comparable: true,
      baseline: { opportunities: 1 },
      experiment: { opportunities: 2 },
      delta: { opportunities: 1 },
    })
    api.startStrategy1Backtest.mockResolvedValue({ ok: true, task_id: 's1bt-new', credibilityStatus: 'EXPERIMENTAL' })
  })

  it('sends experiment payload and baseline task id when starting experiment', async () => {
    const wrapper = mount(Strategy1Backtest)
    await flushUi()

    wrapper.vm.experimentEnabled = true
    wrapper.vm.experimentForm.minimumTotalScore = 75
    wrapper.vm.experimentForm.minVolumeDryScore = 8
    wrapper.vm.baselineTaskId = 's1bt-base'
    await wrapper.vm.startBacktest()

    const payload = api.startStrategy1Backtest.mock.calls[0][0]
    expect(payload.baselineTaskId).toBe('s1bt-base')
    expect(payload.experiment.enabled).toBe(true)
    expect(payload.experiment.minimumTotalScore).toBe(75)
    expect(payload.experiment.decision.minVolumeDryScore).toBe(8)
  })

  it('shows experimental badge and loads comparison for experimental task', async () => {
    const wrapper = mount(Strategy1Backtest)
    await flushUi()
    await wrapper.vm.loadTask('s1bt-exp')
    await flushUi()

    expect(wrapper.text()).toContain('EXPERIMENTAL')
    expect(wrapper.text()).toContain('minimum_total_score')
    expect(wrapper.text()).toContain('对比可用')
    expect(api.getStrategy1BacktestComparison).toHaveBeenCalledWith('s1bt-exp', 's1bt-base')
  })
})
