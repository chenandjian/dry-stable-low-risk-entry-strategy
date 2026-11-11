import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))
import USStrategy6Research from '../USStrategy6Research.vue'

describe('USStrategy6Research', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(async url => ({ ok: true, json: async () => ({ tasks: [] }) })))
  })

  it('is explicit research-only and never fetches market bars on mount', async () => {
    const wrapper = mount(USStrategy6Research)
    await flushPromises()
    expect(wrapper.text()).toContain('未启用市场过滤')
    expect(wrapper.text()).toContain('估算成交额')
    const links = wrapper.get('[aria-label="美股研究快捷入口"]').findAll('a')
    expect(links.map(link => link.attributes('href'))).toEqual([
      '/us/strategy6/batch-evaluation', '/us/strategy6/observations',
    ])
    expect(links[0].classes()).toContain('primary-action')
    expect(wrapper.get('[data-test="scope"]').element.value).toBe('universe')
    expect(wrapper.get('[data-test="start"]').element.disabled).toBe(false)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(fetch.mock.calls.map(([url]) => url)).toContain('/api/us/strategy6/tasks')
    expect(fetch.mock.calls.map(([url]) => url)).toContain('/api/us/data/universe')
    wrapper.unmount()
  })

  it('probes one explicitly selected symbol and shows provider coverage', async () => {
    const wrapper = mount(USStrategy6Research)
    await flushPromises()
    expect(fetch.mock.calls.some(([url]) => url.endsWith('/provider-freshness'))).toBe(false)
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({
      symbol: 'BRK.B.US', status: 'TARGET_MISSING', target_trade_date: '2026-11-06', latest_date: '2026-11-05',
    }) })
    expect(wrapper.get('[data-test="probe-symbol"]').element.value).toBe('AAPL')
    await wrapper.get('[data-test="probe-symbol"]').setValue('BRK.B')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetch).toHaveBeenLastCalledWith('/api/us/data/provider-freshness', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ symbol: 'BRK.B' }),
    }))
    expect(wrapper.get('[data-test="probe-result"]').text()).toContain('未覆盖目标日')
    expect(wrapper.get('[data-test="probe-result"]').text()).toContain('2026-11-05')
    wrapper.unmount()
  })

  it('starts free-only research, shows failure details and saves input separately', async () => {
    fetch.mockImplementation(async (url, options) => ({ ok: true, json: async () => {
      if (options?.method === 'POST') return { task_id: 'us-job' }
      if (url.endsWith('/us-job')) return { task: { task_id: 'us-job', status: 'COMPLETED_WITH_ERRORS',
        context: { target_trade_date: '2026-11-05' },
        progress: { phase: 'FINISHED', processed: 1, total: 1 },
        stocks: [{ symbol: 'AAPL.US', status: 'FAILED', error: 'STALE_OR_UNPUBLISHED' }] } }
      return { tasks: [] }
    } }))
    const wrapper = mount(USStrategy6Research)
    await flushPromises()
    await wrapper.get('[data-test="scope"]').setValue('manual')
    await wrapper.get('textarea').setValue('AAPL\nBRK.B')
    await wrapper.get('[data-test="start"]').trigger('click')
    await flushPromises()
    const post = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
    expect(JSON.parse(post[1].body).symbols).toEqual(['AAPL', 'BRK.B'])
    expect(wrapper.text()).toContain('STALE_OR_UNPUBLISHED')
    expect(wrapper.text()).toContain('AAPL.US')
    expect(localStorage.getItem('strategy6-us-research-symbols')).toBe('AAPL\nBRK.B')
    wrapper.unmount()
  })

  it('ignores an old task response after selecting a different task', async () => {
    let resolveOld
    fetch.mockImplementation(async url => ({ ok: true, json: async () => {
      if (url.endsWith('/tasks')) return { tasks: [{ task_id: 'old' }, { task_id: 'new' }] }
      if (url.endsWith('/old')) return await new Promise(resolve => { resolveOld = resolve })
      return { task: { task_id: 'new', status: 'COMPLETED', stocks: [{ symbol: 'NEW.US', status: 'FAILED', error: 'new failure' }] } }
    } }))
    const wrapper = mount(USStrategy6Research)
    await flushPromises()
    await wrapper.get('[data-test="task-select"]').setValue('new')
    await flushPromises()
    resolveOld({ task: { task_id: 'old', status: 'COMPLETED', stocks: [{ symbol: 'OLD.US' }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('NEW.US')
    expect(wrapper.text()).not.toContain('OLD.US')
    wrapper.unmount()
  })

  it('refreshes the explicit provider pool and starts universe scope without copying codes to textarea', async () => {
    fetch.mockImplementation(async (url, options) => ({ ok: true, json: async () => {
      if (url.includes('/universe')) return { universe: { usable_count: 12412, provider_count: 12412,
        snapshot_id: options?.method === 'POST' ? 'refreshed' : 'cached',
        source: 'tickflow_free', universe_id: 'US_Equity', preview: ['AAPL.US'] } }
      if (options?.method === 'POST') return { task_id: 'full-job' }
      if (url.includes('/full-job')) return { task: { task_id: 'full-job', status: 'COMPLETED', stocks: [],
        pagination: { page: 1, pages: 5, total: 245 } } }
      return { tasks: [] }
    } }))
    const wrapper = mount(USStrategy6Research)
    await flushPromises()
    expect(wrapper.text()).toContain('12412')
    await wrapper.get('[data-test="refresh-pool"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="start"]').trigger('click')
    await flushPromises()
    const post = fetch.mock.calls.find(([url, options]) => url.endsWith('/research') && options?.method === 'POST')
    expect(JSON.parse(post[1].body).scope).toBe('universe')
    expect(JSON.parse(post[1].body).universe_snapshot_id).toBeNull()
    expect(fetch.mock.calls.filter(([url]) => url.endsWith('/universe/refresh'))).toHaveLength(1)
    await wrapper.get('[data-test="next-page"]').trigger('click')
    await flushPromises()
    expect(fetch.mock.calls.some(([url]) => url.includes('page=2'))).toBe(true)
    wrapper.unmount()
  })
})
