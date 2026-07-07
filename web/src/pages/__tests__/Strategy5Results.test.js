import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = {
  getStrategy5Tasks: vi.fn(),
  getStrategy5Candidates: vi.fn(),
}

vi.mock('../../composables/useApi.js', () => ({ useApi: () => api }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { task: 's5-task' } }),
  useRouter: () => ({ replace: vi.fn() }),
}))

import Strategy5Results from '../Strategy5Results.vue'

async function flushUi() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

describe('Strategy5Results', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.getStrategy5Tasks.mockResolvedValue({ tasks: [{ id: 's5-task', status: 'completed', candidates: 2 }] })
    api.getStrategy5Candidates.mockResolvedValue({
      candidates: [
        {
          code: '000001',
          name: '平安银行',
          candidate_type: 'KEY_CANDIDATE',
          classification: 'highlight',
          total_score: 88,
          close: 12.345,
          avg_turnover_60d: 36.78,
          recent_20d_return: 0.25,
          amplitude_5d: 0.08,
          amplitude_10d: 0.16,
          support_status: 'SPRINT_MA5_SUPPORT',
          main_support_ma: 'MA5',
          support_score: 9,
          strength_trigger: 'ret_20d',
          high_trigger: 'new_120d_high',
          kline_latest_date: '2026-07-07',
          risk_tags: [],
          warn_tags: ['LOW_5D_VOLATILITY'],
        },
        {
          code: '000002',
          name: '万科A',
          candidate_type: 'WATCH_CANDIDATE',
          classification: 'observe',
          total_score: 72,
          support_status: 'SPRINT_MA50_TESTING',
          main_support_ma: 'MA50',
          support_score: 4,
          strength_trigger: 'single_day_surge',
          high_trigger: 'near_120d_high',
          risk_tags: ['BIG_DROP_TODAY'],
          warn_tags: ['EXTREME_PULLBACK_OBSERVE'],
        },
      ],
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders key and watch candidates with support and trigger fields', async () => {
    const wrapper = mount(Strategy5Results)
    await flushUi()

    expect(wrapper.text()).toContain('策略5')
    expect(wrapper.text()).toContain('KEY_CANDIDATE')
    expect(wrapper.text()).toContain('WATCH_CANDIDATE')
    expect(wrapper.text()).toContain('SPRINT_MA5_SUPPORT')
    expect(wrapper.text()).toContain('SPRINT_MA50_TESTING')
    expect(wrapper.text()).toContain('ret_20d')
    expect(wrapper.text()).toContain('near_120d_high')
    expect(wrapper.text()).toContain('EXTREME_PULLBACK_OBSERVE')
  })

  it('renders full strategy5 candidate fields returned by the API', async () => {
    const wrapper = mount(Strategy5Results)
    await flushUi()

    expect(wrapper.text()).toContain('收盘')
    expect(wrapper.text()).toContain('12.35')
    expect(wrapper.text()).toContain('60日成交额')
    expect(wrapper.text()).toContain('36.78')
    expect(wrapper.text()).toContain('20日涨幅')
    expect(wrapper.text()).toContain('25.00%')
    expect(wrapper.text()).toContain('5/10日振幅')
    expect(wrapper.text()).toContain('8.00% / 16.00%')
    expect(wrapper.text()).toContain('数据日')
    expect(wrapper.text()).toContain('2026-07-07')
  })
})
