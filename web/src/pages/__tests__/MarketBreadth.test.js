import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getMarketBreadthHistory = vi.fn().mockResolvedValue({
  meta: {
    dataMode: 'CURRENT_UNIVERSE_RECONSTRUCTION',
    affectsStrategy6: false,
    warning: '当前股票池历史重建，存在幸存者偏差',
  },
  summary: {
    date: '2026-01-06', upCount: 1000, downCount: 3000, flatCount: 100,
    validCount: 4100, unavailableCount: 900, downRatio: 3000 / 4100,
    breadth: -2000 / 4100, breadthState: 'BROAD_DECLINE',
  },
  rows: [{
    date: '2026-01-06', previousTradeDate: '2026-01-05', upCount: 1000,
    downCount: 3000, flatCount: 100, validCount: 4100, unavailableCount: 900,
    downRatio: 3000 / 4100, breadth: -2000 / 4100, breadthState: 'BROAD_DECLINE',
    indexes: {
      sh000001: { name: '上证指数', close: 3200, dailyReturn: -0.01, source: 'tickflow' },
      sz399001: { name: '深证成指', close: 10000, dailyReturn: -0.02, source: 'tickflow' },
      sz399006: { name: '创业板指', close: 2100, dailyReturn: -0.03, source: 'tickflow' },
      hs300: { name: '沪深300', close: 3900, dailyReturn: -0.012, source: 'tickflow' },
    },
    strategy6Signal: {
      taskId: 's6-20260106-153000', total: 2, keyCount: 1, watchCount: 1,
      stocks: [{ code: '000001', name: '平安银行', candidateType: 'KEY_CANDIDATE' }],
    },
  }],
})

vi.mock('../../composables/useApi.js', () => ({
  useApi: () => ({ getMarketBreadthHistory }),
}))

import MarketBreadth from '../MarketBreadth.vue'

describe('MarketBreadth', () => {
  it('shows breadth, four real indexes and recorded strategy6 signals as research only', async () => {
    const wrapper = mount(MarketBreadth)
    await flushPromises()

    expect(wrapper.text()).toContain('市场宽度与策略信号')
    expect(wrapper.text()).toContain('下跌 3000')
    expect(wrapper.text()).toContain('上证指数')
    expect(wrapper.text()).toContain('深证成指')
    expect(wrapper.text()).toContain('创业板指')
    expect(wrapper.text()).toContain('沪深300')
    expect(wrapper.text()).toContain('s6-20260106-153000')
    expect(wrapper.text()).toContain('当前股票池历史重建，存在幸存者偏差')
    expect(wrapper.text()).toContain('不参与策略6评分或过滤')
    expect(wrapper.find('[aria-label="四个指数同日涨跌幅"]').exists()).toBe(true)
  })
})
