import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy6Tasks: vi.fn(),
  getStrategy6Candidates: vi.fn(),
}

vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))

import Strategy6Results from '../Strategy6Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('Strategy6Results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy6Tasks.mockResolvedValue({ tasks: [{ id: 's6-task', status: 'completed', candidates: 3 }] })
    api.getStrategy6Candidates.mockResolvedValue({
      candidates: [
        {
          code: '000001',
          name: '平安银行',
          candidate_type: 'READY_CANDIDATE',
          classification: 'ready',
          lifecycle_status: 'BUY_ZONE',
          total_score: 91,
          current_price: 12.34,
          start_type: 'VOLUME_LIMIT_UP',
          start_grade: 'S',
          support_status: 'MA10_SUPPORT',
          key_support_price: 11.8,
          buy_zone_low: 11.8,
          buy_zone_high: 12.2,
          stop_loss_price: 11.45,
          target_price_1: 13.2,
          target_price_2: 14.8,
          target_price_3: 16.5,
          risk_reward_ratio_2: 3.4,
          volume_ratio_5_20: 0.52,
          risk_tags: [],
          warn_tags: ['NEAR_120D_PRESSURE'],
          evaluation_date: '2026-07-09',
        },
        {
          code: '000002',
          name: '万科A',
          candidate_type: 'KEY_CANDIDATE',
          classification: 'key',
          lifecycle_status: 'READY',
          total_score: 82,
          current_price: 8.88,
          start_type: 'NORMAL_STRONG_BREAKOUT',
          start_grade: 'A',
          support_status: 'MA20_SUPPORT',
          key_support_price: 8.4,
          buy_zone_low: 8.4,
          buy_zone_high: 8.65,
          stop_loss_price: 8.1,
          target_price_2: 10.2,
          risk_reward_ratio_2: 2.2,
          volume_ratio_5_20: 0.66,
          risk_tags: ['UPPER_PRESSURE'],
          warn_tags: [],
        },
        {
          code: '000003',
          name: '观察股',
          candidate_type: 'WATCH_CANDIDATE',
          classification: 'watch',
          lifecycle_status: 'SETUP_FORMING',
          total_score: 68,
          support_status: 'MA50_TESTING',
          risk_reward_ratio_2: 1.6,
        },
      ],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders strategy6 ready, key and watch candidates with trade plan fields', async () => {
    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-task' } },
        },
      },
    })
    await flushUi()

    expect(api.getStrategy6Candidates).toHaveBeenCalledWith('s6-task')
    expect(wrapper.text()).toContain('策略6')
    expect(wrapper.text()).toContain('READY_CANDIDATE')
    expect(wrapper.text()).toContain('KEY_CANDIDATE')
    expect(wrapper.text()).toContain('WATCH_CANDIDATE')
    expect(wrapper.text()).toContain('VOLUME_LIMIT_UP / S')
    expect(wrapper.text()).toContain('MA10_SUPPORT')
    expect(wrapper.text()).toContain('11.80 - 12.20')
    expect(wrapper.text()).toContain('止损')
    expect(wrapper.text()).toContain('RR2')
    expect(wrapper.text()).toContain('3.40')
    expect(wrapper.text()).toContain('BUY_ZONE')
    expect(wrapper.text()).toContain('NEAR_120D_PRESSURE')
  })

  it('loads all candidates for a URL task even when task list is stale', async () => {
    api.getStrategy6Tasks.mockResolvedValue({ tasks: [{ id: 's6-other', status: 'completed', candidates: 1 }] })
    const candidates = Array.from({ length: 9 }, (_, idx) => ({
      code: `300${String(idx).padStart(3, '0')}`,
      name: `强VCP${idx}`,
      candidate_type: idx < 2 ? 'READY_CANDIDATE' : idx < 6 ? 'KEY_CANDIDATE' : 'WATCH_CANDIDATE',
      classification: idx < 2 ? 'ready' : idx < 6 ? 'key' : 'watch',
      lifecycle_status: 'READY',
      total_score: 90 - idx,
      start_type: 'VOLUME_LIMIT_UP',
      start_grade: 'A',
      support_status: 'MA20_SUPPORT',
      key_support_price: 10 + idx,
      risk_reward_ratio_2: 2.5,
    }))
    api.getStrategy6Candidates.mockResolvedValue({ candidates })

    const wrapper = mount(Strategy6Results, {
      global: {
        mocks: {
          $route: { query: { task: 's6-20260709-001' } },
        },
      },
    })
    await flushUi()

    expect(api.getStrategy6Candidates).toHaveBeenCalledWith('s6-20260709-001')
    expect(wrapper.text()).toContain('候选数 9')
    expect(wrapper.text()).toContain('就绪 2')
    expect(wrapper.text()).toContain('重点 4')
    expect(wrapper.text()).toContain('观察 3')
    expect(wrapper.findAll('tbody tr')).toHaveLength(9)
  })
})
