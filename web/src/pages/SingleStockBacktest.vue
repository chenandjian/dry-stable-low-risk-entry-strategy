<template>
  <div class="backtest-layout">
    <aside class="left-panel">
      <div class="panel-card">
        <div class="section-title">单股杯柄回测</div>
        <label>股票代码</label>
        <input v-model.trim="form.code" class="form-input" aria-label="股票代码" />
        <label>回测开始日期</label>
        <input v-model="form.startDate" class="form-input date-input" type="date"
          @blur="validateDate('startDate')" />
        <span class="date-err" v-if="dateErrors.startDate">{{ dateErrors.startDate }}</span>
        <label>回测结束日期</label>
        <input v-model="form.endDate" class="form-input date-input" type="date"
          @blur="validateDate('endDate')" />
        <span class="date-err" v-if="dateErrors.endDate">{{ dateErrors.endDate }}</span>
        <div class="section-title small">指定柄区域（可选）</div>
        <label>柄开始日期</label>
        <input v-model="form.handleStartDate" class="form-input date-input" type="date"
          @blur="validateDate('handleStartDate')" />
        <span class="date-err" v-if="dateErrors.handleStartDate">{{ dateErrors.handleStartDate }}</span>
        <label>柄结束日期</label>
        <input v-model="form.handleEndDate" class="form-input date-input" type="date"
          @blur="validateDate('handleEndDate')" />
        <span class="date-err" v-if="dateErrors.handleEndDate">{{ dateErrors.handleEndDate }}</span>
        <button class="run-btn" :disabled="loading" @click="runBacktest">
          {{ loading ? '计算中...' : '运行回测' }}
        </button>
      </div>

      <div class="panel-card diagnosis-card">
        <div class="section-title">指定柄诊断</div>
        <div v-if="!result?.specifiedDiagnosis" class="empty-text">未指定柄区域</div>
        <div v-else>
          <div class="diagnosis-status" :class="result.specifiedDiagnosis.passed ? 'pass' : 'fail'">
            {{ result.specifiedDiagnosis.passed ? '符合策略' : '不符合策略' }}
          </div>
          <div class="rule-counts">
            <span>通过 {{ result.specifiedDiagnosis.passedRules?.length || 0 }}</span>
            <span>失败 {{ result.specifiedDiagnosis.failedRules?.length || 0 }}</span>
          </div>
          <div class="rule-list">
            <div v-for="rule in result.specifiedDiagnosis.failedRules" :key="rule.ruleName + rule.actualValue" class="rule-item" :class="rule.severity">
              <div class="rule-head"><span>{{ rule.ruleName }}</span><em>{{ severityText(rule.severity) }}</em></div>
              <div class="rule-line">要求：{{ rule.requiredValue }}</div>
              <div class="rule-line">实际：{{ rule.actualValue }}</div>
              <p>{{ rule.explanation }}</p>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <main class="main-panel">
      <div v-if="result?.dataCoverage?.coverageWarning" class="warning-card">
        ⚠ 数据覆盖不足 — 输入区间在可用范围之外，仅展示可用数据内的结果
        <div class="warning-detail">
          输入区间：{{ result.dataCoverage.requiredRange?.startDate || '--' }} ~ {{ result.dataCoverage.requiredRange?.endDate || '--' }}
          · 实际可用：{{ result.dataCoverage.availableRange?.startDate || '--' }} ~ {{ result.dataCoverage.availableRange?.endDate || '--' }}
        </div>
      </div>
      <div v-if="error" class="error-card">
        <div class="error-title">{{ error.message || error.error }}</div>
        <div v-if="error.requestedRange" class="error-detail">输入区间：{{ error.requestedRange.startDate }} ~ {{ error.requestedRange.endDate }}</div>
        <div v-if="error.requiredRange" class="error-detail">策略所需：{{ error.requiredRange.startDate }} ~ {{ error.requiredRange.endDate }}</div>
        <div v-if="error.availableRange" class="error-detail">当前可用：{{ error.availableRange.startDate || '--' }} ~ {{ error.availableRange.endDate || '--' }}</div>
        <div v-if="error.missingRanges?.length" class="error-detail">
          缺失区间：<span v-for="r in error.missingRanges" :key="r.startDate">{{ r.startDate }} ~ {{ r.endDate }}</span>
        </div>
      </div>

      <div class="metric-grid">
        <MetricCard label="识别区域" :value="summaryValue('totalPatterns')" />
        <MetricCard label="最高评分" :value="summaryValue('bestScore')" color="gold" />
        <MetricCard label="数据来源" :value="result?.dataCoverage?.source || '--'" color="blue" />
        <MetricCard label="策略版本" :value="result?.strategyVersion || '--'" />
      </div>

      <section class="chart-card">
        <div class="chart-header">
          <span>K线标记</span>
          <span class="hash" :title="result?.configHash">{{ shortHash }}</span>
        </div>
        <div ref="chartRef" class="chart-body"></div>
      </section>

      <section class="results-card">
        <div class="section-title">自动识别结果</div>
        <div v-if="!result" class="empty-text">请输入参数并运行回测</div>
        <div v-else-if="!result.patterns?.length" class="empty-text">该时间段未识别到符合杯柄策略的柄区域</div>
        <table v-else class="result-table">
          <thead><tr><th>首次发现</th><th>最后确认</th><th>类型</th><th>分数</th><th>决策</th><th>回撤</th><th>突破</th></tr></thead>
          <tbody>
            <tr v-for="p in result.patterns" :key="p.patternId" :class="{ selected: p.patternId === selectedPatternId }" @click="selectPattern(p.patternId)">
              <td>{{ p.firstDetectedDate }}</td>
              <td>{{ p.detectedDate }}</td>
              <td>{{ p.dryStable?.pattern_score?.type || '--' }}</td>
              <td class="score">{{ p.score }}</td>
              <td>{{ p.dryStable?.decision?.verdict || '--' }}</td>
              <td>{{ pct(p.handleDepthPct) }}</td>
              <td>{{ p.isBreakout ? '是' : '否' }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="selectedPattern" class="breakdown-card">
        <div class="section-title">评分拆解</div>
        <div class="breakdown-grid">
          <ScoreBar label="量干" :current="selectedPattern.dryStable?.volume_dry?.score || 0" :max="10" />
          <ScoreBar label="价稳" :current="selectedPattern.dryStable?.price_stable?.score || 0" :max="10" />
          <ScoreBar label="形态" :current="selectedPattern.dryStable?.pattern_score?.score || 0" :max="20" />
        </div>
        <div class="trade-plan">
          <div>低吸区间：{{ price(selectedPattern.dryStable?.key_prices?.entry_zone_low) }} ~ {{ price(selectedPattern.dryStable?.key_prices?.entry_zone_high) }}</div>
          <div>Pivot：{{ price(selectedPattern.dryStable?.key_prices?.pivot) }} · 止损：{{ price(selectedPattern.dryStable?.key_prices?.stop_loss) }}</div>
          <div>目标：{{ price(selectedPattern.dryStable?.key_prices?.target_1) }} / {{ price(selectedPattern.dryStable?.key_prices?.target_2) }} · RR：{{ selectedPattern.dryStable?.risk_reward?.rr1 ?? '--' }}</div>
        </div>
        <RiskBox>{{ selectedPattern.dryStable?.decision?.summary || '无决策说明' }}</RiskBox>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import ScoreBar from '../components/ScoreBar.vue'
import RiskBox from '../components/RiskBox.vue'

const route = useRoute()
const { runCupHandleBacktest } = useApi()
const chartRef = ref(null)
const chart = ref(null)
const candleSeries = ref(null)
const result = ref(null)
const error = ref(null)
const loading = ref(false)
const selectedPatternId = ref(null)

const form = ref({
  code: route.params.code || '',
  startDate: '',
  endDate: '',
  handleStartDate: '',
  handleEndDate: '',
})
const dateErrors = ref({})

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function validateDate(field) {
  const v = form.value[field]
  if (!v) { delete dateErrors.value[field]; return }
  if (!DATE_RE.test(v)) {
    dateErrors.value[field] = '格式应为 YYYY-MM-DD'
    return
  }
  const d = new Date(v + 'T00:00:00')
  if (isNaN(d.getTime())) {
    dateErrors.value[field] = '无效日期'
    return
  }
  delete dateErrors.value[field]
}

const selectedPattern = computed(() => (result.value?.patterns || []).find(p => p.patternId === selectedPatternId.value) || null)
const shortHash = computed(() => result.value?.configHash ? result.value.configHash.slice(0, 18) + '…' : '--')

function summaryValue(key) {
  const value = result.value?.summary?.[key]
  return value === null || value === undefined ? '--' : value
}
function pct(value) {
  return value === null || value === undefined ? '--' : `${Number(value).toFixed(1)}%`
}
function price(value) {
  return value === null || value === undefined ? '--' : Number(value).toFixed(2)
}
function severityText(severity) {
  return { info: '提示', low: '轻微', medium: '重要', high: '严重' }[severity] || severity
}
function selectPattern(id) {
  selectedPatternId.value = id
  drawMarkers()
}

async function runBacktest() {
  error.value = null
  result.value = null
  // Validate all date fields before submit
  for (const f of ['startDate','endDate','handleStartDate','handleEndDate']) {
    validateDate(f)
    if (dateErrors.value[f]) { error.value = { message: `${f}: ${dateErrors.value[f]}` }; return }
  }
  if (!form.value.startDate || !form.value.endDate) {
    error.value = { message: '请填写回测开始和结束日期' }; return
  }
  loading.value = true
  try {
    const payload = {
      startDate: form.value.startDate,
      endDate: form.value.endDate,
    }
    if (form.value.handleStartDate && form.value.handleEndDate) {
      payload.specifiedHandle = { startDate: form.value.handleStartDate, endDate: form.value.handleEndDate }
    }
    const body = await runCupHandleBacktest(form.value.code, payload)
    if (!body.ok) {
      error.value = body
      return
    }
    result.value = body
    selectedPatternId.value = body.patterns?.[0]?.id || null
    await nextTick()
    initChart()
  } finally {
    loading.value = false
  }
}

function initChart() {
  if (!chartRef.value || !result.value?.ohlc?.length) return
  if (chart.value) chart.value.remove()
  chart.value = createChart(chartRef.value, {
    width: chartRef.value.clientWidth || 800,
    height: 420,
    layout: { background: { color: '#0B1220' }, textColor: '#CBD5E1' },
    grid: { vertLines: { color: '#1E293B' }, horzLines: { color: '#1E293B' } },
    timeScale: { borderColor: '#334155' },
    rightPriceScale: { borderColor: '#334155' },
  })
  candleSeries.value = chart.value.addSeries(CandlestickSeries, {
    upColor: '#EF4444', downColor: '#22C55E', borderVisible: false,
    wickUpColor: '#EF4444', wickDownColor: '#22C55E',
  })
  candleSeries.value.setData(result.value.ohlc.map(row => ({
    time: row.date, open: row.open, high: row.high, low: row.low, close: row.close,
  })))
  drawMarkers()
  chart.value.timeScale().fitContent()
}

function drawMarkers() {
  if (!candleSeries.value || !result.value) return
  const markers = []
  for (const pattern of result.value.patterns || []) {
    const selected = pattern.id === selectedPatternId.value
    const color = selected ? '#FBBF24' : '#4F7DFF'
    markers.push({ time: pattern.handleStartDate, position: 'belowBar', color, shape: 'arrowUp', text: selected ? '柄开始' : '自动柄' })
    markers.push({ time: pattern.handleEndDate, position: 'aboveBar', color, shape: 'arrowDown', text: selected ? '柄结束' : '' })
    markers.push({ time: pattern.handleLowDate, position: 'belowBar', color: '#F59E0B', shape: 'circle', text: '柄低' })
    markers.push({ time: pattern.leftHighDate, position: 'aboveBar', color: '#64748B', shape: 'circle', text: '左杯口' })
    markers.push({ time: pattern.cupLowDate, position: 'belowBar', color: '#64748B', shape: 'circle', text: '杯底' })
    markers.push({ time: pattern.rightHighDate, position: 'aboveBar', color: '#64748B', shape: 'circle', text: '右杯口' })
  }
  const specified = result.value.specifiedDiagnosis
  if (specified) {
    markers.push({ time: specified.startDate, position: 'belowBar', color: '#A855F7', shape: 'arrowUp', text: '指定柄开始' })
    markers.push({ time: specified.endDate, position: 'aboveBar', color: '#A855F7', shape: 'arrowDown', text: '指定柄结束' })
  }
  createSeriesMarkers(candleSeries.value, markers.filter(m => m.time))
}

watch(() => route.params.code, code => { if (code) form.value.code = code })
onMounted(() => { if (route.params.code) form.value.code = route.params.code })
onUnmounted(() => { if (chart.value) chart.value.remove() })
</script>

<style scoped>
.backtest-layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; padding: 16px; color: var(--text-primary); }
.left-panel { display: flex; flex-direction: column; gap: 14px; }
.panel-card, .chart-card, .results-card, .breakdown-card, .error-card { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.section-title { font-size: 14px; font-weight: 700; margin-bottom: 12px; }
.section-title.small { margin-top: 14px; color: var(--text-secondary); }
label { display: block; margin: 10px 0 5px; font-size: 12px; color: var(--text-secondary); }
.form-input { width: 100%; background: var(--bg-card); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px; font-family: var(--font-mono); }
.date-input { color-scheme: dark; min-height: 38px; }
.date-input::-webkit-calendar-picker-indicator { filter: invert(0.8); cursor: pointer; }
.date-err { display: block; color: var(--up-red); font-size: 11px; margin-top: 2px; }
.run-btn { width: 100%; margin-top: 14px; padding: 10px; border: none; border-radius: 4px; background: var(--accent); color: #fff; font-weight: 700; cursor: pointer; }
.run-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.main-panel { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.chart-header { display: flex; justify-content: space-between; margin-bottom: 8px; color: var(--text-secondary); font-size: 12px; }
.chart-body { height: 420px; }
.hash { font-family: var(--font-mono); }
.result-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.result-table th, .result-table td { padding: 9px 8px; border-bottom: 1px solid var(--border); text-align: left; }
.result-table tr { cursor: pointer; }
.result-table tr.selected { background: rgba(79, 125, 255, 0.12); }
.score { color: var(--gold); font-weight: 700; }
.empty-text { color: var(--text-secondary); font-size: 13px; padding: 12px 0; }
.diagnosis-status { font-size: 18px; font-weight: 800; margin-bottom: 8px; }
.diagnosis-status.pass { color: var(--up-red); }
.diagnosis-status.fail { color: var(--down-green); }
.rule-counts { display: flex; gap: 12px; color: var(--text-secondary); font-size: 12px; margin-bottom: 10px; }
.rule-item { border-left: 3px solid var(--border); padding: 8px 10px; margin-bottom: 8px; background: var(--bg-card); }
.rule-item.high { border-left-color: var(--down-green); }
.rule-item.medium { border-left-color: var(--warn-orange); }
.rule-item.low { border-left-color: var(--accent); }
.rule-head { display: flex; justify-content: space-between; font-weight: 700; }
.rule-head em { font-style: normal; color: var(--text-secondary); }
.rule-line { color: var(--text-secondary); font-size: 12px; margin-top: 4px; }
.rule-item p { margin: 6px 0 0; line-height: 1.5; }
.error-card { border-color: var(--down-green); }
.error-title { color: var(--down-green); font-weight: 700; }
.error-detail { margin-top: 8px; color: var(--text-secondary); }
.error-detail span { display: inline-block; margin-right: 8px; }
.warning-card {
  background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.3);
  border-radius: 8px; padding: 10px 14px; margin-bottom: 12px;
  color: var(--warn-orange); font-size: 13px;
}
.warning-detail { margin-top: 6px; color: var(--text-muted); font-size: 11px; }
.breakdown-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
.trade-plan { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 10px; margin-bottom: 12px; color: var(--text-secondary); font-size: 12px; line-height: 1.8; }
@media (max-width: 1100px) { .backtest-layout { grid-template-columns: 1fr; } .metric-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
