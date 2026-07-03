import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy4Tasks: vi.fn(),
  getStrategy4Topics: vi.fn(),
  getStrategy4Leaders: vi.fn(),
  getStrategy4Candidates: vi.fn(),
  getStrategy4Candidate: vi.fn(),
  getStrategy4TrackedTopics: vi.fn(),
  getStrategy4TrackedLeaders: vi.fn(),
  getStrategy4TrackingEvents: vi.fn(),
}
const replace = vi.fn()

vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { task: 's4-track' } }),
  useRouter: () => ({ replace }),
}))

import Strategy4Results from '../Strategy4Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('Strategy4Results tracking pool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy4Tasks.mockResolvedValue({ tasks: [{ id: 's4-track', status: 'completed' }] })
    api.getStrategy4Topics.mockResolvedValue({ topics: [] })
    api.getStrategy4Leaders.mockResolvedValue({ leaders: [] })
    api.getStrategy4Candidates.mockResolvedValue({
      candidates: [{
        topic_id: 'concept-ai',
        topic_name: 'AI算力',
        code: '300750',
        name: '宁德时代',
        status: 'BUYABLE_SECOND_WAVE',
        strategy4_score: 88,
        candidate_origin: 'tracking_pool',
        tracking_topic_status: 'SECOND_WAVE_WATCH',
        tracking_leader_status: 'SECOND_WAVE_READY',
        tracking_age_days: 30,
        tracking_phase: 'golden_second_wave',
        reward_risk_ratio: 2.4,
      }],
    })
    api.getStrategy4TrackedTopics.mockResolvedValue({
      topics: [{
        topic_id: 'concept-ai',
        topic_name: 'AI算力',
        tracking_status: 'SECOND_WAVE_WATCH',
        tracking_phase: 'golden_second_wave',
        age_calendar_days: 30,
      }],
    })
    api.getStrategy4TrackedLeaders.mockResolvedValue({
      leaders: [{
        topic_id: 'concept-ai',
        topic_name: 'AI算力',
        code: '300750',
        name: '宁德时代',
        tracking_status: 'SECOND_WAVE_READY',
        tracking_phase: 'golden_second_wave',
        reward_risk_ratio: 2.4,
      }],
    })
    api.getStrategy4TrackingEvents.mockResolvedValue({ events: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows tracking pool tab and labels tracking candidates clearly', async () => {
    const wrapper = mount(Strategy4Results)
    await flushUi()

    expect(wrapper.text()).toContain('跟踪池')
    expect(wrapper.text()).toContain('跟踪池二波')
    expect(wrapper.text()).toContain('SECOND_WAVE_READY')
    expect(api.getStrategy4TrackedTopics).toHaveBeenCalled()
    expect(api.getStrategy4TrackedLeaders).toHaveBeenCalled()
  })
})
