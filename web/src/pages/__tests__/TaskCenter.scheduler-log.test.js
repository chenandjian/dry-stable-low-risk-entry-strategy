import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const mockRouter = { push: vi.fn() }
vi.mock('vue-router', () => ({ useRouter: () => mockRouter }))

const api = {
  getStrategy6Tasks: vi.fn(),
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

describe('Strategy6 task center', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy6Tasks.mockResolvedValue({
      tasks: [{
        id: 's6-20260730-151500',
        date: '2026-07-30 15:15:00',
        status: 'completed',
        candidates: 3,
        failed: 1,
      }],
    })
    api.getSchedulerLogs.mockResolvedValue({
      scheduler: {
        enabled: true,
        serial_dual_scan: { enabled: true, cron: '15 15 * * 1-5' },
      },
      runtime: {
        running: true,
        jobs: [{ id: 'strategy6_scan', next_run_time: '2026-07-31 15:15:00' }],
      },
      events: [{
        time: '2026-07-30 15:15:00',
        level: 'info',
        stage: 'strategy6_full',
        task_id: 'sched-s6-20260730-151500',
        message: '策略6定时扫描开始',
      }],
    })
  })

  it('loads only Strategy6 tasks and scheduler state', async () => {
    const wrapper = mount(TaskCenter)
    await flushUi()

    expect(api.getStrategy6Tasks).toHaveBeenCalled()
    expect(wrapper.text()).toContain('策略6扫描任务')
    expect(wrapper.text()).toContain('策略6定时扫描：开启')
    expect(wrapper.text()).toContain('s6-20260730-151500')
    expect(wrapper.text()).toContain('策略6定时扫描开始')
    expect(wrapper.text()).not.toContain('串行三策略')
    expect(wrapper.text()).not.toContain('策略1')
    expect(wrapper.text()).not.toContain('策略2')
    expect(wrapper.text()).not.toContain('策略3')
    expect(wrapper.text()).not.toContain('策略4')
    expect(wrapper.text()).not.toContain('策略5')
  })

  it('opens Strategy6 results for the selected task', async () => {
    const wrapper = mount(TaskCenter)
    await flushUi()
    await wrapper.find('.action-btn').trigger('click')
    expect(mockRouter.push).toHaveBeenCalledWith('/strategy6/results?task=s6-20260730-151500')
  })
})
