import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ScanEngine from '../ScanEngine.vue'


describe('ScanEngine phased progress', () => {
  it('shows TickFlow batch acquisition progress separately from strategy scanning', () => {
    const wrapper = mount(ScanEngine, {
      props: {
        running: true,
        scanned: 0,
        total: 4994,
        phase: 'data_acquisition',
        dataProcessed: 1200,
        dataTotal: 4994,
        currentCode: '600519',
        currentName: '贵州茅台',
        skipped: 0,
        failed: 0,
        candidates: 0,
      },
    })

    expect(wrapper.text()).toContain('TickFlow 批量行情拉取中')
    expect(wrapper.text()).toContain('已拉取 1200 / 4994')
    expect(wrapper.text()).toContain('当前拉取')
    expect(wrapper.text()).toContain('完成后自动进入策略计算')
    expect(wrapper.text()).not.toContain('已处理 0 / 4994')
  })
})
