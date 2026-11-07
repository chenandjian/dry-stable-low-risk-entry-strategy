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
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][0]).toBe('/api/us/strategy6/tasks')
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
    await wrapper.get('select').setValue('new')
    await flushPromises()
    resolveOld({ task: { task_id: 'old', status: 'COMPLETED', stocks: [{ symbol: 'OLD.US' }] } })
    await flushPromises()
    expect(wrapper.text()).toContain('NEW.US')
    expect(wrapper.text()).not.toContain('OLD.US')
    wrapper.unmount()
  })
})
