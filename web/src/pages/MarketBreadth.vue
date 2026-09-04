<template>
  <main class="breadth-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">MARKET BREADTH · RESEARCH ONLY</p>
        <h1>市场宽度与策略信号</h1>
        <p>比较真实指数涨跌与全市场上涨、下跌家数，研究大面积下跌中的相对强势机会。</p>
      </div>
      <div class="research-badge">
        <span>研究展示</span>
        <strong>不参与策略6评分或过滤</strong>
      </div>
    </header>

    <section v-if="error" class="notice error">{{ error }}</section>
    <section v-if="loading" class="terminal-panel loading">正在重建真实历史涨跌家数…</section>

    <template v-else-if="summary">
      <section class="notice warning">{{ meta.warning || '当前股票池历史重建，存在幸存者偏差' }} 可靠图表区间自 {{ meta.reliableStartDate || meta.reliable_start_date || '--' }} 起，低覆盖日期保留但不参与图表和极端排行。当前股票池另有 {{ meta.untrackedStockCount ?? meta.untracked_stock_count ?? 0 }} 只没有可用于历史重建的本地日线。</section>

      <section class="summary-grid">
        <article class="metric terminal-panel"><span>数据日期</span><strong>{{ summary.date }}</strong><small>前一交易日 {{ summary.previousTradeDate }}</small></article>
        <article class="metric terminal-panel up"><span>上涨家数</span><strong>上涨 {{ summary.upCount }}</strong><small>{{ pct(summary.upRatio) }}</small></article>
        <article class="metric terminal-panel down"><span>下跌家数</span><strong>下跌 {{ summary.downCount }}</strong><small>{{ pct(summary.downRatio) }}</small></article>
        <article class="metric terminal-panel"><span>平盘 / 无法比较</span><strong>{{ summary.flatCount }} / {{ summary.unavailableCount }}</strong><small>覆盖率 {{ pct(summary.coverageRate) }}</small></article>
        <article class="metric terminal-panel state"><span>市场宽度状态</span><strong>{{ stateText(summary.breadthState) }}</strong><small>净上涨 {{ signed(summary.netAdvancers) }}</small></article>
      </section>

      <section class="terminal-panel index-panel">
        <div class="panel-title"><div><span>01</span><strong>四个真实宽基指数</strong></div><small>与涨跌家数平行对照，不冒充指数成分股宽度</small></div>
        <div class="index-grid">
          <article v-for="item in summaryIndexes" :key="item.symbol">
            <span>{{ item.name }}</span><strong>{{ price(item.close) }}</strong>
            <em :class="numberClass(item.dailyReturn)">{{ signedPct(item.dailyReturn) }}</em>
            <small>{{ item.source || '来源未记录' }}</small>
          </article>
        </div>
      </section>

      <section class="terminal-panel chart-panel">
        <div class="panel-title">
          <div><span>02</span><strong>历史下跌家数占比</strong></div>
          <div class="range-buttons">
            <button v-for="n in [120, 250, 500, 0]" :key="n" :class="{ active: range === n }" @click="range = n">{{ n || '全部' }}</button>
          </div>
        </div>
        <div class="chart-scale"><span>100%</span><span>80% 恐慌线</span><span>60% 弱势线</span><span>0%</span></div>
        <svg class="breadth-chart" viewBox="0 0 1000 260" preserveAspectRatio="none" role="img" aria-label="历史下跌家数占比">
          <line x1="0" y1="52" x2="1000" y2="52" class="panic-line" />
          <line x1="0" y1="104" x2="1000" y2="104" class="weak-line" />
          <polyline :points="breadthPoints" class="breadth-line" />
          <circle v-for="point in signalPoints" :key="point.key" :cx="point.x" :cy="point.y" r="4" class="signal-dot"><title>{{ point.title }}</title></circle>
        </svg>
        <div class="chart-footer"><span>{{ visibleRows[0]?.date || '--' }}</span><span>金点：当天存在已保存的策略6正式候选任务</span><span>{{ visibleRows.at(-1)?.date || '--' }}</span></div>
        <div class="index-chart-title">
          <strong>同日指数涨跌幅</strong>
          <span v-for="series in indexSeries" :key="series.symbol" :style="{ color: series.color }">{{ series.name }}</span>
        </div>
        <svg class="index-return-chart" viewBox="0 0 1000 220" preserveAspectRatio="none" role="img" aria-label="四个指数同日涨跌幅">
          <line x1="0" y1="110" x2="1000" y2="110" class="zero-line" />
          <polyline v-for="series in indexSeries" :key="series.symbol" :points="series.points" class="index-line" :style="{ stroke: series.color }" />
        </svg>
        <div class="chart-footer"><span>纵轴范围 -10% 至 +10%</span><span>极端涨跌超过范围时截断显示</span></div>
      </section>

      <section class="terminal-panel table-panel">
        <div class="panel-title"><div><span>03</span><strong>跌家数最多的交易日</strong></div><small>点击任务号可在策略6候选页核对真实候选</small></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>日期</th><th>上涨</th><th>下跌</th><th>下跌占比</th><th>市场状态</th><th>指数涨跌</th><th>策略6历史候选信号</th><th>数据覆盖</th></tr></thead>
            <tbody>
              <tr v-for="row in extremeRows" :key="row.date">
                <td>{{ row.date }}</td><td class="up-text">{{ row.upCount }}</td><td class="down-text">{{ row.downCount }}</td>
                <td>{{ pct(row.downRatio) }}</td><td>{{ stateText(row.breadthState) }}</td>
                <td>{{ indexReturns(row) }}</td>
                <td>
                  <template v-if="row.strategy6Signal">
                    <router-link :to="`/strategy6/results?task=${row.strategy6Signal.taskId}`">{{ row.strategy6Signal.taskId }}</router-link>
                    <small>正式候选 {{ row.strategy6Signal.total }} · 重点 {{ row.strategy6Signal.keyCount }} · 观察 {{ row.strategy6Signal.watchCount }}</small>
                  </template>
                  <span v-else class="muted">当日无已保存扫描任务</span>
                </td>
                <td>{{ pct(row.coverageRate) }}<small>缺失 {{ row.unavailableCount }}</small></td>
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
import { computed, onMounted, ref } from 'vue'
import { useApi } from '../composables/useApi.js'

const api = useApi()
const loading = ref(true)
const error = ref('')
const meta = ref({})
const summary = ref(null)
const rows = ref([])
const range = ref(250)

const pick = (obj, camel, snake, fallback = null) => obj?.[camel] ?? obj?.[snake] ?? fallback
function normalizeIndex(item = {}) {
  return { symbol: item.symbol, name: item.name, close: item.close, dailyReturn: pick(item, 'dailyReturn', 'daily_return'), source: item.source }
}
function normalizeSignal(item) {
  if (!item) return null
  return {
    taskId: pick(item, 'taskId', 'task_id', ''), total: item.total || 0,
    readyCount: pick(item, 'readyCount', 'ready_count', 0), keyCount: pick(item, 'keyCount', 'key_count', 0),
    watchCount: pick(item, 'watchCount', 'watch_count', 0), stocks: item.stocks || [],
  }
}
function normalizeRow(item = {}) {
  const indexes = {}
  Object.entries(item.indexes || {}).forEach(([key, value]) => { indexes[key] = normalizeIndex(value) })
  return {
    date: item.date, previousTradeDate: pick(item, 'previousTradeDate', 'previous_trade_date', ''),
    upCount: pick(item, 'upCount', 'up_count', 0), downCount: pick(item, 'downCount', 'down_count', 0),
    flatCount: pick(item, 'flatCount', 'flat_count', 0), validCount: pick(item, 'validCount', 'valid_count', 0),
    unavailableCount: pick(item, 'unavailableCount', 'unavailable_count', 0), coverageRate: pick(item, 'coverageRate', 'coverage_rate', 0),
    upRatio: pick(item, 'upRatio', 'up_ratio', 0), downRatio: pick(item, 'downRatio', 'down_ratio', 0),
    breadth: item.breadth || 0, breadthState: pick(item, 'breadthState', 'breadth_state', 'NORMAL'),
    dataQuality: pick(item, 'dataQuality', 'data_quality', 'RELIABLE'),
    netAdvancers: pick(item, 'netAdvancers', 'net_advancers', 0), indexes,
    strategy6Signal: normalizeSignal(pick(item, 'strategy6Signal', 'strategy6_signal')),
  }
}

const reliableRows = computed(() => rows.value.filter(item => item.dataQuality === 'RELIABLE'))
const visibleRows = computed(() => range.value ? reliableRows.value.slice(-range.value) : reliableRows.value)
const summaryIndexes = computed(() => Object.values(summary.value?.indexes || {}))
const extremeRows = computed(() => [...visibleRows.value].sort((a, b) => b.downRatio - a.downRatio).slice(0, 30))
const breadthPoints = computed(() => chartPoints(visibleRows.value).map(p => `${p.x},${p.y}`).join(' '))
const signalPoints = computed(() => chartPoints(visibleRows.value).filter(p => p.row.strategy6Signal).map(p => ({ ...p, key: p.row.date, title: `${p.row.date} · 策略6候选 ${p.row.strategy6Signal.total}` })))
const indexSeries = computed(() => [
  ['sh000001', '上证指数', '#72a5ff'], ['sz399001', '深证成指', '#d6a84a'],
  ['sz399006', '创业板指', '#f04444'], ['hs300', '沪深300', '#a879ff'],
].map(([symbol, name, color]) => ({ symbol, name, color, points: indexReturnPoints(visibleRows.value, symbol) })))

function chartPoints(items) {
  const divisor = Math.max(items.length - 1, 1)
  return items.map((row, index) => ({ row, x: index / divisor * 1000, y: 260 - Math.max(0, Math.min(1, row.downRatio)) * 260 }))
}
function indexReturnPoints(items, symbol) {
  const divisor = Math.max(items.length - 1, 1)
  return items.map((row, index) => {
    const value = Number(row.indexes?.[symbol]?.dailyReturn ?? 0)
    const clipped = Math.max(-0.10, Math.min(0.10, value))
    return `${index / divisor * 1000},${110 - clipped / 0.10 * 100}`
  }).join(' ')
}
function pct(value) { return value === null || value === undefined ? '--' : `${(Number(value) * 100).toFixed(1)}%` }
function signedPct(value) { return value === null || value === undefined ? '--' : `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%` }
function signed(value) { return Number(value) > 0 ? `+${value}` : String(value ?? '--') }
function price(value) { return value === null || value === undefined ? '--' : Number(value).toFixed(2) }
function numberClass(value) { return Number(value) > 0 ? 'up-text' : Number(value) < 0 ? 'down-text' : '' }
function stateText(value) { return ({ NORMAL: '正常', WEAK: '普遍偏弱', BROAD_DECLINE: '大面积下跌', PANIC_DECLINE: '恐慌下跌', EXTREME_DECLINE: '极端下跌' })[value] || value }
function indexReturns(row) { return Object.values(row.indexes || {}).map(item => `${item.name} ${signedPct(item.dailyReturn)}`).join(' · ') }

onMounted(async () => {
  try {
    const payload = await api.getMarketBreadthHistory({ limit: 1500 })
    meta.value = payload.meta || {}
    rows.value = (payload.rows || []).map(normalizeRow)
    summary.value = payload.summary ? normalizeRow(payload.summary) : rows.value.at(-1) || null
  } catch (exc) {
    error.value = `市场宽度加载失败：${exc.message || exc}`
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.breadth-page{max-width:1560px;margin:0 auto;padding:24px}.page-header{display:flex;justify-content:space-between;gap:24px;margin-bottom:18px}.eyebrow{color:var(--accent);font:11px var(--font-mono);letter-spacing:.16em}.page-header h1{margin:4px 0;font-size:26px}.page-header p{margin:0;color:var(--text-secondary)}.research-badge,.terminal-panel{background:var(--bg-panel);border:1px solid var(--border);box-shadow:var(--shadow-panel)}.research-badge{padding:13px 16px;min-width:260px}.research-badge span,.research-badge strong{display:block}.research-badge span{color:var(--gold);font:11px var(--font-mono)}.research-badge strong{margin-top:5px}.notice{padding:10px 14px;margin:12px 0;border:1px solid}.notice.warning{border-color:rgba(232,144,63,.45);background:var(--warn-orange-glow);color:#f0b16d}.notice.error{border-color:var(--danger);color:var(--danger)}.loading,.empty{padding:40px;text-align:center;color:var(--text-secondary)}.summary-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0}.metric{padding:14px;border-top:2px solid var(--border-light)}.metric.up{border-top-color:var(--up-red)}.metric.down{border-top-color:var(--down-green)}.metric.state{border-top-color:var(--gold)}.metric span,.metric small{display:block;color:var(--text-muted)}.metric strong{display:block;margin:6px 0;font:20px var(--font-mono)}.panel-title{display:flex;justify-content:space-between;align-items:center;padding:12px 15px;border-bottom:1px solid var(--border)}.panel-title>div:first-child{display:flex;gap:9px}.panel-title>div:first-child span{color:var(--accent);font-family:var(--font-mono)}.panel-title small{color:var(--text-muted)}.index-panel,.chart-panel,.table-panel{margin-top:12px}.index-grid{display:grid;grid-template-columns:repeat(4,1fr)}.index-grid article{padding:15px;border-right:1px solid var(--border)}.index-grid article:last-child{border:0}.index-grid span,.index-grid small{display:block;color:var(--text-muted)}.index-grid strong{font:19px var(--font-mono);margin:5px 12px 5px 0}.index-grid em{font-style:normal;font-family:var(--font-mono)}.up-text{color:var(--up-red)}.down-text{color:var(--down-green)}.range-buttons{display:flex;gap:4px}.range-buttons button{border:1px solid var(--border);background:var(--bg-card);color:var(--text-secondary);padding:4px 9px}.range-buttons button.active{border-color:var(--accent);color:#fff}.breadth-chart{display:block;width:100%;height:280px;background:linear-gradient(to bottom,rgba(240,68,68,.04),transparent 50%,rgba(32,173,114,.03))}.breadth-line{fill:none;stroke:var(--down-green);stroke-width:2;vector-effect:non-scaling-stroke}.panic-line,.weak-line{stroke:var(--warn-orange);stroke-width:1;stroke-dasharray:5 5;opacity:.6;vector-effect:non-scaling-stroke}.weak-line{stroke:var(--text-muted)}.signal-dot{fill:var(--gold);stroke:#fff;stroke-width:1;vector-effect:non-scaling-stroke}.chart-scale,.chart-footer{display:flex;justify-content:space-between;padding:7px 12px;color:var(--text-muted);font:11px var(--font-mono)}.table-wrap{overflow:auto;max-height:620px}table{width:100%;border-collapse:collapse;white-space:nowrap}th,td{padding:10px 12px;border-bottom:1px solid var(--border);text-align:left}th{position:sticky;top:0;background:var(--bg-card);color:var(--text-muted);font-size:11px}td small{display:block;color:var(--text-muted);margin-top:3px}.muted{color:var(--text-muted)}@media(max-width:1000px){.summary-grid{grid-template-columns:repeat(2,1fr)}.index-grid{grid-template-columns:repeat(2,1fr)}.page-header{flex-direction:column}.breadth-page{padding:14px}}
.index-chart-title{display:flex;align-items:center;gap:18px;padding:12px;border-top:1px solid var(--border)}
.index-chart-title span{font:11px var(--font-mono)}
.index-return-chart{display:block;width:100%;height:220px;background:var(--bg-card)}
.zero-line{stroke:var(--border-light);stroke-width:1;vector-effect:non-scaling-stroke}
.index-line{fill:none;stroke-width:1.3;opacity:.9;vector-effect:non-scaling-stroke}
</style>
