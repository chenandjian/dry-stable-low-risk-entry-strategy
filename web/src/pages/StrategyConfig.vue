<template>
  <div class="page-content">
    <h2 class="page-title">策略配置</h2>
    <p class="page-sub">修改扫描参数，保存后下次扫描生效</p>

    <!-- 市场范围 -->
    <section class="section">
      <h3 class="section-title">市场范围</h3>
      <div class="toggle-grid">
        <label v-for="m in markets" :key="m.key" class="toggle-item">
          <span class="toggle-label" :title="m.tip">{{ m.label }}</span>
          <button class="toggle" :class="{ active: config.market?.[m.key] }"
            @click="toggle('market', m.key)">{{ config.market?.[m.key] ? '开' : '关' }}</button>
        </label>
      </div>
    </section>

    <!-- 基础参数 -->
    <section class="section">
      <h3 class="section-title">基础参数</h3>
      <div class="param-grid">
        <div class="param">
          <label title="近20日平均成交额低于此值的股票将被过滤（单位：元）">平均成交额阈值 <span class="unit">元</span></label>
          <input type="number" v-model.number="config.liquidity.min_avg_turnover"
            @input="markDirty" step="1000000" />
          <span class="default">默认 1亿</span>
        </div>
        <div class="param">
          <label title="股价低于此值的股票将被过滤（单位：元）">最低股价 <span class="unit">元</span></label>
          <input type="number" v-model.number="config.liquidity.min_stock_price"
            @input="markDirty" step="1" min="0" />
          <span class="default">默认 10元</span>
        </div>
        <div class="param">
          <label title="每只股票拉取的日线数量，低于此天数的股票自动过滤">日线拉取天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.liquidity.min_listing_days"
            @input="markDirty" step="10" min="30" />
          <span class="default">默认 250天</span>
        </div>
        <div class="param">
          <label title="扫描时传入统一策略引擎的最近交易日数量，用于杯柄/VCP形态检测和干稳低吸分析">扫描分析天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.data.scan_window_days"
            @input="markDirty" step="50" min="30" />
          <span class="default">默认 250天</span>
        </div>
        <div class="param">
          <label title="回测时每次形态分析使用的交易日数，逐日滑动评估历史数据中的每个交易日">回测分析天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.data.backtest_window_days"
            @input="markDirty" step="50" min="30" />
          <span class="default">默认 250天</span>
        </div>
      </div>
      <div class="param-group" style="margin-top:12px">
        <label class="param-label" title="按优先级排列，首位为主数据源，拉取失败时按顺序尝试后续数据源">日线数据源 <span class="unit">按优先级排列</span></label>
        <div class="toggle-grid">
          <label v-for="src in availableSources" :key="src.key" class="toggle-item">
            <span class="toggle-label" :title="src.tip">{{ src.label }}</span>
            <button class="toggle" :class="{ active: (config.data.daily_sources || []).includes(src.key) }"
              @click="toggleSource(src.key)">{{ (config.data.daily_sources || []).includes(src.key) ? '开' : '关' }}</button>
          </label>
        </div>
      </div>
    </section>

    <!-- 高级参数 -->
    <section class="section">
      <h3 class="section-title" style="cursor:pointer" @click="showAdvanced = !showAdvanced">
        {{ showAdvanced ? '▾' : '▸' }} 高级参数
      </h3>
      <div v-if="showAdvanced">
        <h4 class="sub-group-title">流动性</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近20日平均成交量低于此值的股票将被过滤（单位：股）">平均成交量阈值 <span class="unit">股</span></label>
            <input type="number" v-model.number="config.liquidity.min_avg_volume"
              @input="markDirty" step="100000" />
            <span class="default">默认 500万</span>
          </div>
          <div class="param">
            <label title="最近交易日成交额低于此值的股票将被过滤（单位：元）">最新成交额阈值 <span class="unit">元</span></label>
            <input type="number" v-model.number="config.liquidity.min_latest_turnover"
              @input="markDirty" step="1000000" />
            <span class="default">默认 8000万</span>
          </div>
        </div>

        <h4 class="sub-group-title">杯体结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="60" v-model.number="config.cup.min_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.min_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="100" max="250" v-model.number="config.cup.max_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.max_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体回调的最小幅度，低于此幅度不算杯体">最小深度 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupMinDepth" @input="markDirty" />
            <div class="range-val">{{ cupMinDepth }}%</div>
          </div>
          <div class="param">
            <label title="杯体回调的最大幅度，超过此幅度杯体太深">最大深度 <span class="unit">%</span></label>
            <input type="range" min="30" max="55" step="1" v-model.number="cupMaxDepth" @input="markDirty" />
            <div class="range-val">{{ cupMaxDepth }}%</div>
          </div>
          <div class="param">
            <label title="左右杯口价格的最大偏差比例">杯口最大偏差 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupLipDeviation" @input="markDirty" />
            <div class="range-val">{{ cupLipDeviation }}%</div>
          </div>
          <div class="param">
            <label title="杯底附近价格在杯底8%范围内的比例阈值">杯底圆滑度 <span class="unit">%</span></label>
            <input type="range" min="5" max="30" step="1" v-model.number="cupRoundness" @input="markDirty" />
            <div class="range-val">{{ cupRoundness }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">柄部结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="柄部回调的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="3" max="10" v-model.number="handleMinDur" @input="markDirty" />
            <div class="range-val">{{ handleMinDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部回调的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="40" v-model.number="handleMaxDur" @input="markDirty" />
            <div class="range-val">{{ handleMaxDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部从右杯口向下的最大回撤幅度">最大回撤 <span class="unit">%</span></label>
            <input type="range" min="8" max="25" step="1" v-model.number="handleMaxDepth" @input="markDirty" />
            <div class="range-val">{{ handleMaxDepth }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">突破判断</h4>
        <div class="param-grid">
          <div class="param">
            <label title="突破确认的价格缓冲比例，超过杯口此比例算突破">缓冲比例 <span class="unit">%</span></label>
            <input type="range" min="0" max="5" step="0.5" v-model.number="breakoutBuffer" @input="markDirty" />
            <div class="range-val">{{ breakoutBuffer }}%</div>
          </div>
          <div class="param">
            <label title="突破当天成交量相对均量的倍数阈值">放量倍数</label>
            <input type="range" min="1.0" max="2.5" step="0.1" v-model.number="config.breakout.volume_multiplier" @input="markDirty" />
            <div class="range-val">{{ config.breakout.volume_multiplier }}×</div>
          </div>
        </div>

        <h4 class="sub-group-title">决策规则</h4>
        <div class="param-grid">
          <div class="param">
            <label title="止损空间超过此值直接拒绝买入">止损空间上限 <span class="unit">%</span></label>
            <input type="range" min="5" max="15" step="0.5" v-model.number="maxRiskPercent" @input="markDirty" />
            <div class="range-val">{{ maxRiskPercent }}%</div>
          </div>
          <div class="param">
            <label title="量干评分低于此值直接拒绝（满分12）">量干最低分</label>
            <input type="range" min="4" max="10" v-model.number="config.decision.min_volume_dry_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_volume_dry_score }} 分</div>
          </div>
          <div class="param">
            <label title="价稳评分低于此值直接拒绝">价稳最低分</label>
            <input type="range" min="3" max="8" v-model.number="config.decision.min_price_stable_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_price_stable_score }} 分</div>
          </div>
          <div class="param">
            <label title="形态评分低于此值直接拒绝">形态最低分</label>
            <input type="range" min="5" max="12" v-model.number="config.decision.min_pattern_score" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_pattern_score }} 分</div>
          </div>
          <div class="param">
            <label title="第一目标盈亏比低于此值直接拒绝">盈亏比下限</label>
            <input type="range" min="1.0" max="3.0" step="0.1" v-model.number="config.decision.min_rr1" @input="markDirty" />
            <div class="range-val">{{ config.decision.min_rr1 }} : 1</div>
          </div>
          <div class="param">
            <label title="可低吸额外要求：止损空间上限">可低吸止损上限 <span class="unit">%</span></label>
            <input type="range" min="3" max="10" step="0.5" v-model.number="config.decision.low_buy_max_risk_percent" @input="markDirty" />
            <div class="range-val">{{ config.decision.low_buy_max_risk_percent }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">量干进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近10日价格线性回归斜率低于此值且收盘低于MA20时，量干最高分被限制">缩量阴跌封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.bad_shrink_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.bad_shrink_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="股价处于近60日区间下半部时量干最高分">低位缩量封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.low_position_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.low_position_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="近5天放量但不涨时量干最高分">放量滞涨封顶分</label>
            <input type="range" min="5" max="10" v-model.number="config.volume_dry.volume_stall_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.volume_stall_max_score }} 分</div>
          </div>
          <div class="param">
            <label title="近3天放量大阴线时量干最高分">大阴线封顶分</label>
            <input type="range" min="4" max="9" v-model.number="config.volume_dry.big_bear_max_score" @input="markDirty" />
            <div class="range-val">{{ config.volume_dry.big_bear_max_score }} 分</div>
          </div>
        </div>

        <h4 class="sub-group-title">价稳进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近5日收盘价波动≤此值视为价格紧致">收盘紧致度 <span class="unit">%</span></label>
            <input type="range" min="1" max="8" v-model.number="config.price_stable.close_tightness_strong_pct" @input="markDirty" />
            <div class="range-val">{{ config.price_stable.close_tightness_strong_pct }}%</div>
          </div>
          <div class="param">
            <label title="跌破柄底/MA50时价稳最高分">支撑跌破封顶分</label>
            <input type="range" min="3" max="7" v-model.number="config.price_stable.support_break_max_score" @input="markDirty" />
            <div class="range-val">{{ config.price_stable.support_break_max_score }} 分</div>
          </div>
        </div>

        <h4 class="sub-group-title">风报进阶</h4>
        <div class="param-grid">
          <div class="param">
            <label title="止损空间必须≥ATR14×此倍数，否则发出警告">ATR止损倍数</label>
            <input type="range" min="1.0" max="2.0" step="0.1" v-model.number="config.risk_reward.atr_stop_multiplier" @input="markDirty" />
            <div class="range-val">{{ config.risk_reward.atr_stop_multiplier }}×</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 策略2：极致量干价稳 -->
    <section class="section strategy2-section">
      <h3 class="section-title strategy2-title">策略2 · 极致量干价稳</h3>
      <p class="section-hint">
        策略2 独立扫描全部股票，不依赖杯柄/VCP 形态识别。日线拉取天数沿用全局配置；本期不支持回测。
      </p>

      <!-- 启停开关 -->
      <div class="toggle-grid" style="margin-bottom:16px">
        <label class="toggle-item">
          <span class="toggle-label">启用策略2</span>
          <button class="toggle" :class="{ active: config.strategy2?.enabled !== false }"
            @click="toggleStrategy2('enabled')">{{ config.strategy2?.enabled !== false ? '开' : '关' }}</button>
        </label>
      </div>

      <div class="param-grid">
        <div class="param">
          <label title="策略2计算仅使用最近 N 个有效交易日的数据">策略计算天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.strategy_window_days"
            @input="markDirty" step="10" min="60" />
          <span class="default">默认 120 · 须 ≥ 最低有效数据天数</span>
        </div>
        <div class="param">
          <label title="有效数据不足此天数时跳过该股票">最低有效数据天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.minimum_required_days"
            @input="markDirty" step="5" min="60" />
          <span class="default">默认 60 · ≥ 60</span>
        </div>
        <div class="param">
          <label title="总分 ≥ 此值且无否决且风险比达标才入选">候选最低分</label>
          <input type="number" v-model.number="config.strategy2.candidate_min_score"
            @input="markDirty" min="0" max="100" />
          <span class="default">默认 70 · 0-100</span>
        </div>
        <div class="param">
          <label title="风险比超过此值强制排除。风险比 = (收盘价 - 止损) / 收盘价">最大风险比 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="maxRiskRatioPct" @input="markDirty" />
          <div class="range-val">{{ maxRiskRatioPct }}%</div>
        </div>
        <div class="param">
          <label title="关键支撑 = 不含评估日的前 N 个交易日最低收盘价">支撑回看天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.strategy2.support_lookback_days"
            @input="markDirty" min="2" />
          <span class="default">默认 10 · ≥ 2</span>
        </div>
        <div class="param">
          <label title="买入区间上限 = 关键支撑 × (1 + 溢价比例)">买入区间溢价 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="buyZonePremiumPct" @input="markDirty" />
          <div class="range-val">{{ buyZonePremiumPct }}%</div>
        </div>
        <div class="param">
          <label title="止损价 = 关键支撑 × (1 - 缓冲比例)">止损缓冲比例 <span class="unit">%</span></label>
          <input type="range" min="1" max="10" step="0.5" v-model.number="stopLossBufferPct" @input="markDirty" />
          <div class="range-val">{{ stopLossBufferPct }}%</div>
        </div>
      </div>

      <div class="info-msg">
        ⓘ 日线拉取天数使用全局配置 ({{ config.liquidity?.min_listing_days || '--' }} 天) · 策略2不使用杯柄/VCP判断 · 本期不支持回测
      </div>
    </section>

    <!-- Actions -->
    <div class="actions-bar">
      <div v-if="saved" class="saved-msg">✓ 配置已保存</div>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <div class="actions-right">
        <button class="btn-reset" @click="resetAll">恢复默认</button>
        <button class="btn-save" :class="{ dirty }" @click="saveConfig" :disabled="saving">
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const { getConfig, updateConfig } = useApi()

const config = reactive({
  market: {},
  liquidity: {},
  data: { scan_window_days: 250, backtest_window_days: 250, daily_sources: ['baidu', 'sina', 'tencent', 'yfinance'] },
  cup: {},
  handle: {},
  breakout: {},
  decision: {},
  volume_dry: { bad_shrink_max_score: 7, low_position_max_score: 7, volume_stall_max_score: 7, big_bear_max_score: 6 },
  price_stable: { close_tightness_strong_pct: 3, support_break_max_score: 5 },
  risk_reward: { atr_stop_multiplier: 1.2 },
  strategy2: {
    enabled: true, strategy_window_days: 120, minimum_required_days: 60,
    candidate_min_score: 70, max_risk_ratio: 0.05, support_lookback_days: 10,
    buy_zone_max_premium: 0.03, stop_loss_buffer: 0.03,
  },
})

const dirty = ref(false)
const saved = ref(false)
const saving = ref(false)
const error = ref('')
const showAdvanced = ref(false)

// Computed: convert cup depth from 0-1 to percentage for slider display
const cupMinDepth = computed({
  get: () => Math.round((config.cup.min_depth || 0.12) * 100),
  set: (v) => { config.cup.min_depth = v / 100 },
})
const cupMaxDepth = computed({
  get: () => Math.round((config.cup.max_depth || 0.45) * 100),
  set: (v) => { config.cup.max_depth = v / 100 },
})
const cupRoundness = computed({
  get: () => Math.round((config.cup.min_bottom_roundness || 0.15) * 100),
  set: (v) => { config.cup.min_bottom_roundness = v / 100 },
})
const cupLipDeviation = computed({
  get: () => Math.round((config.cup.max_lip_deviation || 0.12) * 100),
  set: (v) => { config.cup.max_lip_deviation = v / 100 },
})
const handleMinDur = computed({
  get: () => config.handle?.min_duration || 5,
  set: (v) => { config.handle.min_duration = v },
})
const handleMaxDur = computed({
  get: () => config.handle?.max_duration || 30,
  set: (v) => { config.handle.max_duration = v },
})
const handleMaxDepth = computed({
  get: () => Math.round((config.handle?.max_depth || 0.18) * 100),
  set: (v) => { config.handle.max_depth = v / 100 },
})
const breakoutBuffer = computed({
  get: () => Math.round((config.breakout?.buffer_pct || 0.02) * 100),
  set: (v) => { config.breakout.buffer_pct = v / 100 },
})
const maxRiskPercent = computed({
  get: () => config.decision?.max_risk_percent ?? 8,
  set: (v) => { config.decision.max_risk_percent = v },
})

// Strategy2 computed: percentage sliders
const maxRiskRatioPct = computed({
  get: () => Math.round((config.strategy2?.max_risk_ratio ?? 0.05) * 100),
  set: (v) => { config.strategy2.max_risk_ratio = v / 100 },
})
const buyZonePremiumPct = computed({
  get: () => Math.round((config.strategy2?.buy_zone_max_premium ?? 0.03) * 100),
  set: (v) => { config.strategy2.buy_zone_max_premium = v / 100 },
})
const stopLossBufferPct = computed({
  get: () => Math.round((config.strategy2?.stop_loss_buffer ?? 0.03) * 100),
  set: (v) => { config.strategy2.stop_loss_buffer = v / 100 },
})

function toggleStrategy2(key) {
  config.strategy2[key] = !config.strategy2[key]
  markDirty()
}

const availableSources = [
  { key: 'baidu', label: '百度', tip: '百度股票API，国内数据源，稳定可靠' },
  { key: 'sina', label: '新浪', tip: '新浪财经API，数据覆盖全' },
  { key: 'tencent', label: '腾讯', tip: '腾讯财经API，实时性好' },
  { key: 'yfinance', label: 'Yahoo Finance', tip: 'Yahoo Finance 国际数据源，需稳定外网连接' },
]

const markets = [
  { key: 'include_sh', label: '沪市主板', tip: '上证主板股票，代码 60xxxx' },
  { key: 'include_sz', label: '深市主板', tip: '深证主板股票，代码 00xxxx/002xxx/003xxx' },
  { key: 'include_cyb', label: '创业板', tip: '创业板股票，代码 300xxx/301xxx' },
  { key: 'include_kcb', label: '科创板', tip: '科创板股票，代码 688xxx' },
  { key: 'exclude_bj', label: '排除北交所', tip: '排除北交所股票，代码 8xxxxx/4xxxxx' },
  { key: 'exclude_st', label: '排除 ST/*ST', tip: '排除 ST 及 *ST 股票' },
]

function toggle(section, key) {
  config[section][key] = !config[section][key]
  markDirty()
}

function toggleSource(key) {
  if (!config.data.daily_sources) {
    config.data.daily_sources = availableSources.map(s => s.key)
  }
  const idx = config.data.daily_sources.indexOf(key)
  if (idx >= 0) {
    if (config.data.daily_sources.length <= 1) return  // 至少保留一个
    config.data.daily_sources.splice(idx, 1)
  } else {
    config.data.daily_sources.push(key)
  }
  markDirty()
}

function markDirty() {
  dirty.value = true
  saved.value = false
}

function validate() {
  const errors = []
  const cup = config.cup
  const handle = config.handle

  if (cup.min_duration < 20 || cup.min_duration > 60) errors.push('杯体最短周期需在 20-60 天之间')
  if (cup.max_duration < 100 || cup.max_duration > 250) errors.push('杯体最长周期需在 100-250 天之间')
  if (cup.min_duration >= cup.max_duration) errors.push('杯体最短周期必须小于最长周期')
  if (cup.min_depth < 0.05 || cup.min_depth > 0.20) errors.push('杯体最小深度需在 5%-20% 之间')
  if (cup.max_depth < 0.30 || cup.max_depth > 0.55) errors.push('杯体最大深度需在 30%-55% 之间')
  if (cup.min_depth >= cup.max_depth) errors.push('杯体最小深度必须小于最大深度')
  if (handle.min_duration < 3 || handle.min_duration > 10) errors.push('柄部最短周期需在 3-10 天之间')
  if (handle.max_duration < 20 || handle.max_duration > 40) errors.push('柄部最长周期需在 20-40 天之间')
  if (handle.min_duration >= handle.max_duration) errors.push('柄部最短周期必须小于最长周期')
  if (handle.max_depth < 0.08 || handle.max_depth > 0.25) errors.push('柄部最大回撤需在 8%-25% 之间')

  const liq = config.liquidity
  const dataCfg = config.data || {}
  if (liq.min_avg_turnover < 10000000) errors.push('成交额阈值最低 1000万')
  if (liq.min_stock_price < 1) errors.push('最低股价不能低于 1元')
  if (liq.min_listing_days < 30) errors.push('拉取天数最低 30天')
  if (dataCfg.scan_window_days < 30) errors.push('扫描分析天数最低 30天')
  if (dataCfg.backtest_window_days < 30) errors.push('回测分析天数最低 30天')
  if (dataCfg.scan_window_days > liq.min_listing_days) errors.push('扫描分析天数不能超过日线拉取天数')
  if (!dataCfg.daily_sources || dataCfg.daily_sources.length === 0) errors.push('至少选择一个日线数据源')

  // Strategy2 validation
  const s2 = config.strategy2 || {}
  if (s2.strategy_window_days < s2.minimum_required_days) errors.push('策略2: 计算天数不能小于最低有效数据天数')
  if (s2.minimum_required_days < 60) errors.push('策略2: 最低有效数据天数 ≥ 60')
  if (s2.strategy_window_days > (liq.min_listing_days || 250)) errors.push('策略2: 计算天数不能超过日线拉取天数')
  if (s2.candidate_min_score < 0 || s2.candidate_min_score > 100) errors.push('策略2: 候选最低分需在 0-100')
  if (s2.max_risk_ratio <= 0 || s2.max_risk_ratio >= 1) errors.push('策略2: 最大风险比需在 (0, 1) 之间')
  if (s2.support_lookback_days < 2) errors.push('策略2: 支撑回看天数 ≥ 2')
  if (s2.buy_zone_max_premium <= 0 || s2.buy_zone_max_premium > 0.2) errors.push('策略2: 买入溢价需在 (0, 20%] 之间')
  if (s2.stop_loss_buffer <= 0 || s2.stop_loss_buffer > 0.2) errors.push('策略2: 止损缓冲需在 (0, 20%] 之间')

  return errors
}

async function saveConfig() {
  const errors = validate()
  if (errors.length) {
    error.value = errors.join('；')
    return
  }
  saving.value = true
  error.value = ''
  try {
    // Build the payload matching config.yaml structure
    const payload = {
      market: { ...config.market },
      liquidity: { ...config.liquidity },
      data: { ...config.data },
      cup: {
        min_duration: config.cup.min_duration,
        max_duration: config.cup.max_duration,
        min_depth: config.cup.min_depth,
        max_depth: config.cup.max_depth,
        max_lip_deviation: config.cup.max_lip_deviation,
        min_bottom_roundness: config.cup.min_bottom_roundness,
      },
      handle: {
        min_duration: config.handle.min_duration,
        max_duration: config.handle.max_duration,
        max_depth: config.handle.max_depth,
      },
      breakout: {
        buffer_pct: config.breakout.buffer_pct,
        volume_multiplier: config.breakout.volume_multiplier,
      },
      decision: { ...config.decision },
      volume_dry: { ...config.volume_dry },
      price_stable: { ...config.price_stable },
      risk_reward: { ...config.risk_reward },
      strategy2: { ...config.strategy2 },
    }
    const res = await updateConfig(payload)
    if (res.status === 'ok') {
      dirty.value = false
      saved.value = true
      setTimeout(() => { saved.value = false }, 3000)
    } else {
      error.value = res.message || '保存失败'
    }
  } catch (e) {
    error.value = '保存失败，请检查后端服务'
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
    }
    dirty.value = false
    saved.value = false
    error.value = ''
  } catch (e) {
    error.value = '加载配置失败'
  }
}

onMounted(async () => {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
    }
  } catch (e) {
    // use defaults
  }
})
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 900px; margin: 0 auto; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.page-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 24px; }

.section {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px; margin-bottom: 16px;
}
.section-title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
}

.toggle-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.toggle-item { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.toggle-label { font-size: 13px; color: var(--text-secondary); min-width: 90px; }
.toggle {
  padding: 4px 14px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted); font-size: 12px; font-weight: 600; cursor: pointer;
}
.toggle.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 600px) { .param-grid { grid-template-columns: 1fr; } }
.param label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.param .unit { font-size: 11px; color: var(--text-muted); }
.param .default { font-size: 10px; color: var(--text-muted); margin-top: 2px; display: block; }
.param input[type="range"] { width: 100%; accent-color: var(--accent); }
.param input[type="number"] {
  width: 100%; padding: 6px 10px; border-radius: 4px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary); font-family: var(--font-mono); font-size: 14px;
}
.range-val { font-family: var(--font-mono); font-size: 18px; font-weight: 700; color: var(--accent); margin-top: 4px; }

.sub-group-title {
  font-size: 12px; color: var(--text-muted); margin: 0 0 10px;
  font-weight: 600;
}

.actions-bar {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; margin-top: 20px;
  position: sticky; bottom: 20px;
}
.saved-msg { color: var(--down-green); font-size: 13px; font-weight: 600; }
.error-msg { color: var(--up-red); font-size: 13px; }
.actions-right { display: flex; gap: 10px; }
.btn-reset {
  padding: 8px 18px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary); font-size: 13px; cursor: pointer;
}
.btn-save {
  padding: 8px 24px; border-radius: 4px; border: none;
  background: var(--border); color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-save.dirty {
  background: var(--accent); color: #fff;
}

/* Strategy2 section */
.strategy2-section { border-color: rgba(255, 215, 0, 0.2); }
.strategy2-title { color: #ffd700; }
.section-hint { font-size: 12px; color: var(--text-muted); margin: -10px 0 16px; line-height: 1.5; }
.info-msg {
  margin-top: 16px; padding: 10px 14px; border-radius: 4px;
  background: rgba(255, 215, 0, 0.06); border: 1px solid rgba(255, 215, 0, 0.15);
  font-size: 12px; color: var(--text-muted); line-height: 1.5;
}
</style>
