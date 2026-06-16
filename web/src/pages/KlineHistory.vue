<template>
  <div class="kline-page">
    <section class="panel hero">
      <div>
        <p class="eyebrow">本地数据诊断</p>
        <h1>个股 K 线数据诊断</h1>
        <p class="hint">核对本地历史 K 线是否覆盖最近一个完整交易日。本页面只读本地数据库，不触发行情源拉取。</p>
      </div>
      <div class="status-pill" :class="{ stale: summary?.needs_refetch, fresh: summary?.is_fresh }">
        {{ summary?.needs_refetch ? '需要重新拉取' : summary?.is_fresh ? '数据最新' : '等待查询' }}
      </div>
    </section>

    <section class="summary-grid" v-if="summary">
      <div class="summary-card">
        <span>最新K线日期</span>
        <strong>{{ fmt(summary.latest_kline_date) }}</strong>
      </div>
      <div class="summary-card">
        <span>最近拉取时间</span>
        <strong>{{ fmt(summary.latest_fetch_time) }}</strong>
      </div>
      <div class="summary-card">
        <span>目标完整交易日</span>
        <strong>{{ fmt(summary.target_trade_date) }}</strong>
      </div>
      <div class="summary-card">
        <span>收盘校验时间</span>
        <strong>{{ fmt(summary.min_fetch_time) }}</strong>
      </div>
      <div class="summary-card">
        <span>行情状态</span>
        <strong>{{ summary.quote_status || 'not_requested' }}</strong>
      </div>
      <div class="summary-card wide" :class="{ warning: summary.needs_refetch, ok: summary.is_fresh }">
        <span>数据状态</span>
        <strong>{{ summary.needs_refetch ? '需要重新拉取' : '数据最新' }}</strong>
        <em>{{ summary.reason }}</em>
      </div>
    </section>

    <section class="panel query-panel">
      <label>
        股票代码
        <input v-model.trim="form.code" placeholder="例如 000831" @keyup.enter="submitQuery" />
      </label>
      <label>
        开始日期
        <input v-model="form.start_date" type="date" />
      </label>
      <label>
        结束日期
        <input v-model="form.end_date" type="date" />
      </label>
      <label>
        每页
        <select v-model.number="form.page_size">
          <option :value="20">20</option>
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
        </select>
      </label>
      <button class="btn-primary" :disabled="loading || !form.code" @click="submitQuery">
        {{ loading ? '查询中...' : '查询' }}
      </button>
    </section>

    <p v-if="error" class="error-line">{{ error }}</p>

    <section class="panel table-panel">
      <div class="table-head">
        <div>
          <h2>{{ currentCode || '--' }} 历史 K 线</h2>
          <p>共 {{ total }} 条，本页 {{ rows.length }} 条</p>
        </div>
        <div class="pager">
          <button :disabled="loading || page <= 1" @click="loadPage(page - 1)">上一页</button>
          <span>第 {{ page }} / {{ totalPages }} 页</span>
          <button data-test="next-page" :disabled="loading || page >= totalPages" @click="loadPage(page + 1)">下一页</button>
        </div>
      </div>

      <table v-if="rows.length">
        <thead>
          <tr>
            <th>日期</th>
            <th>开盘</th>
            <th>最高</th>
            <th>最低</th>
            <th>收盘</th>
            <th>成交量</th>
            <th>成交额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.date">
            <td>{{ row.date }}</td>
            <td>{{ number(row.open) }}</td>
            <td>{{ number(row.high) }}</td>
            <td>{{ number(row.low) }}</td>
            <td>{{ number(row.close) }}</td>
            <td>{{ integer(row.volume) }}</td>
            <td>{{ integer(row.turnover) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        本地没有该股票 K 线数据
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useApi } from '../composables/useApi.js'

const { getKlineHistory } = useApi()

const form = reactive({
  code: '000831',
  start_date: '',
  end_date: '',
  page_size: 50,
})
const rows = ref([])
const summary = ref(null)
const page = ref(1)
const total = ref(0)
const currentCode = ref('')
const loading = ref(false)
const error = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / form.page_size)))

function fmt(value) {
  return value || '--'
}

function number(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toFixed(2)
}

function integer(value) {
  if (value === null || value === undefined || value === '') return '--'
  return Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function buildParams(nextPage) {
  return {
    code: form.code,
    start_date: form.start_date,
    end_date: form.end_date,
    page: nextPage,
    page_size: form.page_size,
  }
}

async function loadPage(nextPage = 1) {
  if (!form.code) return
  loading.value = true
  error.value = ''
  try {
    const data = await getKlineHistory(buildParams(nextPage))
    if (data.ok === false) {
      throw new Error(data.message || data.error || '查询失败')
    }
    rows.value = data.rows || []
    summary.value = data.summary || null
    page.value = data.page || nextPage
    total.value = data.total || 0
    currentCode.value = data.code || form.code
  } catch (err) {
    error.value = err?.message || '查询失败'
  } finally {
    loading.value = false
  }
}

function submitQuery() {
  loadPage(1)
}

onMounted(() => {
  loadPage(1)
})
</script>

<style scoped>
.kline-page {
  padding: 20px;
  color: var(--text-primary);
}
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px;
}
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--accent);
  font-size: 12px;
  letter-spacing: 0.08em;
}
h1, h2, p {
  margin: 0;
}
h1 {
  font-size: 24px;
}
h2 {
  font-size: 16px;
}
.hint,
.table-head p {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}
.status-pill {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 10px 16px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.status-pill.fresh {
  color: var(--up-red);
  border-color: rgba(239, 68, 68, 0.35);
}
.status-pill.stale {
  color: var(--down-green);
  border-color: rgba(34, 197, 94, 0.35);
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.summary-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
}
.summary-card span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 8px;
}
.summary-card strong {
  display: block;
  font-size: 15px;
}
.summary-card em {
  display: block;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-style: normal;
}
.summary-card.wide {
  grid-column: span 2;
}
.summary-card.ok {
  border-color: rgba(239, 68, 68, 0.35);
}
.summary-card.warning {
  border-color: rgba(34, 197, 94, 0.35);
}
.query-panel {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr 120px auto;
  gap: 12px;
  align-items: end;
  margin-bottom: 16px;
}
label {
  display: grid;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}
input,
select {
  height: 34px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0 10px;
}
.btn-primary,
.pager button {
  height: 34px;
  border: none;
  border-radius: 6px;
  background: var(--accent);
  color: #fff;
  padding: 0 14px;
  cursor: pointer;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.error-line {
  margin: 0 0 16px;
  color: var(--down-green);
}
.table-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.pager {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  font-size: 13px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  padding: 10px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
th:first-child,
td:first-child {
  text-align: left;
}
th {
  color: var(--text-secondary);
  font-weight: 500;
}
.empty-state {
  padding: 32px;
  text-align: center;
  color: var(--text-secondary);
}
@media (max-width: 1100px) {
  .summary-grid,
  .query-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .summary-card.wide {
    grid-column: span 2;
  }
}
</style>
