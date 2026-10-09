<template>
  <section class="trend-breadth" data-test="trend-breadth-panel">
    <header><div><strong>强势趋势收缩宽度</strong><small>每日真实历史初筛 · 适合本策略的机会环境</small></div><button type="button" :disabled="loading" @click="loadHistory">重新加载</button></header>
    <p v-if="loading" class="notice">正在重建或读取历史初筛，首次计算可能需要一些时间；其他市场宽度数据可正常浏览。</p>
    <p v-if="error" class="notice error">{{ error }}</p>
    <template v-if="rows.length">
      <p class="notice">{{ meta.warning }}。本板块使用固定初筛规则，交易提示仅作参考。</p>
      <p class="footnote">真实历史范围 {{ meta.available_start || '--' }} 至 {{ meta.available_end || '--' }}，选择日期或点击图表查看当日初筛。</p>
      <p class="footnote">当前股票池 {{ meta.pool_count ?? '--' }}只，有本地历史 {{ meta.stocks_with_history_count ?? '--' }}只。覆盖率分母仅为该日已具备250根历史资格的股票，未覆盖或尚不足250根的股票不计入资格分母。</p>
      <div class="toolbar">
        <label>历史日期 <select v-model="selectedDate" data-test="trend-date"><option v-for="row in [...rows].reverse()" :key="row.date" :value="row.date">{{ row.date }}{{ row.screen_count === null ? ' · 数据不足' : '' }}</option></select></label>
        <div><button v-for="size in [120, 250, 500, 0]" :key="size" type="button" :class="{ active: range === size }" @click="range = size">{{ size || '全部' }}</button></div>
      </div>
      <div v-if="current" class="metrics">
        <div><span>当日初筛</span><strong>{{ count(current.screen_count) }}只</strong><small>占比 {{ pct(current.screen_ratio) }}</small></div>
        <div><span>长期强势对照</span><strong>{{ count(current.strong_count) }}只</strong><small>占比 {{ pct(current.strong_ratio) }} · 不要求收缩</small><small>120日分位 {{ pct(current.strong_percentile120) }}</small></div>
        <div><span>较前日增减</span><strong :class="current.screen_change > 0 ? 'up' : current.screen_change < 0 ? 'down' : ''">{{ change(current.screen_change) }}</strong><small>成功评估 {{ current.evaluated_count }} / 有资格 {{ current.eligible_count }}</small></div>
        <div><span>初筛占比 MA5 / MA20</span><strong>{{ pct(current.screen_ma5) }} / {{ pct(current.screen_ma20) }}</strong><small>120日分位 {{ pct(current.screen_percentile120) }}</small></div>
        <div><span>覆盖率 {{ pct(current.coverage_rate) }}</span><strong>{{ current.environment }}</strong><small>{{ current.data_quality === 'RELIABLE' ? '可靠数据' : '覆盖或样本不足，暂停环境判断' }}</small></div>
      </div>
      <div ref="chartElement" class="chart" data-test="trend-breadth-chart" aria-label="上图历史股票数量，下图初筛占比及均线"></div>
      <p class="footnote">上图看数量，下图单独比较初筛占比、MA5与MA20。占比纵轴随可见数据自适应，不固定从0开始；两图同步缩放，点击任一图选择历史日期。低覆盖日期的占比留空，数量仍可核查。</p>
      <div class="history-table"><table><thead><tr><th>日期</th><th>初筛数</th><th>长期强势数</th><th>初筛占比</th><th>覆盖率</th><th>机会环境</th></tr></thead><tbody>
        <tr v-for="row in [...visibleRows].reverse().slice((historyPage-1)*20, historyPage*20)" :key="row.date" :class="{ selected: row.date === selectedDate }" @click="selectedDate = row.date"><td>{{ row.date }}</td><td>{{ count(row.screen_count) }}</td><td>{{ count(row.strong_count) }}</td><td>{{ pct(row.screen_ratio) }}</td><td>{{ pct(row.coverage_rate) }}</td><td>{{ row.environment }}</td></tr>
      </tbody></table></div>
      <div class="toolbar"><button type="button" :disabled="historyPage === 1" @click="historyPage--">上一页</button><span>历史 {{ historyPage }} / {{ Math.max(1, Math.ceil(visibleRows.length/20)) }} 页</span><button type="button" :disabled="historyPage*20 >= visibleRows.length" @click="historyPage++">下一页</button></div>
      <h3>{{ selectedDate }} 初筛名单 <small>{{ selection?.stocks?.length ?? '--' }}只</small></h3>
      <p v-if="stockLoading">正在读取当日名单…</p><p v-else-if="stockError" class="error">{{ stockError }}</p>
      <p v-else-if="selection && !selection.available">当日数据不足，无法确认名单；不能按零机会解释。</p>
      <p v-else-if="selection?.stocks?.length === 0">当日成功评估，初筛无匹配股票。</p>
      <div v-else class="stocks"><span v-for="stock in selection?.stocks || []" :key="stock.code"><b>{{ stock.code }}</b> {{ stock.name }}</span></div>
      <p class="footnote">占比=匹配数÷成功评估数。环境提示使用各自120日占比分位：30%以下偏低、70%以上充足；长期强势高但收缩少时提示注意追涨。该展示约定尚未进行收益校准。</p>
    </template>
    <p v-else-if="!loading && !error">本地指数或个股历史不足，暂无法展示强势收缩宽度。</p>
  </section>
</template>

<script setup>
import * as echarts from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const api = useApi()
const rows = shallowRef([])
const meta = ref({})
const loading = ref(false), error = ref(''), selectedDate = ref(''), range = ref(250), historyPage = ref(1)
const selection = shallowRef(null), stockLoading = ref(false), stockError = ref(''), chartElement = ref(null)
let chart, alive = true, request = 0
const visibleRows = computed(() => range.value ? rows.value.slice(-range.value) : rows.value)
const current = computed(() => rows.value.find(row => row.date === selectedDate.value))
const count = value => typeof value === 'number' ? String(value) : '--'
const pct = value => typeof value === 'number' ? `${(value*100).toFixed(1)}%` : '--'
const change = value => typeof value === 'number' ? `${value > 0 ? '+' : ''}${value}只` : '--'

async function loadHistory() {
  loading.value = true
  error.value = ''
  try {
    const payload = await api.getTrendSqueezeBreadthHistory({ limit: 2000 })
    if (!alive) return
    rows.value = payload.rows || []
    meta.value = payload.meta || {}
    const day = rows.value.at(-1)?.date || ''
    historyPage.value = 1
    // Reloading the same selected day must also reload its corrected list.
    if (selectedDate.value === day) await loadStocks(day)
    else selectedDate.value = day
  } catch (exc) {
    if (alive) error.value = exc.message || String(exc)
  } finally {
    if (alive) loading.value = false
    await nextTick()
    if (alive) renderChart()
  }
}

async function loadStocks(day) {
  const id = ++request
  selection.value = null
  stockError.value = ''
  if (!day) { stockLoading.value = false; return }
  stockLoading.value = true
  try {
    const payload = await api.getTrendSqueezeBreadthHistory({ stock_date: day, end_date: day, limit: 1 })
    if (alive && id === request && selectedDate.value === day) selection.value = payload.selection
  } catch (exc) {
    if (alive && id === request) stockError.value = exc.message || String(exc)
  } finally {
    if (alive && id === request) stockLoading.value = false
  }
}

function renderChart() {
  if (!chartElement.value || !visibleRows.value.length) return
  if (!chart) {
    chart = echarts.init(chartElement.value)
    chart.getZr().on('click', event => {
      const point = [event.offsetX, event.offsetY]
      const gridIndex = [0, 1].find(index => chart.containPixel({ gridIndex: index }, point))
      if (gridIndex === undefined) return
      const [index] = chart.convertFromPixel({ gridIndex }, point)
      const row = visibleRows.value[Math.round(index)]
      if (row) selectedDate.value = row.date
    })
  }
  const series = [
    ['初筛数量', 'screen_count', 0, '#d6a84a'], ['长期强势数量', 'strong_count', 0, '#e75b5b'],
    ['初筛占比', 'screen_ratio', 1, '#65a4ff'], ['占比MA5', 'screen_ma5', 1, '#b785f4'], ['占比MA20', 'screen_ma20', 1, '#20ad72'],
  ]
  const valueFor = (row, field, axis) => typeof row[field] === 'number' && (!axis || row.data_quality === 'RELIABLE') ? row[field]*(axis ? 100 : 1) : null
  const axisPadding = ({ min, max }) => Math.max((max-min)*.15, .2)
  const dates = visibleRows.value.map(r => r.date)
  chart.setOption({ animation: false,
    tooltip: { trigger: 'axis', formatter(params) {
      const row = visibleRows.value[params?.[0]?.dataIndex]
      if (!row) return ''
      const day = String(row.date).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char])
      return [day, ...series.map(([name, field, axis, color]) => {
        const value = valueFor(row, field, axis)
        return `<span style="color:${color}">${name}</span>：${value === null ? '--' : axis ? `${value.toFixed(2)}%` : `${value}只`}`
      })].join('<br>')
    } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    legend: { type: 'scroll', textStyle: { color: '#9ba8bb' }, data: ['初筛数量', '长期强势数量', '初筛占比', '占比MA5', '占比MA20'] },
    title: [{ text: '初筛与长期强势 · 数量', left: 60, top: 38, textStyle: { color: '#9ba8bb', fontSize: 13 } },
      { text: '初筛占比 · 独立比例尺', left: 60, top: '47%', textStyle: { color: '#9ba8bb', fontSize: 13 } }],
    grid: [{ left: 60, right: 28, top: 72, height: '29%' }, { left: 60, right: 28, top: '54%', bottom: 58 }],
    xAxis: [0, 1].map(gridIndex => ({ type: 'category', gridIndex, data: dates, axisLabel: { color: '#74839a', show: gridIndex === 1 } })),
    yAxis: [{ type: 'value', gridIndex: 0, min: 0, name: '只', axisLabel: { color: '#74839a' } },
      { type: 'value', gridIndex: 1, scale: true, name: '%',
        min: value => Number.isFinite(value.min) ? Math.max(0, value.min-axisPadding(value)) : 0,
        max: value => Number.isFinite(value.max) ? Math.min(100, value.max+axisPadding(value)) : 1,
        axisLabel: { color: '#74839a', formatter: value => `${value.toFixed(2)}%` } }],
    dataZoom: [{ type: 'inside', xAxisIndex: [0, 1] }, { type: 'slider', xAxisIndex: [0, 1], height: 18, bottom: 8 }],
    series: series.map(([name, field, axis, color]) => ({ name, type: 'line', showSymbol: false, xAxisIndex: axis, yAxisIndex: axis,
      connectNulls: false, data: visibleRows.value.map(r => valueFor(r, field, axis)),
      lineStyle: { color, width: 1.5 }, itemStyle: { color } })),
  }, true)
}
const resize = () => chart?.resize()
watch(selectedDate, day => loadStocks(day))
watch(visibleRows, async () => { historyPage.value = 1; await nextTick(); if (alive) renderChart() })
onMounted(() => { window.addEventListener('resize', resize); loadHistory() })
onBeforeUnmount(() => { alive = false; request++; window.removeEventListener('resize', resize); chart?.dispose() })
</script>

<style scoped>
.trend-breadth{margin:16px 0;padding:16px;background:var(--bg-panel);border:1px solid var(--border)}header,.toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}header strong{font-size:18px}small{display:block;color:var(--text-muted);margin-top:4px}button,select{padding:5px 9px;background:var(--bg-card);border:1px solid var(--border);color:var(--text-secondary);cursor:pointer}button:disabled{opacity:.4;cursor:default}button.active{border-color:var(--accent)}.notice,.footnote{color:var(--text-muted);font-size:12px;line-height:1.7}.error{color:var(--danger)}.toolbar{margin:12px 0}.toolbar button{margin-right:5px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.metrics div{background:var(--bg-card);padding:12px}.metrics span{color:var(--text-muted);font-size:12px}.metrics strong{display:block;margin-top:5px;font-size:17px}.chart{height:640px}.history-table{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:8px 10px;border-bottom:1px solid var(--border);text-align:left}th{color:var(--text-muted)}tbody tr{cursor:pointer}tr.selected{background:rgba(101,164,255,.1)}.stocks{display:flex;gap:8px;flex-wrap:wrap;max-height:320px;overflow:auto}.stocks span{padding:7px 10px;background:var(--bg-card)}.up{color:var(--up-red)}.down{color:var(--down-green)}@media(max-width:1000px){.metrics{grid-template-columns:repeat(2,1fr)}}
</style>
