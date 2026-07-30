import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockRoute = { path: '/strategy6/results' }

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
}))

import TopNav from '../TopNav.vue'

function mountNav() {
  return mount(TopNav, {
    global: {
      stubs: {
        RouterLink: {
          props: ['to'],
          template: '<a :href="to"><slot /></a>',
        },
      },
    },
  })
}

describe('TopNav', () => {
  beforeEach(() => {
    mockRoute.path = '/strategy6/results'
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ tasks: [] }),
    })
  })

  it('shows only the Strategy6 business navigation', () => {
    const wrapper = mountNav()

    const strategy6Tab = wrapper.findAll('a').find(a => a.text() === '策略6候选')
    expect(strategy6Tab).toBeTruthy()
    expect(strategy6Tab.attributes('href')).toBe('/strategy6/results')
    expect(strategy6Tab.classes()).toContain('active')
    expect(wrapper.text()).not.toContain('策略1')
    expect(wrapper.text()).not.toContain('策略2')
    expect(wrapper.text()).not.toContain('策略3')
    expect(wrapper.text()).not.toContain('策略4')
    expect(wrapper.text()).not.toContain('策略5')
  })
})
