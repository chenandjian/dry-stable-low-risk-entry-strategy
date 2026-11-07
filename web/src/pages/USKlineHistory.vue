<template>
  <section class="us-history">
    <h1>美股 K 线数据</h1>
    <p>只查询本地已入库的日线，不请求 TickFlow，也不触发扫描。</p>
    <form data-test="us-kline-query" class="query" @submit.prevent="submit">
      <label>股票代码<input v-model.trim="form.code" data-test="us-kline-code" placeholder="AAPL / BRK.B" required></label>
      <label>起始日期<input v-model="form.start_date" type="date"></label>
      <label>结束日期<input v-model="form.end_date" type="date"></label>
      <button :disabled="loading">{{ loading ? '查询中…' : '查询本地日线' }}</button>
    </form>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div v-if="result" data-test="us-kline-results">
      <h2>{{ result.symbol }}</h2>
      <p v-if="!result.summary.row_count">本地没有该标的的日线。请先在「美股研究」页获取数据。</p>
      <template v-else>
        <p>本地 {{ result.summary.row_count }} 根 · {{ result.summary.first_kline_date }} 至 {{ result.summary.latest_kline_date }}
          · 目标完整交易日 {{ result.summary.target_trade_date }}</p>
        <p>{{ status }} · 来源 {{ result.metadata.source || '未知' }} · forward 前复权 · 最近获取 {{ fetchTime }}</p>
        <p>成交量保留供应商原值；估算成交额 = 前复权收盘价 × 供应商成交量，不等于实际成交额。</p>
        <div v-if="result.rows.length" class="table-scroll">
          <table>
            <thead><tr><th>交易日（美东）</th><th>开盘 USD</th><th>最高 USD</th><th>最低 USD</th><th>收盘 USD</th><th>成交量</th><th>实际成交额 USD</th><th>估算成交额 USD</th></tr></thead>
            <tbody><tr v-for="row in result.rows" :key="row.date">
              <td>{{ row.date }}</td><td>{{ number(row.open) }}</td><td>{{ number(row.high) }}</td>
              <td>{{ number(row.low) }}</td><td>{{ number(row.close) }}</td><td>{{ number(row.volume) }}</td>
              <td>{{ number(row.turnover) }}</td><td>{{ number(row.turnover_estimated_usd) }}</td>
            </tr></tbody>
          </table>
        </div>
        <p v-else>所选日期范围内没有日线。</p>
        <div class="query">
          <span>符合 {{ result.total }} 根 · 第 {{ result.page }} / {{ pages }} 页</span>
          <button type="button" :disabled="loading || result.page <= 1" @click="loadPage(result.page - 1)">上一页</button>
          <button type="button" data-test="us-kline-next" :disabled="loading || result.page >= pages" @click="loadPage(result.page + 1)">下一页</button>
        </div>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useApi } from '../composables/useApi.js'

const { getUSKlineHistory } = useApi()
const form = reactive({ code: '', start_date: '', end_date: '' })
const result = ref(null)
const loading = ref(false)
const error = ref('')
let submitted = null
const pages = computed(() => Math.max(1, Math.ceil(result.value.total / result.value.page_size)))
const status = computed(() => {
  const summary = result.value.summary
  if (summary.is_fresh) return '已覆盖目标完整交易日'
  return summary.covers_target ? '获取时间未确认满足收盘要求' : '未覆盖目标完整交易日'
})
const fetchTime = computed(() => {
  const timestamp = Date.parse(result.value.metadata.fetched_at)
  return Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Shanghai' }).format(timestamp) + '（北京时间）'
    : '未知'
})
const formatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 6 })
const number = value => typeof value === 'number' && Number.isFinite(value) ? formatter.format(value) : '缺失'

async function loadPage(page) {
  if (loading.value || !submitted) return
  loading.value = true
  error.value = ''
  try {
    const data = await getUSKlineHistory({ ...submitted, page, page_size: 50 })
    if (!data.ok || !data.summary) throw new Error(data.message || '美股日线查询失败')
    result.value = data
  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

function submit() {
  if (loading.value) return
  if (!form.code) { error.value = '请输入美股代码'; return }
  if (form.start_date && form.end_date && form.start_date > form.end_date) {
    error.value = '起始日期不能晚于结束日期'
    return
  }
  submitted = { ...form }
  result.value = null
  loadPage(1)
}
</script>

<style scoped>
.us-history { background: var(--bg-panel); border: 1px solid var(--border); padding: 18px; }
.query { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin: 16px 0; }
label { display: grid; gap: 5px; }
input, button { padding: 7px 10px; background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); }
.error { color: #f37676; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 9px; border-bottom: 1px solid var(--border); text-align: right; white-space: nowrap; }
th:first-child, td:first-child { text-align: left; }
</style>
