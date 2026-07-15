const LABELS = {
  taskStatus: {
    pending: '等待中', running: '扫描中', completed: '已完成', failed: '失败',
    interrupted: '已中断', selected: '已选择', canceled: '已取消', cancelled: '已取消',
  },
  candidateType: {
    READY_CANDIDATE: '就绪候选', KEY_CANDIDATE: '重点候选', WATCH_CANDIDATE: '观察候选', REJECTED: '已排除',
  },
  classification: {
    ready: '就绪', key: '重点', highlight: '重点', watch: '观察', observe: '观察', rejected: '已排除',
  },
  lifecycleStatus: {
    START_CONFIRMED: '强势启动已确认', SETUP_FORMING: '结构形成中', READY: '就绪',
    BUY_ZONE: '买入区间', BREAKOUT_CONFIRMED: '突破已确认', EXTENDED: '涨幅已过度延伸',
    FAILED: '结构失效', EXPIRED: '已过期', COOLDOWN: '冷却期',
  },
  vcpStatus: {
    VCP_NONE: '未形成VCP观察结构', VCP_FORMING: 'VCP形成中',
    VCP_NEAR_PIVOT: '接近VCP支点', VCP_BREAKOUT_CONFIRMED: 'VCP突破已确认',
    VCP_POST_BREAKOUT: 'VCP突破后观察', VCP_EXTENDED: '突破后过度延伸',
    VCP_INVALID: 'VCP结构失效',
  },
  entryArchetype: {
    SUPPORT_PULLBACK: '支撑低吸', PIVOT_BREAKOUT: '枢轴突破',
    FAILED_BREAKOUT_RECLAIM: '假跌破收复', WAIT_BREAKOUT: '等待突破', NONE: '无有效入场',
  },
  tailSegmentationStatus: {
    DYNAMIC_CONTRACTION: '动态收缩尾段', FALLBACK_FIXED: '固定窗口回退',
    INSUFFICIENT_BASELINE: '基准数据不足', DISABLED: '动态划分关闭',
  },
  startType: {
    NONE: '未识别强势启动', ONE_WORD_LIMIT_UP: '一字涨停启动', VOLUME_LIMIT_UP: '放量涨停启动',
    LOW_VOLUME_LIMIT_UP: '缩量涨停启动', NORMAL_STRONG_BREAKOUT: '普通强势突破',
    TOUCHED_LIMIT_UP_FAILED: '触及涨停后回落', B_GRADE_MOMENTUM: 'B级动量启动',
  },
  supportStatus: {
    MA5_SUPPORT: 'MA5支撑', MA10_SUPPORT: 'MA10支撑', MA20_SUPPORT: 'MA20支撑',
    PATTERN_SUPPORT: '形态支撑', KEY_SUPPORT_VALID: '关键支撑有效', SUPPORT_FAILED: '支撑失效',
    MA50_TESTING: 'MA50支撑测试中',
  },
  phaseStatus: {
    PHASE_VALID: '阶段有效', START_NOT_FOUND: '未找到强势启动', START_TOO_RECENT: '启动时间过近',
    START_TOO_OLD: '启动时间过早', CONSOLIDATION_TOO_SHORT: '整理周期过短',
    CONSOLIDATION_TOO_LONG: '整理周期过长', PHASE_ORDER_INVALID: '阶段时序无效',
  },
  patternType: { VCP: 'VCP', CUP_HANDLE: '杯柄', PLATFORM: '平台', UNKNOWN: '未识别形态' },
  pivotSource: {
    VCP_LAST_CONTRACTION: 'VCP最后一次收缩', CUP_HANDLE_PIVOT: '杯柄突破枢轴', PLATFORM_TOP: '平台上沿',
  },
  supportSource: {
    MA5: 'MA5', MA10: 'MA10', MA20: 'MA20', PATTERN_LOW: '形态低点', PLATFORM_LOW: '平台低点',
    RECENT_10_CLOSE_LOW: '近10日最低收盘', RECENT_10_LOW: '近10日最低价',
    RECENT_20_CLOSE_LOW: '近20日最低收盘', START_LOW: '启动日低点', ATR: 'ATR',
  },
  tailPath: { ORIGINAL: '原尾段路径', BOX: '稳定箱体路径', BOTH: '双路径同时通过', NONE: '未形成尾段路径' },
  tailPathSummary: {
    ORIGINAL: '原尾段路径', BOX: '稳定箱体路径', BROOKS: 'Brooks价格行为',
    MULTI: '多路径', NONE: '未形成尾段路径',
  },
  tailPrimaryPath: {
    ORIGINAL: '原尾段路径', BOX: '稳定箱体路径', BROOKS: 'Brooks价格行为', NONE: '无主路径',
  },
  brooksStatus: {
    BROOKS_DISABLED: '未启用或旧任务无数据', BROOKS_FAILED: 'Brooks条件未成立',
    BROOKS_WATCH: 'Brooks观察', BARB_WIRE_WAIT: '铁丝网震荡，等待方向确认',
    COMPACT_BEARISH_REJECT: '紧密结构偏空，已排除', MICRO_DOUBLE_BOTTOM: '微型双底',
    FAILED_BEAR_BREAKOUT: '空头假突破', SECOND_ENTRY_LONG_READY: '二次入场准备',
    ORDERLY_COMPRESSION_AT_SUPPORT: '支撑位有序收缩', BROOKS_SUPPORT_READY: '支撑位触发确认',
    BROOKS_FAILED_BREAKOUT_READY: '假跌破反转触发确认', BROOKS_BREAKOUT_WAIT: '突破后等待确认',
    BROOKS_BREAKOUT_READY: '突破跟进确认',
  },
  brooksTriggerType: {
    SECOND_ENTRY_BREAK: '二次入场突破触发', FAILED_BEAR_BREAKOUT: '假跌破反转触发',
    BREAKOUT_FOLLOW_THROUGH: '突破跟进触发', SUPPORT_REVERSAL: '支撑反转触发',
    BROOKS_SUPPORT_READY: '二次入场突破触发',
    BROOKS_FAILED_BREAKOUT_READY: '假跌破反转触发',
    BROOKS_BREAKOUT_READY: '突破跟进触发',
  },
  brooksContext: {
    BULL_CONTEXT: '上涨背景', WEAK_BULL_CONTEXT: '弱上涨背景',
    TRADING_RANGE_CONTEXT: '交易区间背景', BEAR_CONTEXT: '下跌背景',
    INVALID_CONTEXT: '背景数据不足',
  },
  brooksCompact: {
    NO_COMPACT: '未形成紧密结构', COMPACT_ORDERLY: '有序紧密结构',
    COMPACT_NEUTRAL: '中性紧密结构', BARB_WIRE: '铁丝网震荡',
    COMPACT_BEARISH: '偏空紧密结构',
  },
  brooksSetup: {
    MICRO_DOUBLE_BOTTOM: '微型双底', FAILED_BEAR_BREAKOUT: '空头假突破',
    BEAR_FOLLOW_THROUGH_FAILED: '空方跟进失败', SECOND_ENTRY_LONG_READY: '二次入场准备',
    ORDERLY_COMPRESSION_AT_SUPPORT: '支撑位有序收缩',
  },
  boxStatus: {
    BOX_FORMING: '箱体形成中', BOX_SUPPORT_READY: '箱体下沿支撑就绪', BOX_STABLE: '箱体稳定',
    BOX_BREAKOUT_READY: '箱体突破就绪', BOX_BROKEN: '箱体已破位', NO_BOX: '未形成箱体',
  },
  boxQualityTag: { BOX_COMPACT_READY: '箱体K线紧密就绪', NONE: '无紧密排列标签' },
  marketStatus: {
    MARKET_STRONG: '市场强势', MARKET_NEUTRAL: '市场中性', MARKET_WEAK: '市场偏弱',
    MARKET_RISK: '市场风险', UNKNOWN: '市场状态未知',
  },
  marketFilterMode: { strict: '严格过滤', downgrade: '降级处理', score_only: '仅调整评分', disabled: '已关闭' },
  marketDataStatus: { FRESH: '新鲜', STALE: '已过期', MISSING: '缺失' },
  source: { sina: '新浪', tencent: '腾讯', baidu: '百度' },
  priceBasis: { FORWARD_ADJUSTED: '前复权' },
  executionNote: {
    NEXT_TRADING_DAY_ONLY: '仅限下一交易日执行', SIGNAL_AFTER_CLOSE: '收盘后生成信号',
    T1_STOP_UNAVAILABLE_ON_BUY_DAY: '买入当日T+1限制下无法止损',
    DO_NOT_CHASE_ABOVE_BUY_ZONE: '高于买入区时不追高', ONE_WORD_LIMIT_UP_NO_FILL: '一字涨停可能无法成交',
    LIMIT_DOWN_STOP_MAY_NOT_FILL: '跌停时止损可能无法成交',
    PRICE_BASIS_FORWARD_ADJUSTED: '价格口径为前复权',
    SLIPPAGE_COMMISSION_TAX_NOT_INCLUDED_IN_SIGNAL_RR: '信号盈亏比未计入滑点、佣金和印花税',
    WAIT_FOR_BREAKOUT_NO_ORDER: '等待突破，当前不生成订单',
  },
  tag: {
    BIG_DOWN_VOLUME: '放量大跌', PRESSURE_NEAR_HIGH: '接近前高压力', UPPER_PRESSURE: '上方压力', UPPER_SHADOW_PRESSURE: '上影线抛压',
    NEAR_120D_PRESSURE: '接近120日压力位', BREAKOUT_EXTENDED: '突破后过度延伸',
    RS20_DATA_UNAVAILABLE: 'RS20数据不可用', MARKET_DATA_UNAVAILABLE: '市场数据不可用',
    MARKET_DATA_PARTIAL: '市场指数数据不完整', MARKET_WEAK_STRICT: '市场偏弱，严格过滤',
    MARKET_WEAK_DOWNGRADED: '市场偏弱，候选已降级', ONE_WORD_LIMIT_UP_UNCONFIRMED: '一字涨停启动尚未确认',
    PATTERN_UNKNOWN: '未识别有效形态', NO_STRONG_START: '未找到强势启动', NO_NEW_HIGH_CONFIRMATION: '缺少新高确认',
    NO_VALID_SUPPORT_TEST: '缺少有效支撑测试', SUPPORT_FAILED: '支撑失效', MA_CALC_FAILED: '均线计算失败',
    STRATEGY_REJECTED: '策略判定排除', MAX_WATCH_DAYS_REACHED: '已达最长观察天数',
    CLOSE_LE_MA250: '收盘价不高于MA250', MA120_LE_MA250: 'MA120不高于MA250',
    AVG60D_LT_MIN: '60日平均成交额低于门槛', AVG30D_LT_MIN: '30日平均成交额低于门槛',
    AVG10D_LT_MIN: '10日平均成交额低于门槛', AVG10D_LT_AVG30D_RATIO: '10日成交额相对30日过低',
    CLOSE_LT_KEY_SUPPORT: '收盘价跌破关键支撑', CLOSE_LT_KEY_SUPPORT_0_96: '收盘价跌破关键支撑96%',
    TWO_CLOSES_LT_KEY_SUPPORT: '连续两日收盘跌破关键支撑', CLOSE_LT_MA50_0_92: '收盘价低于MA50的92%',
    CONSOLIDATION_RANGE_10_GT_ABSOLUTE_LIMIT: '10日整理振幅超过绝对上限',
    CONSOLIDATION_PULLBACK_20D_GT_ABSOLUTE_LIMIT: '20日整理回撤超过绝对上限',
    LATEST_TRADE_SUSPENDED: '最新交易日停牌', LATEST_TRADE_NO_TRADE: '最新交易日无成交',
    TAIL_VOLUME_BASE_INSUFFICIENT: '尾段成交量基准数据不足', TAIL_VOLUME_NOT_DRY: '尾段成交量未充分萎缩',
    TAIL_CLOSE_RANGE_GT_8PCT: '尾段收盘区间超过8%', TAIL_LOW_DECLINING: '尾段低点持续下移', TAIL_NEW_LOW: '尾段创新低',
    TAIL_RETURN_5_TOO_WEAK: '尾段5日涨跌幅过弱', TAIL_SINGLE_DROP_TOO_WEAK: '尾段单日跌幅过大',
    BOX_WIDTH_TOO_WIDE: '箱体宽度过大', BOX_LOW_TESTS_INSUFFICIENT: '箱体下沿测试次数不足',
    BOX_CENTER_SHIFT_TOO_WEAK: '箱体中枢承接过弱', BOX_VOLUME_NOT_CONTRACTED: '箱体后半段成交量未收缩',
    BOX_CURRENT_CLOSE_OUT_OF_RANGE: '当前收盘价超出箱体范围', BOX_TAIL_VOLUME_NOT_DRY: '箱体尾段量能未萎缩',
    BOX_VOLUME_SELLOFF: '箱体内出现放量抛售', BOX_KEY_SUPPORT_BROKEN: '箱体关键支撑跌破', BOX_BROKEN: '箱体已破位',
    NO_ELIGIBLE_BOX_WINDOW: '未找到合格箱体窗口', COMPACT_DATA_INSUFFICIENT: '紧密K线数据不足',
    COMPACT_AVG_BODY_TOO_LARGE: '平均K线实体过大', COMPACT_MAX_BODY_TOO_LARGE: '最大K线实体过大',
    COMPACT_CLOSE_RANGE_TOO_WIDE: '紧密区收盘范围过宽', COMPACT_OVERLAP_INSUFFICIENT: 'K线重叠程度不足',
    COMPACT_GAP_TOO_LARGE: 'K线跳空过大', COMPACT_ATR_NOT_CONTRACTED: 'ATR未收缩', COMPACT_VOLUME_SELLOFF: '紧密区出现放量抛售',
    ATR_DATA_INSUFFICIENT: 'ATR数据不足', COMPACT_INVALID_CLOSE: '紧密K线收盘价无效',
    COMPACT_INVALID_PREVIOUS_CLOSE: '前一日收盘价无效', COMPACT_ZERO_RANGE_KLINE: '存在零振幅K线',
    BOX_PHASE_INVALID: '箱体阶段无效', BOX_TAIL_VOLUME_BASE_INSUFFICIENT: '箱体尾段量能基准不足',
    BOX_STRUCTURE_DATA_INSUFFICIENT: '箱体结构数据不足', BOX_BOUNDARY_INVALID: '箱体边界无效',
    BOX_HALF_DATA_INSUFFICIENT: '箱体前后半段数据不足', BOX_FIRST_HALF_VOLUME_INVALID: '箱体前半段成交量无效',
    BOX_FIRST_HALF_CENTER_INVALID: '箱体前半段中枢无效', CLOSE_BELOW_BOX_LOW_TOLERANCE: '收盘价跌破箱体下沿容差',
    TWO_CLOSES_BELOW_BOX_LOW: '连续两日收盘跌破箱体下沿', VOLUME_SELLOFF_BELOW_BOX_LOW: '放量跌破箱体下沿',
    CLOSE_BELOW_KEY_SUPPORT: '收盘价跌破关键支撑', PATTERN_DATA_INSUFFICIENT: '形态数据不足',
    PATTERN_NOT_RECOGNIZED: '未识别有效形态',
    'box:width_valid': '箱体宽度合格', 'box:independent_low_tests': '箱体下沿独立测试合格',
    'box:center_stable': '箱体中枢稳定', 'box:second_half_volume_contracted': '箱体后半段成交量收缩',
    'box:current_close_in_range': '当前收盘位于箱体内', 'box:tail_volume_dry': '箱体尾段量能萎缩',
    'box:no_volume_selloff': '箱体内无放量抛售', 'box:key_support_valid': '箱体关键支撑有效', 'box:not_broken': '箱体未破位',
    'compact:small_average_body': '平均K线实体较小', 'compact:no_large_body': '无过大K线实体',
    'compact:close_concentrated': '收盘价集中', 'compact:range_overlap': 'K线区间重叠合格',
    'compact:no_large_gap': '无过大跳空', 'compact:atr_contracted': 'ATR已收缩', 'compact:no_volume_selloff': '紧密区无放量抛售',
    highest_box_quality_score_then_days_width_volume_contraction: '按箱体质量分、天数、宽度和量缩程度择优',
    BROOKS_GRADE_B_WATCH_ONLY: 'B级启动仅观察', BARB_WIRE_RISK: '铁丝网震荡，方向不明确',
    BROOKS_CONTEXT_DATA_INSUFFICIENT: 'Brooks背景数据不足', BROOKS_CONTEXT_NOT_BULLISH: 'Brooks背景不支持上涨',
    BROOKS_BEAR_CONTEXT: '处于下跌背景', BROOKS_BULL_CONTEXT_VALID: '上涨背景有效',
    BROOKS_SUPPORT_EFFECTIVELY_BROKEN: 'Brooks关键支撑有效跌破',
    BROOKS_SELLING_PRESSURE_DATA_INSUFFICIENT: '卖压判断数据不足',
    BROOKS_SELLING_PRESSURE_EXHAUSTED: '卖压已衰竭', BROOKS_CONSECUTIVE_BEAR_BARS: '连续阴线卖压仍在',
    BROOKS_STRONG_BEAR_BARS_EXCESSIVE: '强空方K线过多', BROOKS_BEAR_FOLLOW_THROUGH: '空方存在跟进',
    BROOKS_STRUCTURE_DATA_INSUFFICIENT: '结构判断数据不足', BROOKS_COMPACT_ORDERLY: '紧密结构有序',
    BROOKS_COMPACT_NEUTRAL: '紧密结构中性', BROOKS_COMPACT_BEARISH: '紧密结构偏空',
    BROOKS_TAIL_PATH_PASSED: 'Brooks尾部路径通过', BROOKS_CONTEXT_REJECT: '上涨背景不合格',
    BROOKS_SELLING_PRESSURE_NOT_EXHAUSTED: '卖压尚未衰竭', BROOKS_PRICE_NOT_STABLE: '价格尚未稳定',
    BROOKS_VOLUME_NOT_DRY: '量能尚未充分萎缩', BROOKS_SUPPORT_BROKEN: '支撑已经失效',
    BROOKS_SETUP_NOT_FOUND: '未识别Brooks结构', BROOKS_TRIGGER_SIGNAL_NOT_VISIBLE: '触发信号尚不可见',
    BROOKS_TRIGGER_REQUIRES_LATER_SESSION: '需等待后续交易日确认', BROOKS_TRIGGER_GAP_TOO_FAR: '跳空后距离触发位过远',
    BROOKS_TRIGGER_EXPIRED: 'Brooks触发已过期', BROOKS_SECOND_ENTRY_TRIGGERED: '二次入场已触发',
    BROOKS_FAILED_BREAKOUT_CONFIRMED: '假跌破反转已确认', BROOKS_BREAKOUT_FOLLOW_THROUGH: '突破获得后续跟进',
    SUPPORT_TEST_LOW_VOLUME: '支撑测试时缩量', SUPPORT_TEST_RECOVERED: '支撑测试后收复',
    SUPPORT_TEST_REPEATED: '支撑经过重复测试', SUPPORT_VOLUME_BREAK_UNRECOVERED: '放量跌破支撑且未收复',
    SUPPORT_REACTION_WEAKENING: '支撑反应正在减弱', SETUP_QUALITY_DATA_UNAVAILABLE: '整理质量数据不足',
    START_GAIN_POORLY_RETAINED: '启动涨幅保持不足', DISTRIBUTION_PRESSURE_HIGH: '派发压力较高',
    DOWN_VOLUME_DOMINATES: '下跌日成交量占优', VOLATILITY_NOT_CONTRACTING: '波动率未收缩',
    RELATIVE_STRENGTH_FADING: '相对强度走弱', REPEATED_FAILED_BREAKOUTS: '反复假突破',
    RS_TREND_UNAVAILABLE: '相对强度趋势数据不可用', START_LOW_BROKEN: '启动低点被跌破',
    START_GAIN_FULLY_RETRACED: '启动涨幅已完全回吐', START_FOLLOW_THROUGH_DISTRIBUTION: '启动后出现放量派发',
    VCP_ORIGIN_STRONG_START: 'VCP结构前存在强势启动', VCP_ORIGIN_START_MISSING: 'VCP结构缺少历史强势启动',
    VCP_SWING_CONTRACTIONS: 'VCP波段收缩成立', VCP_RANGE_CONTRACTING: 'VCP振幅依次收缩',
    VCP_VOLUME_CONTRACTING: 'VCP成交量依次收缩', VCP_LOW_NOT_FALLING: 'VCP低点未下移',
    VCP_NEAR_PIVOT: '接近VCP支点', VCP_BREAKOUT_CONFIRMED: 'VCP突破已确认',
    VCP_POST_BREAKOUT: 'VCP突破后观察', VCP_PRICE_EXTENDED: 'VCP价格偏离支点过远',
    VCP_PIVOT_LOST: 'VCP突破后跌回支点下方', VCP_STRUCTURE_LOW_BROKEN: 'VCP结构低点被跌破',
    VCP_VOLUME_BREAKDOWN_UNRECOVERED: 'VCP放量跌回支点后3日未收复',
    VCP_OBSERVATION_EXPIRED: 'VCP突破观察期已结束', VCP_DATA_INSUFFICIENT: 'VCP观察数据不足',
    VCP_BASE_FILTER_FAILED: 'VCP观察未通过基础数据或流动性门槛',
    TRADING_LIFECYCLE_BLOCKED: '原交易生命周期处于退出或冷却状态',
  },
}

const DYNAMIC_LABELS = [
  [/^RR2_LT_(.+)$/, value => `RR2低于${value.replaceAll('_', '.')}`],
  [/^RS20_LT_(.+)$/, value => `RS20低于${value.replaceAll('_', '.')}`],
  [/^TRADING_DAYS_LT_(.+)$/, value => `交易日数少于${value}`],
  [/^CONSOLIDATION_RANGE_5_GT_(.+)_LIMIT$/, value => `5日整理振幅超过${value}级限制`],
  [/^CONSOLIDATION_RANGE_10_GT_(.+)_LIMIT$/, value => `10日整理振幅超过${value}级限制`],
  [/^CONSOLIDATION_PULLBACK_20D_GT_(.+)_LIMIT$/, value => `20日整理回撤超过${value}级限制`],
  [/^strong=(.+)$/, value => `强势启动得分=${value}`],
  [/^pattern=(.+)$/, value => `形态得分=${value}`],
  [/^support=(.+)$/, value => `支撑得分=${value}`],
  [/^tail=(.+)$/, value => `尾段得分=${value}`],
  [/^objective_rr=(.+)$/, value => `客观盈亏比得分=${value}`],
  [/^rs_risk=(.+)$/, value => `RS/风险得分=${value}`],
  [/^above_ma20=(.+)$/, value => `收盘位于MA20上方的指数数=${value}`],
  [/^ma20_above_ma50=(.+)$/, value => `MA20不低于MA50的指数数=${value}`],
  [/^risk_count=(.+)$/, value => `放量下跌风险指数数=${value}`],
  [/^observed_indexes=(.+)$/, value => `有效指数数量=${value}`],
  [/^gain_retention=(.+)$/, value => `启动涨幅保持率=${value}`],
  [/^distribution_days=(.+)$/, value => `派发日数量=${value}`],
  [/^up_down_volume=(.+)$/, value => `上涨/下跌成交量比=${value}`],
  [/^volatility_contraction=(.+)$/, value => `波动收缩比=${value}`],
  [/^failed_breakouts=(.+)$/, value => `假突破次数=${value}`],
  [/^rs_trend=(.+)$/, value => `相对强度趋势=${value}`],
]

export function strategy6Label(group, value) {
  if (value == null || value === '') return '--'
  const raw = String(value)
  const direct = LABELS[group]?.[raw]
  if (direct) return direct
  if (group === 'tag') {
    for (const fallbackGroup of ['phaseStatus', 'supportStatus', 'lifecycleStatus', 'boxStatus', 'brooksStatus', 'brooksSetup', 'brooksCompact']) {
      const fallback = LABELS[fallbackGroup]?.[raw]
      if (fallback) return fallback
    }
  }
  if (group === 'marketReason') {
    const marketTag = LABELS.tag?.[raw]
    if (marketTag) return marketTag
  }
  if (group === 'tag' || group === 'marketReason') {
    for (const [pattern, formatter] of DYNAMIC_LABELS) {
      const match = raw.match(pattern)
      if (match) return formatter(match[1])
    }
  }
  return raw
}

export function strategy6Labels(group, values) {
  if (!Array.isArray(values)) return []
  return values.map(value => strategy6Label(group, value))
}
