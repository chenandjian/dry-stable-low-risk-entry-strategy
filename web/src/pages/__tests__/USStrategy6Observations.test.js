import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import USStrategy6Observations from '../USStrategy6Observations.vue'

afterEach(() => vi.unstubAllGlobals())

it('shows research candidates and separately tracks an earlier breakout without marking it invalid', async () => {
  const fetchMock = vi.fn(async url => ({ ok: true, json: async () => ({
    as_of: '2026-11-06', latest_evaluation_date: '2026-11-06', total: 1, page: 1, page_size: 50,
    rows: url.includes('view=vcp') ? [{
      symbol: 'AAPL.US', status: 'VCP_BREAKOUT_CONFIRMED', first_seen_date: '2026-11-04',
      last_seen_date: '2026-11-05', last_evaluation_date: '2026-11-05', breakout_date: '2026-11-05',
      updated_on_date: false, confirmed_days: 2,
    }] : [{ symbol: 'BRK.B.US', status: 'NEW', total_score: 73, first_seen_date: '2026-11-06' }],
  }) }))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(USStrategy6Observations)
  await flushPromises()
  expect(wrapper.text()).toContain('BRK.B.US')
  expect(wrapper.text()).toContain('新入池')
  await wrapper.get('[data-test="us-pool-vcp"]').trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('AAPL.US')
  expect(wrapper.text()).toContain('突破确认')
  expect(wrapper.text()).toContain('评估日未更新')
  expect(wrapper.text()).not.toContain('BRK.B.US')
  expect(fetchMock.mock.calls.every(([url]) => url.startsWith('/api/us/strategy6/observations?'))).toBe(true)
  wrapper.unmount()
})
