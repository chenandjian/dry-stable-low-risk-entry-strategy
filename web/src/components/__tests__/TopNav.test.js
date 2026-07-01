import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockRoute = { path: '/strategy3/results' }

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
    mockRoute.path = '/strategy3/results'
    global.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ tasks: [] }),
    })
  })

  it('shows a dedicated strategy3 candidate tab', () => {
    const wrapper = mountNav()

    const strategy3Tab = wrapper.findAll('a').find(a => a.text() === '策略3候选')
    expect(strategy3Tab).toBeTruthy()
    expect(strategy3Tab.attributes('href')).toBe('/strategy3/results')
    expect(strategy3Tab.classes()).toContain('active')
  })
})
