import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const chartMocks = vi.hoisted(() => {
  const charts = []
  const init = vi.fn(() => {
    const chart = { setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), group: null }
    charts.push(chart)
    return chart
  })
  return { charts, init, connect: vi.fn(), disconnect: vi.fn() }
})

vi.mock('echarts', () => ({
  init: chartMocks.init,
  connect: chartMocks.connect,
  disconnect: chartMocks.disconnect,
}))

const rates = [0.62, 0.58, 0.55, 0.51, 0.48, 0.45, 0.42, 0.39, 0.37, 0.35]
const reliableRows = rates.map((rate, index) => {
  const upCount = Math.round(rate * 4000)
  const date = `2026-01-${String(index + 2).padStart(2, '0')}`
  return {
    date,
    previousTradeDate: index ? `2026-01-${String(index + 1).padStart(2, '0')}` : '2025-12-31',
    upCount,
    downCount: 4000 - upCount,
    flatCount: 100,
    validCount: 4100,
    unavailableCount: 900,
    coverage: 0.91,
    dataQuality: 'RELIABLE',
    indexes: {
      sh000001: { name: '上证指数', close: 3200.5 + index, dailyReturn: index === 9 ? 0.01 : 0.001 },
      sz399001: { name: '深证成指', close: 10000 + index, dailyReturn: 0.002 },
      sz399006: { name: '创业板指', close: 2100 + index, dailyReturn: -0.001 },
      hs300: { name: '沪深300', close: 3900 + index, dailyReturn: 0.003 },
    },
    strategy6Signal: index === 9
      ? { taskId: 's6-20260111-153000', total: 2, keyCount: 1, watchCount: 1, stocks: [] }
      : null,
  }
})
const rows = [
  ...reliableRows,
  {
    ...reliableRows.at(-1),
    date: '2026-01-12',
    upCount: 3600,
    downCount: 400,
    dataQuality: 'LOW_COVERAGE',
  },
]

const getMarketBreadthHistory = vi.fn().mockResolvedValue({
  meta: {
    dataMode: 'CURRENT_UNIVERSE_RECONSTRUCTION',
    affectsStrategy6: false,
    warning: '当前股票池历史重建，存在幸存者偏差',
  },
  rows,
})

vi.mock('../../composables/useApi.js', () => ({
  useApi: () => ({ getMarketBreadthHistory }),
}))

import MarketBreadth from '../MarketBreadth.vue'

describe('MarketBreadth', () => {
  it('shows conclusion-first breadth analysis and linked research charts', async () => {
    const wrapper = mount(MarketBreadth, { attachTo: document.body })
    await flushPromises()
    await flushPromises()

    expect(wrapper.text()).toContain('市场偏弱')
    expect(wrapper.text()).toContain('上涨占比')
    expect(wrapper.text()).toContain('35.0%')
    expect(wrapper.text()).toContain('2026-01-11')
    expect(wrapper.text()).not.toContain('2026-01-12')
    expect(wrapper.text()).toContain('MA5')
    expect(wrapper.text()).toContain('明显转弱')
    expect(wrapper.text()).toContain('指数虚强')
    expect(wrapper.text()).toContain('四指数综合')
    expect(wrapper.text()).toContain('最近5个交易日')
    expect(wrapper.text()).toContain('最近20日市场宽度')
    expect(wrapper.text()).toContain('显示策略6信号')
    expect(wrapper.text()).toContain('不参与策略6评分或过滤')
    expect(wrapper.text()).not.toContain('tickflow')
    expect(wrapper.find('[data-test="breadth-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="index-chart"]').exists()).toBe(true)
    expect(chartMocks.init).toHaveBeenCalledTimes(2)
    expect(chartMocks.connect).toHaveBeenCalled()
    expect(chartMocks.charts[0].setOption).toHaveBeenCalled()
    expect(chartMocks.charts[1].setOption).toHaveBeenCalled()

    const breadthOption = chartMocks.charts[0].setOption.mock.calls.at(-1)[0]
    const indexOption = chartMocks.charts[1].setOption.mock.calls.at(-1)[0]
    const tooltip = breadthOption.tooltip.formatter([{ dataIndex: 9 }])
    expect(indexOption.tooltip.show).toBe(false)
    expect(tooltip).toContain('color:#e75b5b')
    expect(tooltip).toContain('color:#20ad72')
    expect(tooltip).toContain('color:#e6a23c')
    expect(tooltip).toContain('四指数综合')
    expect(tooltip).toContain('上证指数')
    expect(tooltip).toContain('深证成指')
    expect(tooltip).toContain('创业板指')
    expect(tooltip).toContain('沪深300')

    await wrapper.findAll('.index-grid button')[2].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('指数虚强')
    expect(wrapper.text()).toContain('市场偏弱')

    wrapper.unmount()
  })
})
