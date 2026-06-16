import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = { getKlineHistory: vi.fn() }
vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import KlineHistory from '../KlineHistory.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function freshResponse(overrides = {}) {
  return {
    code: '000831',
    rows: [{ date: '2026-06-16', open: 10, high: 11, low: 9, close: 10.5, volume: 1000, turnover: 10500 }],
    total: 1,
    page: 1,
    page_size: 50,
    summary: {
      latest_kline_date: '2026-06-16',
      latest_fetch_time: '2026-06-16 15:12:00',
      target_trade_date: '2026-06-16',
      min_fetch_time: '2026-06-16 15:00:00',
      is_fresh: true,
      needs_refetch: false,
      quote_status: 'not_requested',
      reason: '数据已覆盖目标完整交易日',
      ...(overrides.summary || {}),
    },
    ...overrides,
  }
}

describe('KlineHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getKlineHistory.mockResolvedValue(freshResponse())
  })

  it('renders freshness summary and kline rows', async () => {
    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(api.getKlineHistory).toHaveBeenCalledWith({
      code: '000831',
      start_date: '',
      end_date: '',
      page: 1,
      page_size: 50,
    })
    expect(wrapper.text()).toContain('个股 K 线数据诊断')
    expect(wrapper.text()).toContain('数据最新')
    expect(wrapper.text()).toContain('最新K线日期')
    expect(wrapper.text()).toContain('2026-06-16')
    expect(wrapper.text()).toContain('10.50')
  })

  it('loads the next page with the current query', async () => {
    api.getKlineHistory
      .mockResolvedValueOnce(freshResponse({ total: 100, page: 1, page_size: 50 }))
      .mockResolvedValueOnce(freshResponse({
        rows: [{ date: '2026-06-15', open: 9, high: 10, low: 8, close: 9.5, volume: 2000, turnover: 19000 }],
        total: 100,
        page: 2,
        page_size: 50,
      }))
    const wrapper = mount(KlineHistory)
    await flushUi()

    await wrapper.find('[data-test="next-page"]').trigger('click')
    await flushUi()

    expect(api.getKlineHistory).toHaveBeenLastCalledWith({
      code: '000831',
      start_date: '',
      end_date: '',
      page: 2,
      page_size: 50,
    })
    expect(wrapper.text()).toContain('2026-06-15')
    expect(wrapper.text()).toContain('9.50')
  })

  it('shows refetch warning when data is stale', async () => {
    api.getKlineHistory.mockResolvedValue(freshResponse({
      summary: {
        is_fresh: false,
        needs_refetch: true,
        reason: '最近拉取时间早于目标交易日收盘时间，需要重新拉取',
      },
    }))

    const wrapper = mount(KlineHistory)
    await flushUi()

    expect(wrapper.text()).toContain('需要重新拉取')
    expect(wrapper.text()).toContain('最近拉取时间早于目标交易日收盘时间')
  })
})
