<template>
  <div class="detail-layout">
    <!-- LEFT: Analysis Summary -->
    <div class="left-panel">
      <div class="stock-id">
        <div class="name">{{ stock.name || '--' }}</div>
        <div class="code">{{ stock.code }} · {{ stock.market || 'A股' }}</div>
        <div class="price-row">
          <span class="price" :class="priceColor">{{ stock.latest_close?.toFixed(2) || '--' }}</span>
          <span class="change" :class="priceColor" v-if="stock.change">{{ stock.change }}</span>
        </div>
        <div class="tags">
          <SignalBadge :type="score >= 80 ? 'strong' : score >= 70 ? 'medium' : 'weak'">
            {{ score >= 80 ? '强候选' : score >= 70 ? '中等候选' : '弱候选' }} · {{ score }}分
          </SignalBadge>
          <SignalBadge type="breakout" v-if="stock.is_breakout">◉ 已突破</SignalBadge>
          <SignalBadge type="volume" v-if="stock.is_volume_breakout">放量确认</SignalBadge>
          <SignalBadge type="medium" v-if="stock.pattern_type">{{ stock.pattern_type }}</SignalBadge>
          <SignalBadge :type="dryVerdictType" v-if="stock.dry_stable_verdict">{{ stock.dry_stable_verdict }}</SignalBadge>
        </div>
      </div>

      <div class="section-label">干稳低吸</div>
      <div class="kv-list">
        <div class="kv"><span class="k">量干 / 价稳</span><span class="v blue">{{ stock.volume_dry_score ?? '--' }} / {{ stock.price_stable_score ?? '--' }}</span></div>
        <div class="kv"><span class="k">形态分</span><span class="v">{{ stock.pattern_score_20 ?? '--' }} / 20</span></div>
        <div class="kv"><span class="k">形态类型</span><span class="v">{{ stock.pattern_type || '--' }}</span></div>
        <div class="kv"><span class="k">大盘环境</span><span class="v" :class="marketClass">{{ stock.market_status || '一般' }}</span></div>
        <div class="kv"><span class="k">建议仓位</span><span class="v">{{ stock.position_advice || '--' }}</span></div>
      </div>

      <div class="section-label">形态评分</div>
      <div class="score-section">
        <ScoreBar label="杯体结构" :current="cupScore" :max="35" />
        <ScoreBar label="柄部结构" :current="handleScore" :max="25" />
        <ScoreBar label="成交量结构" :current="volScore" :max="20" />
        <ScoreBar label="前置上涨趋势" :current="trendScore" :max="10" />
        <ScoreBar label="突破确认" :current="breakoutScore" :max="10" />
        <div class="score-total">
          <span class="total-label">形态总分</span>
          <span class="total-value">{{ score }}</span>
        </div>
      </div>

      <div class="section-label">关键价格</div>
      <div class="kv-list">
        <div class="kv"><span class="k">低吸区间</span><span class="v blue">{{ entryZone }}</span></div>
        <div class="kv"><span class="k">Pivot</span><span class="v red">{{ price(stock.pivot || stock.breakout_price) }}</span></div>
        <div class="kv"><span class="k">止损位</span><span class="v orange">{{ price(stopLoss) }}</span></div>
        <div class="kv"><span class="k">第一止盈</span><span class="v blue">{{ price(target1) }}</span></div>
        <div class="kv"><span class="k">止损距离</span><span class="v red">{{ riskPct?.toFixed(1) }}%</span></div>
        <div class="kv"><span class="k">盈亏比</span><span class="v blue">{{ rr1?.toFixed(1) }} : 1</span></div>
      </div>

      <div class="section-label">关键日期</div>
      <div class="kv-list">
        <div class="kv"><span class="k">左杯口</span><span class="v">{{ stock.left_high_date || '--' }}</span></div>
        <div class="kv"><span class="k">杯底</span><span class="v">{{ stock.cup_low_date || '--' }}</span></div>
        <div class="kv"><span class="k">右杯口</span><span class="v">{{ stock.right_high_date || '--' }}</span></div>
        <div class="kv"><span class="k">柄部低点</span><span class="v">{{ stock.handle_low_date || '--' }}</span></div>
      </div>

      <RiskBox>
        本页面为技术形态筛选工具，不构成投资建议。形态识别存在假突破可能，请结合基本面和其他技术指标综合判断。
      </RiskBox>
    </div>

    <!-- CENTER: K-line Chart -->
    <div class="center-panel">
      <div class="chart-toolbar">
        <div class="chart-left">
        </div>
        <div class="chart-right">
          <span>{{ structureSummary }}</span>
        </div>
      </div>
      <div ref="chartRef" class="chart-body"></div>
      <div class="structure-readout">
        <div class="structure-title">{{ isVcp ? 'VCP 收缩结构' : '杯柄结构时间线' }}</div>
        <div class="structure-grid" v-if="isVcp">
          <div class="sc"><div class="phase">低吸区间</div><div class="val">{{ entryZone }}</div><div class="vrd blue">缩量企稳观察</div></div>
          <div class="sc"><div class="phase">Pivot</div><div class="val">{{ price(stock.pivot || stock.breakout_price) }}</div><div class="vrd gold">突破参考</div></div>
          <div class="sc"><div class="phase">止损</div><div class="val">{{ price(stopLoss) }}</div><div class="vrd blue">结构失效线</div></div>
          <div class="sc"><div class="phase">目标价</div><div class="val">{{ price(target1) }}</div><div class="vrd blue">第一目标</div></div>
          <div class="sc"><div class="phase">干稳评级</div><div class="val">{{ stock.dry_stable_verdict || '--' }}</div><div class="vrd" :class="stock.dry_stable_verdict === '可低吸' ? 'gold' : 'blue'">{{ stock.pattern_score_20 ?? '--' }}/20</div></div>
        </div>
        <div class="structure-grid" v-else>
          <div class="sc"><div class="phase">① 前置上涨</div><div class="val">{{ stock.left_high_price?.toFixed(2) }}</div><div class="vrd blue">左杯口高点</div></div>
          <div class="sc"><div class="phase">② 杯体下降</div><div class="val">{{ stock.cup_depth_pct?.toFixed(1) }}%</div><div class="vrd gold">深度{{ stock.cup_depth_pct >= 12 && stock.cup_depth_pct <= 33 ? '合理' : '偏离' }}</div></div>
          <div class="sc"><div class="phase">③ 杯底整理</div><div class="val">{{ stock.cup_duration }}d</div><div class="vrd blue">杯体{{ stock.cup_duration >= 50 ? '成熟' : '偏短' }}</div></div>
          <div class="sc"><div class="phase">④ 右侧回升</div><div class="val">{{ stock.right_high_price?.toFixed(2) }}</div><div class="vrd blue">右杯口高点</div></div>
          <div class="sc"><div class="phase">⑤ 柄部收缩</div><div class="val">{{ stock.handle_depth_pct?.toFixed(1) }}%</div><div class="vrd" :class="stock.handle_depth_pct <= 12 ? 'gold' : 'blue'">{{ stock.handle_depth_pct <= 12 ? '回撤合理' : '回撤偏深' }}</div></div>
        </div>
      </div>
    </div>

    <!-- RIGHT: Watchlist -->
    <div class="right-panel">
      <div class="wl-header">
        <span class="wl-title">候选观察列表</span>
        <span class="wl-count">{{ watchlist.length }} 只</span>
      </div>
      <div class="wl-filters">
        <button class="wlf" :class="{ active: wlFilter === 'all' }" @click="wlFilter = 'all'">全部</button>
        <button class="wlf" :class="{ active: wlFilter === 'breakout' }" @click="wlFilter = 'breakout'">已突破</button>
        <button class="wlf" :class="{ active: wlFilter === 'near' }" @click="wlFilter = 'near'">接近突破</button>
      </div>
      <div class="wl-list">
        <div v-for="w in filteredWatchlist" :key="w.code"
          class="wl-item" :class="{ active: w.code === stock.code }"
          @click="goToStock(w.code)"
        >
          <div class="wl-bar" :class="w.is_breakout ? 'wl-red' : w.score >= 70 ? 'wl-orange' : 'wl-blue'"></div>
          <div class="wl-info">
            <span class="wl-code">{{ w.code }}</span>
            <span class="wl-name">{{ w.name }}</span>
            <div class="wl-detail" v-if="w.is_breakout">已突破 · 放量{{ w.vol_multiplier?.toFixed(1) }}×</div>
            <div class="wl-detail" v-else>距突破 {{ distFromBreakout(w) }}</div>
          </div>
          <span class="wl-score" :class="w.score >= 80 ? 'gold' : w.score >= 70 ? '' : 'muted'">{{ w.score }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'
import * as echarts from 'echarts'
import SignalBadge from '../components/SignalBadge.vue'
import ScoreBar from '../components/ScoreBar.vue'
import RiskBox from '../components/RiskBox.vue'

const route = useRoute()
const router = useRouter()
const { getCandidate, getCandidates } = useApi()

const stock = ref({})
const score = ref(0)
const watchlist = ref([])
const wlFilter = ref('all')
const chartRef = ref(null)
let chart = null

const stopLoss = computed(() => stock.value.stop_loss || (stock.value.handle_low_price ? (stock.value.handle_low_price * 0.98) : null))
const target1 = computed(() => {
  if (stock.value.target_1) return stock.value.target_1
  const cp = stock.value.latest_close
  const sl = parseFloat(stopLoss.value)
  if (!cp || !sl) return null
  return cp + 2 * (cp - sl)
})
const riskPct = computed(() => {
  if (stock.value.risk_percent != null) return Number(stock.value.risk_percent)
  const cp = stock.value.latest_close
  const sl = parseFloat(stopLoss.value)
  if (!cp || !sl) return 0
  return ((cp - sl) / cp * 100)
})
const rr1 = computed(() => {
  if (stock.value.rr1 != null) return Number(stock.value.rr1)
  const cp = stock.value.latest_close
  const sl = parseFloat(stopLoss.value)
  const t1 = parseFloat(target1.value)
  if (!cp || !sl || !t1 || cp <= sl) return 0
  return ((t1 - cp) / (cp - sl))
})
const priceColor = computed(() => stock.value.change?.startsWith('+') ? 'red' : 'green')
const entryZone = computed(() => {
  if (!stock.value.entry_zone_low || !stock.value.entry_zone_high) return '--'
  return `${price(stock.value.entry_zone_low)} - ${price(stock.value.entry_zone_high)}`
})
const dryVerdictType = computed(() => {
  if (stock.value.dry_stable_verdict === '可低吸') return 'strong'
  if (stock.value.dry_stable_verdict === '突破确认') return 'breakout'
  return 'medium'
})
const marketClass = computed(() => {
  if (stock.value.market_status === '良好') return 'red'
  if (stock.value.market_status === '较差') return 'green'
  return 'orange'
})
const isVcp = computed(() => stock.value.key_pattern_type === 'vcp')
const structureSummary = computed(() => {
  if (isVcp.value) return `VCP · ${stock.value.pattern_type || '收缩结构'}`
  const duration = stock.value.cup_duration || '--'
  const depth = stock.value.cup_depth_pct != null ? stock.value.cup_depth_pct.toFixed(1) : '--'
  return `${duration}d 杯体 · 深度 ${depth}%`
})

function price(v) {
  return v ? Number(v).toFixed(2) : '--'
}

// Dynamic sub-scores based on cup/handle data
const cupScore = computed(() => {
  const s = stock.value; let v = 0
  const d = s.cup_depth_pct || 0
  if (d >= 12 && d <= 33) v += 10; else if (d > 33 && d <= 45) v += 5; else v += 3
  const dur = s.cup_duration || 0
  if (dur >= 50 && dur <= 120) v += 8; else if (dur >= 35 && dur <= 180) v += 4
  const dev = s.lip_deviation_pct || 0
  if (dev <= 5) v += 7; else if (dev <= 8) v += 5; else if (dev <= 12) v += 3
  v += 6; return Math.min(v, 35)
})
const handleScore = computed(() => {
  const s = stock.value; let v = 0
  const d = s.handle_depth_pct || 0; const dur = s.handle_duration || 0
  if (dur >= 5 && dur <= 20) v += 8; else if (dur > 20 && dur <= 30) v += 5
  if (d <= 8) v += 10; else if (d <= 12) v += 7; else if (d <= 18) v += 3
  if (d <= 10) v += 7; else if (d <= 15) v += 4
  return Math.min(v, 25)
})
const volScore = computed(() => stock.value.is_volume_breakout ? 17 : 10)
const trendScore = computed(() => {
  const s = stock.value
  if (!s.left_high_price || !s.cup_low_price) return 6
  const cupLow = s.cup_low_price
  const cupDuration = s.cup_duration || 60
  // Estimate: cup formed from ~half of cup_duration before left_high
  const preLow = cupLow * 0.85  // rough estimate
  const gain = (s.left_high_price - preLow) / preLow
  if (gain >= 0.25) return 10
  if (gain >= 0.15) return 7
  if (gain >= 0.10) return 4
  return 3
})
const breakoutScore = computed(() => {
  const s = stock.value
  if (s.is_breakout && s.is_volume_breakout) return 10
  if (s.is_breakout) return 7
  return 3
})

const filteredWatchlist = computed(() => {
  if (wlFilter.value === 'breakout') return watchlist.value.filter(w => w.is_breakout)
  if (wlFilter.value === 'near') return watchlist.value.filter(w => !w.is_breakout && w.score >= 70)
  return watchlist.value
})

function distFromBreakout(w) {
  if (!w.breakout_price || !w.latest_close) return '--'
  return ((w.latest_close - w.breakout_price) / w.breakout_price * 100).toFixed(1) + '%'
}

function goToStock(code) {
  router.push(`/stock/${code}`)
}

async function initChart() {
  if (!chartRef.value) return
  if (chart) chart.dispose()

  const s = stock.value
  const code = s.code
  if (!code) return

  // Fetch real OHLC data from API
  let ohlcRaw = []
  try {
    const res = await fetch(`/api/stock/${code}/ohlc`)
    const json = await res.json()
    ohlcRaw = json.data || []
  } catch (e) {
    return
  }

  if (!ohlcRaw.length) return

  chart = echarts.init(chartRef.value, 'dark')

  const dates = ohlcRaw.map(d => d.date)
  const ohlc = ohlcRaw.map(d => [+(d.open ?? 0).toFixed(2), +(d.close ?? 0).toFixed(2), +(d.low ?? 0).toFixed(2), +(d.high ?? 0).toFixed(2)])
  const volumes = ohlcRaw.map((d, i) => [i, Math.round(d.volume || 0), d.close >= d.open ? 1 : -1])

  // Mark key pattern dates on chart
  const markPoints = []
  if (s.left_high_date) markPoints.push({ name: '左杯口', coord: [s.left_high_date, s.left_high_price], value: '左杯口', symbol: 'pin', symbolSize: 30, itemStyle: { color: '#F59E0B' }, label: { show: true, color: '#F59E0B', fontSize: 10 } })
  if (s.cup_low_date) markPoints.push({ name: '杯底', coord: [s.cup_low_date, s.cup_low_price], value: '杯底', symbol: 'pin', symbolSize: 30, itemStyle: { color: '#EF4444' }, label: { show: true, color: '#EF4444', fontSize: 10 } })
  if (s.right_high_date) markPoints.push({ name: '右杯口', coord: [s.right_high_date, s.right_high_price], value: '右杯口', symbol: 'pin', symbolSize: 30, itemStyle: { color: '#F59E0B' }, label: { show: true, color: '#F59E0B', fontSize: 10 } })
  if (s.handle_low_date) markPoints.push({ name: '柄部低点', coord: [s.handle_low_date, s.handle_low_price], value: '柄部低点', symbol: 'pin', symbolSize: 30, itemStyle: { color: '#4F7DFF' }, label: { show: true, color: '#4F7DFF', fontSize: 10 } })

  const option = {
    backgroundColor: '#070B14',
    grid: [
      { left: '8%', right: '3%', top: '5%', height: '65%' },
      { left: '8%', right: '3%', top: '78%', height: '15%' },
    ],
    xAxis: [
      { type: 'category', data: dates, gridIndex: 0, axisLine: { lineStyle: { color: '#1F2A3A' } }, axisLabel: { color: '#5A6A7E', fontSize: 10 } },
      { type: 'category', data: dates, gridIndex: 1, axisLine: { lineStyle: { color: '#1F2A3A' } }, axisLabel: { show: false } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, scale: true, splitLine: { lineStyle: { color: '#1F2A3A', type: 'dashed' } }, axisLabel: { color: '#5A6A7E', fontSize: 10 } },
      { type: 'value', gridIndex: 1, splitLine: { show: false }, axisLabel: { color: '#5A6A7E', fontSize: 9 } },
    ],
    series: [
      {
        type: 'candlestick', data: ohlc,
        itemStyle: { color: '#EF4444', color0: '#22C55E', borderColor: '#EF4444', borderColor0: '#22C55E' },
        markPoint: markPoints.length ? { data: markPoints, symbol: 'circle', symbolSize: 6, label: { fontSize: 9, color: '#fff' } } : undefined,
      },
      {
        type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: {
          color: function (params) { return params.data[2] > 0 ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)' }
        },
      },
    ],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  }
  chart.setOption(option)
}

let resizeHandler = null

onMounted(async () => {
  try {
    const code = route.params.code
    if (code) {
      const data = await getCandidate(code)
      if (data) {
        stock.value = data
        score.value = data.score || 0
      }
    }
    // Load watchlist
    const cands = await getCandidates()
    watchlist.value = (cands.candidates || []).map(c => ({
      code: c.code, name: c.name, score: c.score,
      is_breakout: c.is_breakout, is_volume_breakout: c.is_volume_breakout,
      breakout_price: c.breakout_price, latest_close: c.latest_close,
      vol_multiplier: c.vol_multiplier,
      dry_stable_verdict: c.dry_stable_verdict,
    }))
    await nextTick()
    initChart()
    resizeHandler = () => chart?.resize()
    window.addEventListener('resize', resizeHandler)
  } catch (e) {
    console.error('Failed to load stock detail:', e)
  }
})
onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
</script>

<style scoped>
.detail-layout {
  display: grid; grid-template-columns: 280px 1fr 280px; height: calc(100vh - 48px);
}
@media (max-width: 1280px) { .detail-layout { grid-template-columns: 260px 1fr 0; } .right-panel { display: none; } }
.left-panel, .right-panel {
  background: var(--bg-panel); overflow-y: auto;
}
.left-panel { border-right: 1px solid var(--border); }
.right-panel { border-left: 1px solid var(--border); display: flex; flex-direction: column; }

.stock-id { padding: 16px; border-bottom: 1px solid var(--border); }
.name { font-size: 20px; font-weight: 700; }
.code { font-size: 13px; color: var(--accent); font-family: var(--font-mono); margin-top: 2px; }
.price-row { display: flex; align-items: baseline; gap: 10px; margin-top: 10px; }
.price { font-size: 32px; font-weight: 700; font-family: var(--font-mono); }
.red { color: var(--up-red); }
.green { color: var(--down-green); }
.change { font-size: 14px; }
.tags { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }

.section-label {
  font-size: 11px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; padding: 14px 16px 6px;
}
.score-section { padding: 0 16px 12px; }
.score-total {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--border);
}
.total-label { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.total-value { font-size: 32px; font-weight: 700; font-family: var(--font-mono); color: var(--gold); }

.kv-list { padding: 0 16px 8px; }
.kv { display: flex; justify-content: space-between; padding: 4px 0; font-size: 12px; }
.k { color: var(--text-muted); }
.v { color: var(--text-primary); font-family: var(--font-mono); font-size: 12px; }
.v.red { color: var(--up-red); }
.v.orange { color: var(--warn-orange); }
.v.blue { color: var(--accent); }

.center-panel { display: flex; flex-direction: column; overflow: hidden; }
.chart-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px; background: var(--bg-panel); border-bottom: 1px solid var(--border);
}
.ct {
  font-size: 11px; padding: 4px 10px; border-radius: 3px;
  border: 1px solid transparent; background: transparent; color: var(--text-muted); cursor: pointer;
}
.ct.active { background: rgba(79,125,255,0.12); border-color: var(--accent); color: var(--accent); }
.chart-right { font-size: 11px; color: var(--text-muted); }
.chart-body { flex: 1; min-height: 400px; }
.structure-readout { padding: 12px 16px; background: var(--bg-panel); border-top: 1px solid var(--border); }
.structure-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.structure-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }
.sc { background: var(--bg-card); border: 1px solid var(--border); border-radius: 4px; padding: 8px; }
.phase { font-size: 10px; color: var(--text-muted); margin-bottom: 2px; }
.val { font-size: 12px; font-family: var(--font-mono); color: var(--text-primary); font-weight: 600; }
.vrd { font-size: 10px; margin-top: 2px; }
.vrd.blue { color: var(--accent); }
.vrd.gold { color: var(--gold); }

/* Watchlist */
.wl-header { padding: 14px 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; }
.wl-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.wl-count { font-size: 12px; color: var(--accent); }
.wl-filters { padding: 8px 16px; border-bottom: 1px solid var(--border); display: flex; gap: 5px; }
.wlf {
  font-size: 10px; padding: 3px 8px; border-radius: 3px;
  border: 1px solid var(--border); background: transparent; color: var(--text-muted); cursor: pointer;
}
.wlf.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.wl-list { flex: 1; overflow-y: auto; }
.wl-item {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-bottom: 1px solid rgba(31,42,58,0.5);
  cursor: pointer; transition: background 0.1s;
}
.wl-item:hover { background: rgba(79,125,255,0.03); }
.wl-item.active { background: rgba(79,125,255,0.08); border-left: 3px solid var(--accent); padding-left: 11px; }
.wl-bar { width: 3px; height: 28px; border-radius: 2px; flex-shrink: 0; }
.wl-red { background: var(--up-red); }
.wl-orange { background: var(--warn-orange); }
.wl-blue { background: var(--accent); }
.wl-info { flex: 1; min-width: 0; }
.wl-code { font-family: var(--font-mono); font-size: 12px; color: var(--accent); font-weight: 600; }
.wl-name { font-size: 12px; color: var(--text-primary); margin-left: 4px; }
.wl-detail { font-size: 10px; color: var(--text-muted); margin-top: 1px; }
.wl-score { font-size: 16px; font-weight: 700; font-family: var(--font-mono); flex-shrink: 0; color: var(--text-primary); }
.wl-score.gold { color: var(--gold); }
.wl-score.muted { color: var(--text-muted); }
</style>
