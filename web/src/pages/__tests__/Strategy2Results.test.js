import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy2Tasks: vi.fn(),
  getStrategy2Candidates: vi.fn(),
  getTaskStocks: vi.fn(),
}
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy2Results from '../Strategy2Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function installDownloadMocks() {
  const originalUrl = globalThis.URL
  const createObjectURL = vi.fn(() => 'blob:strategy2')
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

function mountPage(query = {}) {
  return mount(Strategy2Results, {
    global: {
      mocks: { $route: { query } },
      stubs: { RouterLink: true },
    },
  })
}

describe('Strategy2Results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy2Tasks.mockResolvedValue({
      tasks: [{ id: 's2-task', status: 'completed', candidates: 1 }],
    })
    api.getStrategy2Candidates.mockResolvedValue({
      candidates: [{
        code: '000001',
        name: '平安银行',
        total_score: 82,
        level: '重点观察',
        volume_dry_score: 45,
        price_stable_score: 37,
        trend_type: 'UPTREND_OR_SIDEWAYS',
        risk_ratio: 0.045,
        risk_level: '可接受',
        key_support: 9.7,
        stop_loss: 9.31,
        buy_zone_low: 9.8,
        buy_zone_high: 10.1,
        short_term_time_exit_days: 5,
        evaluation_date: '2026-06-25',
      }],
    })
    api.getTaskStocks.mockResolvedValue({ total: 0 })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('exports the current strategy2 candidate list as csv', async () => {
    const wrapper = mountPage({ task: 's2-task' })
    await flushUi()
    const mocks = installDownloadMocks()

    const button = wrapper.find('[data-test="export-candidates"]')
    expect(button.exists()).toBe(true)
    expect(button.text()).toContain('一键导出列表')
    await button.trigger('click')

    expect(mocks.click).toHaveBeenCalled()
    const blob = mocks.createObjectURL.mock.calls[0][0]
    const csv = await blob.text()
    expect(csv).toContain('代码,名称,总分,等级')
    expect(csv).toContain('000001,平安银行,82,重点观察')
  })
})
