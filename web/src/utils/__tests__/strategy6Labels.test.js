import { describe, expect, it } from 'vitest'

import { strategy6Label, strategy6Labels } from '../strategy6Labels.js'

describe('strategy6Labels', () => {
  it('translates known strategy6 business enums by context', () => {
    expect(strategy6Label('candidateType', 'READY_CANDIDATE')).toBe('就绪候选')
    expect(strategy6Label('lifecycleStatus', 'BUY_ZONE')).toBe('买入区间')
    expect(strategy6Label('startType', 'VOLUME_LIMIT_UP')).toBe('放量涨停启动')
    expect(strategy6Label('supportStatus', 'MA20_SUPPORT')).toBe('MA20支撑')
    expect(strategy6Label('marketStatus', 'MARKET_WEAK')).toBe('市场偏弱')
    expect(strategy6Label('tailPath', 'BOX')).toBe('稳定箱体路径')
    expect(strategy6Label('boxStatus', 'BOX_SUPPORT_READY')).toBe('箱体下沿支撑就绪')
    expect(strategy6Label('priceBasis', 'FORWARD_ADJUSTED')).toBe('前复权')
  })

  it('translates tags, dynamic reasons and market snapshot reasons', () => {
    expect(strategy6Label('tag', 'NEAR_120D_PRESSURE')).toBe('接近120日压力位')
    expect(strategy6Label('tag', 'RR2_LT_1_5')).toBe('RR2低于1.5')
    expect(strategy6Label('tag', 'strong=8')).toBe('强势启动得分=8')
    expect(strategy6Label('marketReason', 'above_ma20=2')).toBe('收盘位于MA20上方的指数数=2')
    expect(strategy6Label('marketReason', 'MARKET_DATA_UNAVAILABLE')).toBe('市场数据不可用')
    expect(strategy6Label('marketReason', 'MARKET_DATA_PARTIAL')).toBe('市场指数数据不完整')
    expect(strategy6Label('marketReason', 'observed_indexes=1')).toBe('有效指数数量=1')
    expect(strategy6Labels('executionNote', ['NEXT_TRADING_DAY_ONLY', 'T1_STOP_UNAVAILABLE_ON_BUY_DAY']))
      .toEqual(['仅限下一交易日执行', '买入当日T+1限制下无法止损'])
  })

  it('preserves technical abbreviations and unknown future values', () => {
    expect(strategy6Label('patternType', 'VCP')).toBe('VCP')
    expect(strategy6Label('startGrade', 'S')).toBe('S')
    expect(strategy6Label('tag', 'FUTURE_NEW_REASON')).toBe('FUTURE_NEW_REASON')
    expect(strategy6Label('marketReason', 'future_market_reason')).toBe('future_market_reason')
    expect(strategy6Label('candidateType', null)).toBe('--')
    expect(strategy6Labels('tag', null)).toEqual([])
  })
})
