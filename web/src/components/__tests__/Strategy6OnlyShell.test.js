import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-router', () => ({ useRoute: () => ({ path: '/' }) }))

import ScanEngine from '../ScanEngine.vue'
import TopNav from '../TopNav.vue'

describe('strategy6-only application shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ tasks: [] }),
    }))
  })

  it('shows only strategy6 navigation entries', () => {
    const wrapper = mount(TopNav, {
      global: {
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
        },
      },
    })

    expect(wrapper.text()).toContain('策略6扫描')
    expect(wrapper.text()).toContain('策略6候选')
    expect(wrapper.text()).not.toContain('策略1')
    expect(wrapper.text()).not.toContain('策略2')
    expect(wrapper.text()).not.toContain('策略3')
    expect(wrapper.text()).not.toContain('策略4')
    expect(wrapper.text()).not.toContain('策略5')
    expect(fetch).toHaveBeenCalledWith('/api/strategy6/tasks')
  })

  it('emits only the strategy6 scan action', async () => {
    const wrapper = mount(ScanEngine, { props: { running: false } })
    const buttons = wrapper.findAll('button')

    expect(buttons).toHaveLength(1)
    expect(buttons[0].text()).toContain('启动策略6扫描')
    await buttons[0].trigger('click')
    expect(wrapper.emitted('startStrategy6')).toHaveLength(1)
    expect(wrapper.emitted('start')).toBeUndefined()
  })
})
