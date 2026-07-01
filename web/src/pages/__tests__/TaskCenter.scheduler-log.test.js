import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const mockRouter = { push: vi.fn() }
vi.mock('vue-router', () => ({ useRouter: () => mockRouter }))

const api = {
  getScanTasks: vi.fn(),
  getStrategy2Tasks: vi.fn(),
  getStrategy3Tasks: vi.fn(),
  reEvaluateTask: vi.fn(),
  reEvaluateStrategy2Task: vi.fn(),
  reEvaluateStrategy3Task: vi.fn(),
  getSchedulerLogs: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import TaskCenter from '../TaskCenter.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('TaskCenter scheduler logs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getScanTasks.mockResolvedValue({ tasks: [] })
    api.getStrategy2Tasks.mockResolvedValue({ tasks: [] })
    api.getStrategy3Tasks.mockResolvedValue({ tasks: [] })
    api.getSchedulerLogs.mockResolvedValue({
      scheduler: {
        enabled: true,
        serial_dual_scan: {
          enabled: true,
          cron: '50 15 * * 1-5',
          strategy1_failed_retry_rounds: 3,
        },
      },
      runtime: {
        running: true,
        jobs: [
          {
            id: 'serial_dual_strategy_scan',
            next_run_time: '2026-06-17 15:50:00',
          },
        ],
      },
      events: [
        {
          time: '2026-06-16 15:15:00',
          level: 'info',
          stage: 'strategy1_full',
          task_id: 'sched-s1-1',
          message: '策略1全量扫描开始',
          details: { stocks: 5000 },
        },
        {
          time: '2026-06-16 15:20:00',
          level: 'warning',
          stage: 'strategy1_remaining_failed',
          task_id: 'sched-s1-1',
          message: '策略1重试后仍有失败股票',
          details: { remaining_failed: 2 },
        },
      ],
    })
  })

  it('shows scheduler config and recent scheduler events', async () => {
    const wrapper = mount(TaskCenter)
    await flushUi()

    expect(api.getSchedulerLogs).toHaveBeenCalled()
    expect(wrapper.text()).toContain('定时任务日志')
    expect(wrapper.text()).toContain('配置已启用')
    expect(wrapper.text()).toContain('实际运行中')
    expect(wrapper.text()).toContain('串行三策略：开启')
    expect(wrapper.text()).toContain('50 15 * * 1-5')
    expect(wrapper.text()).toContain('下次 2026-06-17 15:50:00')
    expect(wrapper.text()).toContain('重试 3 轮')
    expect(wrapper.text()).toContain('策略1全量扫描开始')
    expect(wrapper.text()).toContain('策略1重试后仍有失败股票')
    expect(wrapper.text()).toContain('sched-s1-1')
  })
})
