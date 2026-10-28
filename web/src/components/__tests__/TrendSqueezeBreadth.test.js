import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
const mocks = vi.hoisted(() => ({ api: vi.fn(), chart: { setOption: vi.fn(), getZr: vi.fn(), containPixel: vi.fn(), convertFromPixel: vi.fn(), dispose: vi.fn(), resize: vi.fn() }, on: vi.fn() }))
vi.mock('../../composables/useApi.js', () => ({ useApi: () => ({ getTrendSqueezeBreadthHistory: mocks.api }) }))
vi.mock('echarts', () => ({ init: () => mocks.chart }))
import TrendSqueezeBreadth from '../TrendSqueezeBreadth.vue'

const rows = [1, 2].map(i => ({ date: `2026-09-0${i}`, screen_count: i, strong_count: 20,
  screen_ratio: .01*i, strong_ratio: .1*i, strong_ma5: .09*i, strong_ma20: .08*i, evaluated_count: 1000, eligible_count: 1000, coverage_rate: 1,
  data_quality: 'RELIABLE', screen_change: i === 2 ? 1 : null, screen_ma5: null,
  screen_ma20: null, screen_percentile120: null, environment: '数据不足，暂不判断' }))
beforeEach(() => {
  vi.clearAllMocks()
  mocks.chart.getZr.mockReturnValue({ on: mocks.on })
  mocks.chart.containPixel.mockReturnValue(true)
  mocks.chart.convertFromPixel.mockReturnValue([0, 0])
  mocks.api.mockImplementation(params => Promise.resolve(params.stock_date
    ? { selection: { date: params.stock_date, available: true, stocks: [{ code: params.stock_date.endsWith('01') ? '000001' : '600001', name: '样本' }] } }
    : { rows, meta: { warning: '真实历史重建', pool_count: 1200, stocks_with_history_count: 1100 } }))
})

describe('TrendSqueezeBreadth', () => {
  it('can defer expensive history until the user requests it', async () => {
    const wrapper = mount(TrendSqueezeBreadth, { props: { autoLoad: false, disabled: true } })
    await flushPromises()
    expect(mocks.api).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('本地指数或个股历史不足')
    expect(wrapper.find('header button').element.disabled).toBe(true)
    await wrapper.setProps({ disabled: false })
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(mocks.api).toHaveBeenCalledTimes(2)
    expect(mocks.chart.setOption).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('loads historical metrics, chart and the latest list independently', async () => {
    const wrapper = mount(TrendSqueezeBreadth)
    await flushPromises()
    expect(wrapper.text()).toContain('强势趋势收缩宽度')
    expect(wrapper.text()).toContain('长期强势对照')
    expect(wrapper.text()).toContain('当前股票池 1200只，有本地历史 1100只')
    expect(wrapper.text()).toContain('600001')
    expect(mocks.api).toHaveBeenCalledTimes(2)
    const option = mocks.chart.setOption.mock.calls.at(-1)[0]
    expect(option.xAxis[0].data).toEqual(rows.map(r => r.date))
    expect(option.xAxis[1].data).toEqual(rows.map(r => r.date))
    expect(option.series[0].data).toEqual([1, 2])
    expect(option.series[3].data).toEqual([null, null])
    expect(option.series[2].xAxisIndex).toBe(1)
    expect(option.dataZoom[0].xAxisIndex).toEqual([0, 1, 2])
    expect(option.xAxis[2].data).toEqual(rows.map(r => r.date))
    expect(option.series[5].data).toEqual([10, 20])
    expect(option.series[6].data).toEqual([9, 18])
    expect(option.series[7].data).toEqual([8, 16])
    expect(option.series[5].yAxisIndex).toBe(2)
    expect(wrapper.text()).toContain('长期强势占比 MA5 / MA20')
    expect(option.yAxis[1].min({ min: 1.1, max: 2.1 })).toBeCloseTo(.9)
    expect(option.yAxis[1].max({ min: 1.1, max: 2.1 })).toBeCloseTo(2.3)
    expect(option.tooltip.formatter([{ dataIndex: 0 }])).toContain('1.00%')
    expect(option.tooltip.formatter([{ dataIndex: 0 }])).toContain('10.00%')
    mocks.chart.containPixel.mockImplementation(({ gridIndex }) => gridIndex === 2)
    mocks.on.mock.calls.at(-1)[1]({ offsetX: 100, offsetY: 200 })
    await flushPromises()
    expect(wrapper.get('[data-test="trend-date"]').element.value).toBe('2026-09-01')
    expect(wrapper.text()).toContain('000001')
    expect(mocks.chart.convertFromPixel).toHaveBeenLastCalledWith({ gridIndex: 2 }, [100, 200])
    wrapper.unmount()
    expect(mocks.chart.dispose).toHaveBeenCalled()
  })

  it('selects past dates and prevents late responses overwriting the current list', async () => {
    const wrapper = mount(TrendSqueezeBreadth)
    await flushPromises()
    let resolveOld
    mocks.api.mockImplementation(params => params.stock_date.endsWith('01')
      ? new Promise(resolve => { resolveOld = resolve })
      : Promise.resolve({ selection: { available: true, stocks: [{ code: '600002' }] } }))
    await wrapper.get('[data-test="trend-date"]').setValue('2026-09-01')
    await wrapper.get('[data-test="trend-date"]').setValue('2026-09-02')
    await flushPromises()
    resolveOld({ selection: { available: true, stocks: [{ code: '000009' }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('600002')
    expect(wrapper.text()).not.toContain('000009')
    wrapper.unmount()
  })

  it('keeps low-coverage outliers off the ratio plot and handles an empty ratio axis', async () => {
    const history = [...rows, { ...rows[1], date: '2026-09-03', data_quality: 'LOW_COVERAGE', screen_count: 77, screen_ratio: 1 }]
    mocks.api.mockImplementation(params => Promise.resolve(params.stock_date
      ? { selection: { available: true, stocks: [] } } : { rows: history }))
    const wrapper = mount(TrendSqueezeBreadth)
    await flushPromises()
    const option = mocks.chart.setOption.mock.calls.at(-1)[0]
    expect(option.series[0].data).toEqual([1, 2, 77])
    expect(option.series[2].data).toEqual([1, 2, null])
    expect(option.series[5].data).toEqual([10, 20, null])
    expect(option.series[6].data).toEqual([9, 18, null])
    expect(option.yAxis[1].min({ min: Infinity, max: -Infinity })).toBe(0)
    expect(option.yAxis[1].max({ min: Infinity, max: -Infinity })).toBe(1)
    expect(option.yAxis[1].min({ min: 0, max: 0 })).toBe(0)
    expect(option.yAxis[1].max({ min: 100, max: 100 })).toBe(100)
    wrapper.unmount()
  })

  it('distinguishes missing data from a genuine empty screen', async () => {
    mocks.api.mockImplementation(params => Promise.resolve(params.stock_date
      ? { selection: { available: false, stocks: [] } } : { rows }))
    const wrapper = mount(TrendSqueezeBreadth)
    await flushPromises()
    expect(wrapper.text()).toContain('不能按零机会解释')
    wrapper.unmount()
  })

  it('shows errors with a retry control and reloads the same day list', async () => {
    const wrapper = mount(TrendSqueezeBreadth)
    await flushPromises()
    mocks.api.mockRejectedValueOnce(new Error('行情正在更新'))
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('行情正在更新')
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('行情正在更新')
    expect(mocks.api.mock.calls.filter(([p]) => p.stock_date).length).toBe(2)
    wrapper.unmount()
  })
})
