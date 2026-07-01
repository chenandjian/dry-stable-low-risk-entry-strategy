import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, nextTick } from 'vue'

const mockRoute = reactive({ query: { task_id: 's1-task' } })
const mockRouter = { push: vi.fn() }
vi.mock('vue-router', () => ({ useRoute: () => mockRoute, useRouter: () => mockRouter }))

const api = {
  getScanTasks: vi.fn(),
  getCandidates: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import ResultsRadar from '../ResultsRadar.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function installDownloadMocks() {
  const originalUrl = globalThis.URL
  const createObjectURL = vi.fn(() => 'blob:strategy1')
  const revokeObjectURL = vi.fn()
  const click = vi.fn()
  vi.stubGlobal('URL', { ...originalUrl, createObjectURL, revokeObjectURL })
  const originalCreateElement = document.createElement.bind(document)
  vi.spyOn(document, 'createElement').mockImplementation(tag => {
    const el = originalCreateElement(tag)
    if (tag === 'a') vi.spyOn(el, 'click').mockImplementation(click)
    return el
  })
  return { createObjectURL, click }
}

describe('ResultsRadar export', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRoute.query = { task_id: 's1-task' }
    api.getScanTasks.mockResolvedValue({
      tasks: [{ id: 's1-task', status: 'completed', candidates: 2, date: '2026-06-25' }],
    })
    api.getCandidates.mockResolvedValue({
      candidates: [
        {
          code: '000001',
          name: '平安银行',
          score: 85,
          pattern_type: '杯柄',
          dry_stable_verdict: '可低吸',
          volume_dry_score: 9,
          price_stable_score: 8,
          rr1: 2.1,
          position_advice: '轻仓',
          market_status: '良好',
          is_breakout: false,
          is_volume_breakout: true,
          latest_close: 10.12,
          pivot: 10.5,
          cup_depth_pct: 18.5,
          handle_depth_pct: 7.2,
          cup_duration: 80,
          vol_multiplier: 1.6,
        },
        {
          code: '000002',
          name: '万科A',
          score: 72,
          pattern_type: 'VCP',
        },
      ],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('exports the currently filtered strategy1 candidate list', async () => {
    const wrapper = mount(ResultsRadar, {
      global: {
        stubs: {
          MetricCard: { props: ['label', 'value'], template: '<div>{{ label }} {{ value }}</div>' },
          SignalBadge: { template: '<span><slot /></span>' },
        },
      },
    })
    await flushUi()
    await wrapper.findAll('button').find(b => b.text() === 'A级 ≥80').trigger('click')
    const mocks = installDownloadMocks()

    const button = wrapper.find('[data-test="export-candidates"]')
    expect(button.exists()).toBe(true)
    expect(button.text()).toContain('一键导出列表')
    await button.trigger('click')

    expect(mocks.click).toHaveBeenCalled()
    const csv = await mocks.createObjectURL.mock.calls[0][0].text()
    expect(csv).toContain('000001,平安银行,85')
    expect(csv).not.toContain('000002,万科A,72')
  })
})
