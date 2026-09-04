<template>
  <main class="breadth-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">MARKET BREADTH · RESEARCH ONLY</p>
        <h1>市场宽度与策略信号</h1>
        <p>先看赚钱效应，再判断指数与个股是否共振或背离。</p>
      </div>
      <div class="research-badge">
        <span>研究展示</span>
        <strong>不参与策略6评分或过滤</strong>
      </div>
    </header>

    <section v-if="error" class="notice error">{{ error }}</section>
    <section v-if="loading" class="terminal-panel loading">正在读取真实历史涨跌家数…</section>

    <template v-else-if="currentRow">
      <section class="conclusion terminal-panel" :class="currentRow.breadthLevel.className">
        <div>
          <span>当前结论</span>
          <h2>市场{{ currentRow.breadthLevel.label }} · {{ currentRow.breadthTrend.label }}</h2>
          <p>{{ marketConclusion }}</p>
        </div>
        <div class="relation-tag">
          <small>指数 × 个股</small>
          <strong>{{ marketRelation.label }}</strong>
          <span>{{ marketRelation.description }}</span>
        </div>
      </section>

      <section class="notice warning">
        {{ meta.warning || '当前股票池历史重建，存在幸存者偏差' }}
        仅可靠日期参与趋势、图表、分位和排行。
      </section>

      <section class="summary-grid">
        <article class="metric terminal-panel">
          <span>数据日期</span><strong>{{ currentRow.date }}</strong>
          <small>前一交易日 {{ currentRow.previousTradeDate || '--' }}</small>
        </article>
        <article class="metric terminal-panel breadth-state">
          <span>上涨占比</span><strong>{{ pct(currentRow.breadthRate) }}</strong>
          <small>{{ currentRow.breadthLevel.label }} · 上涨 {{ currentRow.upCount }} / 下跌 {{ currentRow.downCount }}</small>
        </article>
        <article class="metric terminal-panel trend-state">
          <span>MA5</span><strong>{{ pct(currentRow.breadthMA5) }}</strong>
          <small>{{ pct(recent5?.startBreadthMA5) }} → {{ pct(recent5?.endBreadthMA5) }} · {{ currentRow.breadthTrend.label }}</small>
        </article>
        <article class="metric terminal-panel">
          <span>{{ primaryIndexDefinition.name }}</span><strong :class="numberClass(primaryIndexData?.dailyReturn)">{{ signedPct(primaryIndexData?.dailyReturn) }}</strong>
          <small>收盘 {{ price(primaryIndexData?.close) }}</small>
        </article>
        <article class="metric terminal-panel relation-state">
          <span>市场状态</span><strong>{{ marketRelation.label }}</strong>
          <small>指数{{ marketRelation.indexState.label }} · 个股{{ marketRelation.stockState.label }}</small>
        </article>
      </section>

      <section class="terminal-panel index-panel">
        <div class="panel-title"><div><span>01</span><strong>四个真实宽基指数</strong></div><small>选择主指数后，结论和下方图表同步更新</small></div>
        <div class="index-grid">
          <button
            v-for="definition in indexDefinitions"
            :key="definition.symbol"
            type="button"
            :class="{ active: primaryIndex === definition.symbol }"
            @click="selectPrimaryIndex(definition.symbol)"
          >
            <span>{{ definition.name }}</span>
            <strong>{{ price(currentRow.indexes?.[definition.symbol]?.close) }}</strong>
            <em :class="numberClass(currentRow.indexes?.[definition.symbol]?.dailyReturn)">{{ signedPct(currentRow.indexes?.[definition.symbol]?.dailyReturn) }}</em>
          </button>
        </div>
      </section>

      <section class="insight-grid">
        <article class="terminal-panel insight-card">
          <div class="panel-title"><div><span>02</span><strong>最近5个交易日</strong></div></div>
          <dl>
            <div><dt>{{ primaryIndexDefinition.name }}累计</dt><dd :class="numberClass(recent5?.indexCumulativeReturn)">{{ signedPct(recent5?.indexCumulativeReturn) }}</dd></div>
            <div><dt>平均上涨占比</dt><dd>{{ pct(recent5?.averageBreadthRate) }}</dd></div>
            <div><dt>上涨占比</dt><dd>{{ pct(recent5?.startBreadthRate) }} → {{ pct(recent5?.endBreadthRate) }}</dd></div>
            <div><dt>MA5</dt><dd>{{ pct(recent5?.startBreadthMA5) }} → {{ pct(recent5?.endBreadthMA5) }}</dd></div>
          </dl>
          <p>{{ marketConclusion }}</p>
        </article>
        <article class="terminal-panel insight-card">
          <div class="panel-title"><div><span>03</span><strong>最近20日市场宽度</strong></div></div>
          <div class="level-stats">
            <span>极强 <b>{{ levelCounts20.EXTREME_STRONG }}</b>天</span>
            <span>偏强 <b>{{ levelCounts20.STRONG }}</b>天</span>
            <span>均衡 <b>{{ levelCounts20.NEUTRAL }}</b>天</span>
            <span>偏弱 <b>{{ levelCounts20.WEAK }}</b>天</span>
            <span>极弱 <b>{{ levelCounts20.EXTREME_WEAK }}</b>天</span>
          </div>
          <p v-if="breadthPercentile !== null">当前上涨占比处于过去120个可靠交易日的 <strong>{{ pct(breadthPercentile) }}</strong> 分位，弱于其中 {{ pct(1 - breadthPercentile) }}。</p>
          <p v-else>可靠历史不足，暂不计算市场宽度分位。</p>
        </article>
      </section>

      <section class="terminal-panel chart-panel">
        <div class="panel-title chart-toolbar">
          <div><span>04</span><strong>市场宽度与主指数联动</strong></div>
          <div class="controls">
            <div class="range-buttons">
              <button v-for="n in [120, 250, 500, 0]" :key="n" :class="{ active: range === n }" @click="range = n">{{ n || '全部' }}</button>
            </div>
            <label><input v-model="showStrategySignals" type="checkbox"> 显示策略6信号</label>
          </div>
        </div>
        <div ref="breadthChartElement" data-test="breadth-chart" class="echart breadth-echart" aria-label="历史市场宽度"></div>
        <div class="series-controls">
          <strong>指数叠加</strong>
          <label v-for="definition in indexDefinitions" :key="definition.symbol">
            <input
              type="checkbox"
              :checked="visibleIndexSymbols.includes(definition.symbol)"
              :disabled="primaryIndex === definition.symbol"
              @change="toggleIndex(definition.symbol)"
            > {{ definition.name }}
          </label>
        </div>
        <div ref="indexChartElement" data-test="index-chart" class="echart index-echart" aria-label="主指数同日涨跌幅"></div>
        <div class="chart-footnote"><span>红涨绿跌；金色只表示当天存在已保存的策略6正式候选任务。</span><span>拖动底部时间轴可同步缩放两张图。</span></div>
      </section>

      <section class="terminal-panel table-panel">
        <div class="panel-title"><div><span>05</span><strong>上涨占比最低的交易日</strong></div><small>仅统计可靠日期</small></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>日期</th><th>上涨 / 下跌</th><th>上涨占比</th><th>MA5</th><th>宽度状态</th><th>{{ primaryIndexDefinition.name }}</th><th>指数 × 个股</th><th>策略6信号</th><th>覆盖率</th></tr></thead>
            <tbody>
              <tr v-for="row in weakestRows" :key="row.date">
                <td>{{ row.date }}</td>
                <td><span class="up-text">{{ row.upCount }}</span> / <span class="down-text">{{ row.downCount }}</span></td>
                <td>{{ pct(row.breadthRate) }}</td><td>{{ pct(row.breadthMA5) }}</td><td>{{ row.breadthLevel.label }}</td>
                <td :class="numberClass(row.indexes?.[primaryIndex]?.dailyReturn)">{{ signedPct(row.indexes?.[primaryIndex]?.dailyReturn) }}</td>
                <td>{{ relationFor(row).label }}</td>
                <td>
                  <template v-if="row.strategy6Signal">
                    <router-link :to="`/strategy6/results?task=${row.strategy6Signal.taskId}`">{{ row.strategy6Signal.taskId }}</router-link>
                    <small>正式候选 {{ row.strategy6Signal.total }} · 重点 {{ row.strategy6Signal.keyCount }} · 观察 {{ row.strategy6Signal.watchCount }}</small>
                  </template>
                  <span v-else class="muted">无</span>
                </td>
                <td>{{ pct(row.coverageRate) }}<small>无法比较 {{ row.unavailableCount }}</small></td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <section v-else-if="!loading" class="terminal-panel empty">本地真实指数或个股历史不足，无法生成市场宽度。</section>
  </main>
</template>

<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useApi } from '../composables/useApi.js'
import {
  buildMarketConclusion,
  calcBreadthPercentile,
  countBreadthLevels,
  enrichBreadthRows,
  getMarketRelation,
  summarizeRecentBreadth,
} from '../utils/marketBreadth.js'

const api = useApi()
const loading = ref(true)
const error = ref('')
const meta = ref({})
const rows = ref([])
const range = ref(250)
const primaryIndex = ref('sh000001')
const visibleIndexSymbols = ref(['sh000001'])
const showStrategySignals = ref(true)
const breadthChartElement = ref(null)
const indexChartElement = ref(null)
let breadthChart = null
let indexChart = null
const chartGroup = 'market-breadth-linked'

const indexDefinitions = [
  { symbol: 'sh000001', name: '上证指数', color: '#e75b5b' },
  { symbol: 'sz399001', name: '深证成指', color: '#65a4ff' },
  { symbol: 'sz399006', name: '创业板指', color: '#b785f4' },
  { symbol: 'hs300', name: '沪深300', color: '#d6a84a' },
]

const pick = (obj, camel, snake, fallback = null) => obj?.[camel] ?? obj?.[snake] ?? fallback
function normalizeIndex(item = {}) {
  return { name: item.name, close: Number(item.close), dailyReturn: pick(item, 'dailyReturn', 'daily_return') }
}
function normalizeSignal(item) {
  if (!item) return null
  return {
    taskId: pick(item, 'taskId', 'task_id', ''), total: item.total || 0,
    keyCount: pick(item, 'keyCount', 'key_count', 0), watchCount: pick(item, 'watchCount', 'watch_count', 0),
    stocks: item.stocks || [],
  }
}
function normalizeRow(item = {}) {
  const indexes = {}
  Object.entries(item.indexes || {}).forEach(([key, value]) => { indexes[key] = normalizeIndex(value) })
  return {
    date: item.date,
    previousTradeDate: pick(item, 'previousTradeDate', 'previous_trade_date', ''),
    upCount: Number(pick(item, 'upCount', 'up_count', 0)),
    downCount: Number(pick(item, 'downCount', 'down_count', 0)),
    flatCount: Number(pick(item, 'flatCount', 'flat_count', 0)),
    unavailableCount: Number(pick(item, 'unavailableCount', 'unavailable_count', 0)),
    coverageRate: Number(pick(item, 'coverageRate', 'coverage_rate', item.coverage ?? 0)),
    dataQuality: pick(item, 'dataQuality', 'data_quality', 'RELIABLE'),
    indexes,
    strategy6Signal: normalizeSignal(pick(item, 'strategy6Signal', 'strategy6_signal')),
  }
}

const reliableRows = computed(() => rows.value.filter(item => item.dataQuality === 'RELIABLE'))
const enrichedRows = computed(() => enrichBreadthRows(reliableRows.value))
const visibleRows = computed(() => range.value ? enrichedRows.value.slice(-range.value) : enrichedRows.value)
const currentRow = computed(() => enrichedRows.value.at(-1) || null)
const primaryIndexDefinition = computed(() => indexDefinitions.find(item => item.symbol === primaryIndex.value) || indexDefinitions[0])
const primaryIndexData = computed(() => currentRow.value?.indexes?.[primaryIndex.value] || null)
const marketRelation = computed(() => getMarketRelation(primaryIndexData.value?.dailyReturn, currentRow.value?.breadthRate))
const marketConclusion = computed(() => buildMarketConclusion(currentRow.value, marketRelation.value))
const recent5 = computed(() => summarizeRecentBreadth(enrichedRows.value, primaryIndex.value, 5))
const levelCounts20 = computed(() => countBreadthLevels(enrichedRows.value, 20))
const breadthPercentile = computed(() => calcBreadthPercentile(enrichedRows.value.map(row => row.breadthRate), currentRow.value?.breadthRate, 120))
const weakestRows = computed(() => [...visibleRows.value].sort((a, b) => (a.breadthRate ?? 1) - (b.breadthRate ?? 1)).slice(0, 30))

function relationFor(row) { return getMarketRelation(row.indexes?.[primaryIndex.value]?.dailyReturn, row.breadthRate) }
function pct(value) { return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '--' }
function signedPct(value) { return typeof value === 'number' && Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${(value * 100).toFixed(2)}%` : '--' }
function price(value) { return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '--' }
function numberClass(value) { return Number(value) > 0 ? 'up-text' : Number(value) < 0 ? 'down-text' : '' }
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
}

function selectPrimaryIndex(symbol) {
  primaryIndex.value = symbol
  if (!visibleIndexSymbols.value.includes(symbol)) visibleIndexSymbols.value = [...visibleIndexSymbols.value, symbol]
}
function toggleIndex(symbol) {
  if (symbol === primaryIndex.value) return
  visibleIndexSymbols.value = visibleIndexSymbols.value.includes(symbol)
    ? visibleIndexSymbols.value.filter(item => item !== symbol)
    : [...visibleIndexSymbols.value, symbol]
}

function tooltipHtml(dataIndex) {
  const row = visibleRows.value[dataIndex]
  if (!row) return ''
  const relation = relationFor(row)
  const index = row.indexes?.[primaryIndex.value]
  const signal = row.strategy6Signal
  return `<div style="min-width:250px;line-height:1.7">
    <strong>${escapeHtml(row.date)} · ${escapeHtml(relation.label)}</strong><br>
    <span style="color:#9ba8bb">市场宽度</span><br>
    上涨占比 ${pct(row.breadthRate)} · MA5 ${pct(row.breadthMA5)}<br>
    上涨 ${row.upCount} · 下跌 ${row.downCount} · 平盘 ${row.flatCount}<br>
    状态 ${escapeHtml(row.breadthLevel.label)} · ${escapeHtml(row.breadthTrend.label)}<br>
    <span style="color:#9ba8bb">${escapeHtml(primaryIndexDefinition.value.name)}</span><br>
    涨跌 ${signedPct(index?.dailyReturn)} · 收盘 ${price(index?.close)}<br>
    ${signal ? `<span style="color:#d6a84a">策略6正式候选 ${signal.total} · ${escapeHtml(signal.taskId)}</span>` : '策略6信号：无'}
  </div>`
}

function commonTooltip() {
  return {
    trigger: 'axis',
    axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
    backgroundColor: 'rgba(9, 16, 27, .96)', borderColor: '#34445c', textStyle: { color: '#e6edf7' },
    formatter(params) {
      const item = Array.isArray(params) ? params[0] : params
      return tooltipHtml(item?.dataIndex)
    },
  }
}

function renderCharts() {
  if (!breadthChartElement.value || !indexChartElement.value || !visibleRows.value.length) return
  if (!breadthChart) {
    breadthChart = echarts.init(breadthChartElement.value)
    indexChart = echarts.init(indexChartElement.value)
    breadthChart.group = chartGroup
    indexChart.group = chartGroup
    echarts.connect(chartGroup)
  }
  const dates = visibleRows.value.map(row => row.date)
  const signalData = showStrategySignals.value
    ? visibleRows.value.map((row, index) => row.strategy6Signal ? [index, (row.breadthRate || 0) * 100, row.strategy6Signal.total] : null).filter(Boolean)
    : []
  breadthChart.setOption({
    animation: false,
    grid: { left: 58, right: 28, top: 32, bottom: 35 },
    tooltip: commonTooltip(),
    legend: { top: 4, textStyle: { color: '#9ba8bb' }, data: ['每日上涨占比', '上涨占比 MA5', '策略6信号'] },
    xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { color: '#74839a' }, axisLine: { lineStyle: { color: '#2b394e' } }, axisPointer: { show: true } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#74839a', formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(100,120,150,.13)' } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }],
    series: [
      {
        name: '每日上涨占比', type: 'line', showSymbol: false, data: visibleRows.value.map(row => row.breadthRate === null ? null : row.breadthRate * 100),
        lineStyle: { width: 1.5, color: '#65a4ff' }, itemStyle: { color: '#65a4ff' },
        markArea: { silent: true, data: [
          [{ yAxis: 0, itemStyle: { color: 'rgba(32,173,114,.06)' } }, { yAxis: 30 }],
          [{ yAxis: 30, itemStyle: { color: 'rgba(32,173,114,.025)' } }, { yAxis: 45 }],
          [{ yAxis: 45, itemStyle: { color: 'rgba(110,130,155,.025)' } }, { yAxis: 55 }],
          [{ yAxis: 55, itemStyle: { color: 'rgba(240,112,68,.025)' } }, { yAxis: 70 }],
          [{ yAxis: 70, itemStyle: { color: 'rgba(240,68,68,.055)' } }, { yAxis: 100 }],
        ] },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: '#73839a', opacity: .55 }, data: [{ yAxis: 50, name: '平衡线' }] },
      },
      { name: '上涨占比 MA5', type: 'line', showSymbol: false, data: visibleRows.value.map(row => row.breadthMA5 === null ? null : row.breadthMA5 * 100), lineStyle: { width: 2, type: 'dashed', color: '#d6a84a' }, itemStyle: { color: '#d6a84a' } },
      { name: '策略6信号', type: 'scatter', data: signalData, symbolSize: value => Math.min(10, 4 + Number(value?.[2] || 0)), itemStyle: { color: '#d6a84a' } },
    ],
  }, true)

  const selected = indexDefinitions.filter(item => visibleIndexSymbols.value.includes(item.symbol))
  indexChart.setOption({
    animation: false,
    grid: { left: 58, right: 28, top: 28, bottom: 62 },
    tooltip: commonTooltip(),
    legend: { top: 3, textStyle: { color: '#9ba8bb' }, data: selected.map(item => item.name) },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#74839a' }, axisLine: { lineStyle: { color: '#2b394e' } }, axisPointer: { show: true } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#74839a', formatter: value => `${value.toFixed(1)}%` }, splitLine: { lineStyle: { color: 'rgba(100,120,150,.13)' } } },
    dataZoom: [{ type: 'inside', xAxisIndex: 0 }, { type: 'slider', xAxisIndex: 0, height: 18, bottom: 16, borderColor: '#2b394e', fillerColor: 'rgba(101,164,255,.18)', textStyle: { color: '#74839a' } }],
    series: selected.map(definition => ({
      name: definition.name,
      type: definition.symbol === primaryIndex.value ? 'bar' : 'line',
      showSymbol: false,
      data: visibleRows.value.map(row => {
        const value = row.indexes?.[definition.symbol]?.dailyReturn
        return typeof value === 'number' ? Number((value * 100).toFixed(4)) : null
      }),
      barMaxWidth: 7,
      lineStyle: { width: definition.symbol === primaryIndex.value ? 0 : 1.3, color: definition.color },
      itemStyle: definition.symbol === primaryIndex.value
        ? { color: params => Number(params.value) >= 0 ? '#e75b5b' : '#20ad72' }
        : { color: definition.color },
    })),
  }, true)
}

function resizeCharts() {
  breadthChart?.resize()
  indexChart?.resize()
}

watch([visibleRows, primaryIndex, visibleIndexSymbols, showStrategySignals], async () => {
  await nextTick()
  renderCharts()
}, { deep: true })

onMounted(async () => {
  window.addEventListener('resize', resizeCharts)
  try {
    const payload = await api.getMarketBreadthHistory({ limit: 1500 })
    meta.value = payload.meta || {}
    rows.value = (payload.rows || []).map(normalizeRow)
    await nextTick()
    renderCharts()
  } catch (exc) {
    error.value = `市场宽度加载失败：${exc.message || exc}`
  } finally {
    loading.value = false
    await nextTick()
    renderCharts()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeCharts)
  echarts.disconnect(chartGroup)
  breadthChart?.dispose()
  indexChart?.dispose()
  breadthChart = null
  indexChart = null
})
</script>

<style scoped>
.breadth-page{max-width:1560px;margin:0 auto;padding:24px}.page-header{display:flex;justify-content:space-between;gap:24px;margin-bottom:18px}.eyebrow{color:var(--accent);font:11px var(--font-mono);letter-spacing:.16em}.page-header h1{margin:4px 0;font-size:26px}.page-header p{margin:0;color:var(--text-secondary)}.research-badge,.terminal-panel{background:var(--bg-panel);border:1px solid var(--border);box-shadow:var(--shadow-panel)}.research-badge{padding:13px 16px;min-width:260px}.research-badge span,.research-badge strong{display:block}.research-badge span{color:var(--gold);font:11px var(--font-mono)}.research-badge strong{margin-top:5px}.notice{padding:10px 14px;margin:12px 0;border:1px solid}.notice.warning{border-color:rgba(232,144,63,.45);background:var(--warn-orange-glow);color:#f0b16d}.notice.error{border-color:var(--danger);color:var(--danger)}.loading,.empty{padding:40px;text-align:center;color:var(--text-secondary)}
.conclusion{display:flex;justify-content:space-between;align-items:center;gap:28px;padding:18px 20px;border-left:4px solid var(--border-light)}.conclusion.extreme-strong,.conclusion.strong{border-left-color:var(--up-red)}.conclusion.weak,.conclusion.extreme-weak{border-left-color:var(--down-green)}.conclusion span,.conclusion small{color:var(--text-muted)}.conclusion h2{margin:5px 0;font-size:24px}.conclusion p{margin:0;color:var(--text-secondary)}.relation-tag{min-width:250px;padding:11px 14px;background:var(--bg-card);border:1px solid var(--border)}.relation-tag>*{display:block}.relation-tag strong{margin:5px 0;font-size:18px}
.summary-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}.metric{padding:14px;border-top:2px solid var(--border-light)}.metric.breadth-state{border-top-color:var(--accent)}.metric.trend-state{border-top-color:var(--gold)}.metric.relation-state{border-top-color:var(--warn-orange)}.metric span,.metric small{display:block;color:var(--text-muted)}.metric strong{display:block;margin:6px 0;font:20px var(--font-mono)}.panel-title{display:flex;justify-content:space-between;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border)}.panel-title>div:first-child{display:flex;gap:9px}.panel-title>div:first-child span{color:var(--accent);font-family:var(--font-mono)}.panel-title small{color:var(--text-muted)}
.index-panel,.chart-panel,.table-panel{margin-top:12px}.index-grid{display:grid;grid-template-columns:repeat(4,1fr)}.index-grid button{padding:15px;border:0;border-right:1px solid var(--border);background:transparent;color:inherit;text-align:left;cursor:pointer}.index-grid button:last-child{border-right:0}.index-grid button.active{background:rgba(101,164,255,.07);box-shadow:inset 0 -2px var(--accent)}.index-grid span{display:block;color:var(--text-muted)}.index-grid strong{font:19px var(--font-mono);margin:5px 12px 5px 0}.index-grid em{font-style:normal;font-family:var(--font-mono)}
.insight-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.insight-card dl{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:0;padding:8px 15px}.insight-card dl div{display:flex;justify-content:space-between;padding:9px;border-bottom:1px solid var(--border)}.insight-card dt{color:var(--text-muted)}.insight-card dd{margin:0;font-family:var(--font-mono)}.insight-card>p{margin:4px 15px 15px;color:var(--text-secondary)}.level-stats{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;padding:15px}.level-stats span{padding:10px;background:var(--bg-card);color:var(--text-muted);text-align:center}.level-stats b{display:block;margin:5px;color:var(--text-primary);font:20px var(--font-mono)}
.chart-toolbar{gap:14px;flex-wrap:wrap}.controls,.range-buttons,.series-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.controls label,.series-controls label{color:var(--text-secondary);font-size:12px}.range-buttons button{border:1px solid var(--border);background:var(--bg-card);color:var(--text-secondary);padding:5px 10px;cursor:pointer}.range-buttons button.active{border-color:var(--accent);color:#fff}.echart{width:100%}.breadth-echart{height:310px}.index-echart{height:260px}.series-controls{padding:9px 15px;border-top:1px solid var(--border);border-bottom:1px solid var(--border)}.series-controls strong{margin-right:8px}.chart-footnote{display:flex;justify-content:space-between;padding:8px 14px;color:var(--text-muted);font-size:11px}
.table-wrap{overflow:auto;max-height:620px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left}th{position:sticky;top:0;background:var(--bg-card);color:var(--text-muted);font-size:11px}td small{display:block;color:var(--text-muted);margin-top:3px}.up-text{color:var(--up-red)}.down-text{color:var(--down-green)}.muted{color:var(--text-muted)}
@media(max-width:1000px){.summary-grid{grid-template-columns:repeat(2,1fr)}.index-grid{grid-template-columns:repeat(2,1fr)}.insight-grid{grid-template-columns:1fr}.page-header,.conclusion{flex-direction:column;align-items:stretch}.breadth-page{padding:14px}.chart-footnote{display:block}.chart-footnote span{display:block;margin-top:4px}}
</style>
