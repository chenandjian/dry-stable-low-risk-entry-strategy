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

      <div class="section-label" v-if="tradePlan">交易计划</div>
      <div class="plan-list" v-if="tradePlan">
        <div class="plan-row">
          <span class="plan-k">买入依据</span>
          <span class="plan-v">{{ listText(tradePlan.buy_reasons) }}</span>
        </div>
        <div class="plan-row">
          <span class="plan-k">止损逻辑</span>
          <span class="plan-v">{{ listText(tradePlan.stop_reasons) }}</span>
        </div>
        <div class="plan-row">
          <span class="plan-k">目标逻辑</span>
          <span class="plan-v">{{ listText(tradePlan.target_reasons) }}</span>
        </div>
        <div class="plan-row" v-if="tradePlan.invalid_conditions?.length">
          <span class="plan-k">失效条件</span>
          <span class="plan-v orange">{{ listText(tradePlan.invalid_conditions) }}</span>
        </div>
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
      <div class="chart-legend">
        <span class="legend-group">MA</span>
        <span class="legend-item"><i style="background:#F59E0B"></i>5</span>
        <span class="legend-item"><i style="background:#EF4444"></i>10</span>
        <span class="legend-item"><i style="background:#4F7DFF"></i>20</span>
        <span class="legend-item"><i style="background:#22C55E"></i>50</span>
        <span class="legend-item"><i style="background:#A855F7"></i>100</span>
        <span class="legend-item"><i style="background:#EC4899"></i>200</span>
        <span class="legend-sep">|</span>
        <span class="legend-group">RSI</span>
        <span class="legend-item"><i style="background:#4F7DFF"></i>6</span>
        <span class="legend-item"><i style="background:#F59E0B"></i>12</span>
        <span class="legend-item"><i style="background:#EF4444"></i>24</span>
      </div>
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
import SignalBadge from '../components/SignalBadge.vue'
import ScoreBar from '../components/ScoreBar.vue'
import RiskBox from '../components/RiskBox.vue'
import { createChart, CandlestickSeries, LineSeries, HistogramSeries, createSeriesMarkers } from 'lightweight-charts'

// --- Helper: MA calculation ---
function calcMA(data, period) {
  const result = []
  for (let i = period - 1; i < data.length; i++) {
    let sum = 0
    for (let j = i - period + 1; j <= i; j++) {
      sum += data[j].close
    }
    result.push({ time: data[i].time, value: sum / period })
  }
  return result
}

// --- Helper: RSI calculation ---
function calcRSI(data, period) {
  const result = []
  let gains = 0, losses = 0

  // First average
  for (let i = 1; i <= period; i++) {
    const change = data[i].close - data[i - 1].close
    if (change > 0) gains += change
    else losses -= change
  }

  let avgGain = gains / period
  let avgLoss = losses / period

  for (let i = period + 1; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close
    const gain = change > 0 ? change : 0
    const loss = change < 0 ? -change : 0

    avgGain = (avgGain * (period - 1) + gain) / period
    avgLoss = (avgLoss * (period - 1) + loss) / period

    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
    const rsi = 100 - (100 / (1 + rs))
    result.push({ time: data[i].time, value: rsi })
  }

  return result
}

const route = useRoute()
const router = useRouter()
const { getCandidate, getCandidates } = useApi()

const stock = ref({})
const score = ref(0)
const watchlist = ref([])
const wlFilter = ref('all')
const chartRef = ref(null)

async function loadStock(code) {
  try {
    const data = await getCandidate(code)
    if (data) {
      stock.value = data
      score.value = data.score || 0
    }
  } catch (e) {
    console.error('Failed to load stock detail:', e)
  }
}

async function loadWatchlist() {
  const taskId = stock.value.task_id
  const cands = taskId
    ? await getCandidates({ task_id: taskId })
    : await getCandidates()
  watchlist.value = (cands.candidates || []).map(c => ({
    code: c.code, name: c.name, score: c.score,
    is_breakout: c.is_breakout, is_volume_breakout: c.is_volume_breakout,
    breakout_price: c.breakout_price, latest_close: c.latest_close,
    vol_multiplier: c.vol_multiplier,
    dry_stable_verdict: c.dry_stable_verdict,
  }))
}

// Watch for route param changes (e.g., /stock/000001 -> /stock/000002)
watch(() => route.params.code, async (newCode) => {
  if (newCode) {
    await loadStock(newCode)
    await loadWatchlist()
    await nextTick()
    await initChart()
  }
})

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
const tradePlan = computed(() => stock.value.trade_plan || null)
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
function listText(list) {
  return list?.length ? list.join('；') : '--'
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
  if (!chartRef.value) { console.warn('[StockDetail] chartRef not ready'); return }
  // Dispose previous chart
  if (chartRef.value._chart) { chartRef.value._chart.remove(); chartRef.value._chart = null }
  chartRef.value.innerHTML = ''

  const s = stock.value
  const code = s.code
  if (!code) { console.warn('[StockDetail] no stock code'); return }

  let ohlcRaw = []
  try {
    const res = await fetch(`/api/stock/${code}/ohlc`)
    if (!res.ok) { console.warn(`[StockDetail] OHLC fetch ${res.status}`); return }
    const json = await res.json()
    ohlcRaw = json.data || []
  } catch (e) { console.error('[StockDetail] OHLC fetch error:', e); return }
  if (!ohlcRaw.length) { console.warn('[StockDetail] OHLC data empty'); return }

  // Ensure container has dimensions after clear
  await new Promise(r => requestAnimationFrame(r))

  const w = chartRef.value.clientWidth || 800
  const h = chartRef.value.clientHeight || 500
  console.log('[StockDetail] creating chart', { w, h, dataPoints: ohlcRaw.length })

  const chart = createChart(chartRef.value, {
    layout: {
      background: { color: '#070B14' },
      textColor: '#5A6A7E',
    },
    grid: {
      vertLines: { color: '#1F2A3A' },
      horzLines: { color: '#1F2A3A' },
    },
    crosshair: { mode: 0 },
    timeScale: {
      borderColor: '#1F2A3A',
      timeVisible: true,
    },
    rightPriceScale: {
      borderColor: '#1F2A3A',
    },
    width: w,
    height: h,
  })

  // Build candle data
  const candleData = ohlcRaw.map(d => ({
    time: d.date,
    open: +(d.open ?? 0),
    high: +(d.high ?? 0),
    low: +(d.low ?? 0),
    close: +(d.close ?? 0),
  }))

  // Candlestick series
  const candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: '#EF4444',
    downColor: '#22C55E',
    borderUpColor: '#EF4444',
    borderDownColor: '#22C55E',
    wickUpColor: '#EF4444',
    wickDownColor: '#22C55E',
  })
  candleSeries.setData(candleData)
  console.log('[StockDetail] chart ready, candles:', candleData.length)

  // Volume series (overlay on bottom)
  const volumeSeries = chart.addSeries(HistogramSeries, {
    color: 'rgba(239,68,68,0.4)',
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  })
  volumeSeries.priceScale().applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  })

  const volumeData = ohlcRaw.map(d => ({
    time: d.date,
    value: Math.round(d.volume || 0),
    color: d.close >= d.open ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)',
  }))
  volumeSeries.setData(volumeData)

  // MA lines (5, 10, 20, 50, 100, 200)
  const maPeriods = [5, 10, 20, 50, 100, 200]
  const maColors = ['#F59E0B', '#EF4444', '#4F7DFF', '#22C55E', '#A855F7', '#EC4899']

  maPeriods.forEach((period, i) => {
    const maData = calcMA(candleData, period)
    const maSeries = chart.addSeries(LineSeries, {
      color: maColors[i],
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    maSeries.setData(maData)
  })

  // RSI pane (overlaid in main chart, bottom-margin)
  const rsiPeriods = [6, 12, 24]
  const rsiColors = ['#4F7DFF', '#F59E0B', '#EF4444']

  rsiPeriods.forEach((period, i) => {
    const rsiData = calcRSI(candleData, period)
    const rsiSeries = chart.addSeries(LineSeries, {
      color: rsiColors[i],
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      priceScaleId: 'rsi',
    })
    rsiSeries.setData(rsiData)
  })

  // Configure RSI price scale
  chart.priceScale('rsi').applyOptions({
    scaleMargins: { top: 0.85, bottom: 0 },
  })

  // Store chart reference for resize
  chartRef.value._chart = chart

  // Add markers for key pattern dates
  const markers = []
  if (s.left_high_date) markers.push({ time: s.left_high_date, position: 'aboveBar', color: '#F59E0B', shape: 'arrowDown', text: '左杯口' })
  if (s.cup_low_date) markers.push({ time: s.cup_low_date, position: 'belowBar', color: '#EF4444', shape: 'arrowUp', text: '杯底' })
  if (s.right_high_date) markers.push({ time: s.right_high_date, position: 'aboveBar', color: '#F59E0B', shape: 'arrowDown', text: '右杯口' })
  if (s.handle_low_date) markers.push({ time: s.handle_low_date, position: 'belowBar', color: '#4F7DFF', shape: 'arrowUp', text: '柄低' })
  if (markers.length) createSeriesMarkers(candleSeries, markers.filter(m => m.time))

  chart.timeScale().fitContent()
}

let resizeHandler = null

onMounted(async () => {
  const code = route.params.code
  if (code) await loadStock(code)

  // Load watchlist from same task as current stock
  try {
    await loadWatchlist()
  } catch (e) {
    console.error('[StockDetail] Failed to load watchlist:', e)
  }

  await nextTick()
  await initChart()
  resizeHandler = () => {
    const c = chartRef.value?._chart
    if (c) {
      c.applyOptions({
        width: chartRef.value.clientWidth,
        height: chartRef.value.clientHeight || 500
      })
    }
  }
  window.addEventListener('resize', resizeHandler)
})
onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  chartRef.value?._chart?.remove()
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
.plan-list { padding: 0 16px 8px; }
.plan-row { padding: 6px 0; border-bottom: 1px solid rgba(31,42,58,0.45); }
.plan-row:last-child { border-bottom: none; }
.plan-k { display: block; color: var(--text-muted); font-size: 11px; margin-bottom: 3px; }
.plan-v { display: block; color: var(--text-secondary); font-size: 12px; line-height: 1.45; }
.plan-v.orange { color: var(--warn-orange); }

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
.chart-legend {
  display: flex; align-items: center; gap: 6px; padding: 6px 16px;
  background: var(--bg-panel); border-top: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted); flex-wrap: wrap;
}
.legend-group { font-weight: 600; color: var(--text-secondary); margin-right: 4px; }
.legend-item { display: flex; align-items: center; gap: 3px; margin-right: 2px; }
.legend-item i { display: inline-block; width: 12px; height: 2px; border-radius: 1px; }
.legend-sep { color: var(--border); margin: 0 4px; }
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
.wl-item.active { background: rgba(79,125,255,0.12); border-left: 3px solid var(--accent); padding-left: 11px; }
.wl-item.active .wl-code { color: #fff; }
.wl-item.active .wl-score { color: var(--gold); }
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
