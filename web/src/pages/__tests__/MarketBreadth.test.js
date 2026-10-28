import { beforeEach, describe, expect, it, vi } from 'vitest'
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
    estimated_limit_up_count: index === 0 ? null : index + 10,
    estimated_limit_down_count: index === 0 ? null : index + 2,
    estimated_limit_net_count: index === 0 ? null : 8,
    limit_estimate_sample_count: index === 0 ? 0 : 3900,
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
const getTrendSqueezeBreadthHistory = vi.fn().mockResolvedValue({ rows: [] })

vi.mock('../../composables/useApi.js', () => ({
  useApi: () => ({ getMarketBreadthHistory, getTrendSqueezeBreadthHistory }),
}))

import MarketBreadth from '../MarketBreadth.vue'

beforeEach(() => {
  vi.clearAllMocks()
  chartMocks.charts.length = 0
  getMarketBreadthHistory.mockReset().mockResolvedValue({ meta: {}, rows })
  getTrendSqueezeBreadthHistory.mockReset().mockResolvedValue({ rows: [] })
})

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
    expect(wrapper.text()).toContain('最近5个交易日')
    expect(wrapper.text()).toContain('最近20日市场宽度')
    expect(wrapper.text()).toContain('显示策略6信号')
    expect(wrapper.text()).toContain('不参与策略6评分或过滤')
    expect(wrapper.text()).not.toContain('tickflow')
    expect(wrapper.find('[data-test="breadth-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="index-chart"]').exists()).toBe(true)
    expect(chartMocks.init).toHaveBeenCalledTimes(3)
    expect(chartMocks.connect).toHaveBeenCalled()
    expect(chartMocks.charts[0].setOption).toHaveBeenCalled()
    expect(chartMocks.charts[1].setOption).toHaveBeenCalled()
    expect(getTrendSqueezeBreadthHistory).not.toHaveBeenCalled()
    expect(chartMocks.charts[0].setOption).toHaveBeenCalledTimes(2) // One render per progressive snapshot.

    const breadthOption = chartMocks.charts[0].setOption.mock.calls.at(-1)[0]
    const indexOption = chartMocks.charts[1].setOption.mock.calls.at(-1)[0]
    const tooltip = breadthOption.tooltip.formatter([{ dataIndex: 9 }])
    expect(indexOption.tooltip.show).toBe(false)
    expect(tooltip).toContain('color:#e75b5b')
    expect(tooltip).toContain('color:#20ad72')
    expect(tooltip).toContain('color:#e6a23c')
    expect(wrapper.text()).toContain('涨跌停家数（本地估算）')
    expect(wrapper.get('[data-test="limit-up-estimate"]').text()).toContain('19')
    expect(wrapper.get('[data-test="limit-down-estimate"]').text()).toContain('11')
    const limitOption = chartMocks.charts[2].setOption.mock.calls.at(-1)[0]
    expect(limitOption.series[0].data[0]).toBeNull()
    expect(limitOption.series[0].data.at(-1)).toBe(19)
    expect(limitOption.series[1].data.at(-1)).toBe(11)
    expect(limitOption.tooltip.showContent).toBe(false)
    expect(tooltip).toContain('估算涨停')
    expect(tooltip).toContain('估算跌停')
    expect(limitOption.xAxis.data).toEqual(indexOption.xAxis.data)

    wrapper.unmount()
  })

  it('shows the recent snapshot while complete history is pending and ignores a late unmounted response', async () => {
    let finish
    getMarketBreadthHistory.mockResolvedValueOnce({ rows }).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const wrapper = mount(MarketBreadth)
    await flushPromises()
    expect(getMarketBreadthHistory.mock.calls.map(([params]) => params.limit)).toEqual([30, 1500])
    expect(wrapper.text()).toContain('市场偏弱')
    expect(wrapper.text()).toContain('正在补齐完整历史')
    expect(chartMocks.charts[0].setOption).toHaveBeenCalledTimes(1)
    expect(getTrendSqueezeBreadthHistory).not.toHaveBeenCalled()
    wrapper.unmount()
    finish({ rows: reliableRows })
    await flushPromises()
    expect(chartMocks.charts[0].setOption).toHaveBeenCalledTimes(1)
    expect(chartMocks.charts[0].dispose).toHaveBeenCalledTimes(1)
  })

  it('keeps recent data when complete history fails and allows retry without hiding charts', async () => {
    getMarketBreadthHistory.mockResolvedValueOnce({ rows }).mockRejectedValueOnce(new Error('完整历史暂不可用'))
    const wrapper = mount(MarketBreadth)
    await flushPromises()
    expect(wrapper.text()).toContain('完整历史加载失败')
    expect(wrapper.text()).toContain('市场偏弱')
    expect(wrapper.find('[data-test="breadth-chart"]').exists()).toBe(true)
    await wrapper.get('[data-test="retry-breadth-history"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('完整历史加载失败')
    expect(wrapper.find('[data-test="breadth-chart"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
