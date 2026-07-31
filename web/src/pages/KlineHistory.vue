<template>
  <div class="kline-page">
    <section class="panel hero">
      <div>
        <p class="eyebrow">本地数据诊断</p>
        <h1>个股 K 线数据诊断</h1>
        <p class="hint">核对本地历史 K 线是否覆盖最近一个完整交易日。查询本身只读，重新拉取按钮会明确请求行情源。</p>
      </div>
      <div class="status-pill" :class="{ stale: summary?.needs_refetch, fresh: summary?.is_fresh }">
        {{ summary?.needs_refetch ? '需要重新拉取' : summary?.is_fresh ? '数据最新' : '等待查询' }}
      </div>
    </section>

    <section class="panel health-panel">
      <div class="table-head">
        <div>
          <h2>全市场数据健康</h2>
          <p>自动列出需要关注的停牌、异常和拉取失败股票，不需要手动撞代码。</p>
        </div>
        <div class="panel-actions">
          <button
            class="btn-secondary danger-action"
            :disabled="bulkRefreshing || healthLoading || !bulkRefreshableCount"
            data-test="bulk-refresh-health"
            @click="bulkRefreshHealth"
          >
            {{ bulkRefreshing ? '批量拉取中...' : `一键重新拉取 ${bulkRefreshableCount} 只` }}
          </button>
          <button class="btn-secondary" :disabled="healthLoading || bulkRefreshing" @click="loadKlineHealth">
            {{ healthLoading ? '刷新中...' : '刷新健康状态' }}
          </button>
        </div>
      </div>

      <div class="maintenance-divider">
        <span>数据维护工具</span>
        <small>行情重拉与远端新鲜度验证</small>
      </div>
      <div class="tickflow-box" data-test="tickflow-status">
        <div class="tickflow-box-head">
          <div>
            <strong>TickFlow 全市场重新拉取</strong>
            <p>固定参数：整个股票池 · 约 1100 根前复权日线 · 四个宽基指数（不复权）· 每批 100 只 · 5 个并发工作线程</p>
          </div>
          <button
            class="btn-secondary maintenance-action"
            :disabled="tickFlowStarting || tickFlowStatus?.running"
            data-test="tickflow-full-refresh"
            @click="startTickFlowRefresh"
          >
            {{ tickFlowStatus?.running ? 'TickFlow 全量拉取中...' : '启动全市场重拉' }}
          </button>
        </div>
        <div v-if="tickFlowStatus?.status && tickFlowStatus.status !== 'idle'" class="tickflow-progress">
          <strong>{{ tickFlowStatusLabel }}</strong>
          <span>{{ tickFlowStatus.processed || 0 }} / {{ tickFlowStatus.total_stocks || 0 }}</span>
          <span>成功 {{ tickFlowStatus.succeeded || 0 }}，失败 {{ tickFlowStatus.failed || 0 }}</span>
          <span v-if="tickFlowStatus.total_chunks">批次 {{ tickFlowStatus.current_chunk || 0 }} / {{ tickFlowStatus.total_chunks }}</span>
          <span v-if="tickFlowStatus.total_indexes">
            指数 {{ tickFlowStatus.indexes_processed || 0 }} / {{ tickFlowStatus.total_indexes }}，失败 {{ tickFlowStatus.indexes_failed || 0 }}
          </span>
        </div>
        <p v-if="tickFlowError" class="error-line">{{ tickFlowError }}</p>
        <p v-if="tickFlowStatus?.report_path" class="tickflow-report">
          任务报告：{{ tickFlowStatus.report_path }}
        </p>
        <ul v-if="tickFlowStatus?.failures?.length" class="tickflow-failures">
          <li v-for="item in tickFlowStatus.failures.slice(0, 10)" :key="item.code">
            {{ item.code }}：{{ item.error }}
          </li>
        </ul>
        <ul v-if="tickFlowStatus?.index_failures?.length" class="tickflow-failures">
          <li v-for="item in tickFlowStatus.index_failures" :key="item.symbol">
            {{ item.symbol }}：{{ item.error }}
          </li>
        </ul>
      </div>

      <div class="tickflow-probe" data-test="tickflow-freshness-panel">
        <div class="table-head">
          <div>
            <h2>TickFlow 数据新鲜度测试</h2>
            <p>真实读取指定股票的前复权日线和四个宽基指数，不写入本地数据库。</p>
          </div>
          <div class="probe-actions">
            <input
              v-model.trim="probeCode"
              maxlength="6"
              inputmode="numeric"
              placeholder="6位股票代码"
              data-test="tickflow-probe-code"
              @keyup.enter="runTickFlowProbe"
            />
            <button
              class="btn-secondary"
              :disabled="probeLoading"
              data-test="tickflow-freshness-check"
              @click="runTickFlowProbe"
            >
              {{ probeLoading ? '测试中...' : '测试远端新鲜度' }}
            </button>
          </div>
        </div>
        <p v-if="probeError" class="error-line">{{ probeError }}</p>
        <div v-if="probeResult" class="probe-summary">
          <span>目标完整交易日：<strong>{{ fmt(probeResult.target_trade_date) }}</strong></span>
          <span>检测时间：<strong>{{ fmt(probeResult.checked_at) }}</strong></span>
          <span>整体状态：<strong>{{ probeOverallLabel }}</strong></span>
        </div>
        <table v-if="probeItems.length" class="probe-table">
          <thead>
            <tr>
              <th>对象</th>
              <th>远端最新日</th>
              <th>本地最新日</th>
              <th>目标日</th>
              <th>状态</th>
              <th>行数</th>
              <th>耗时</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in probeItems" :key="`${item.code}-${item.symbol}`">
              <td>{{ item.code }} {{ item.name || '' }}</td>
              <td>{{ fmt(item.remote_latest_date) }}</td>
              <td>{{ fmt(item.local_latest_date) }}</td>
              <td>{{ fmt(item.target_trade_date) }}</td>
              <td><span class="health-badge" :class="probeStatusClass(item.status)">{{ probeStatusLabel(item.status) }}</span></td>
              <td>{{ item.row_count ?? 0 }}</td>
              <td>{{ item.elapsed_ms ?? 0 }} ms</td>
              <td class="reason-cell">{{ item.error || '--' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="health-grid" v-if="healthSummary">
        <button class="health-card ok" @click="setHealthFilter('fresh')">
          <span>最新数据</span>
          <strong>{{ healthSummary.fresh }} / {{ healthSummary.total }}</strong>
        </button>
        <button class="health-card warning" @click="setHealthFilter('no_trade')">
          <span>停牌/无交易</span>
          <strong>{{ healthSummary.no_trade }}</strong>
        </button>
        <button class="health-card danger" @click="setHealthFilter('anomaly')">
          <span>异常/需重拉</span>
          <strong>{{ healthSummary.anomaly }}</strong>
        </button>
        <button class="health-card danger" @click="setHealthFilter('failed')">
          <span>拉取失败</span>
          <strong>{{ healthSummary.failed }}</strong>
        </button>
        <div class="health-card">
          <span>目标完整交易日</span>
          <strong>{{ fmt(healthSummary.target_trade_date) }}</strong>
        </div>
        <div class="health-card">
          <span>收盘校验时间</span>
          <strong>{{ fmt(healthSummary.min_fetch_time) }}</strong>
        </div>
      </div>

      <p v-if="healthError" class="error-line">{{ healthError }}</p>
      <p v-if="bulkRefreshMessage" class="success-line">{{ bulkRefreshMessage }}</p>

      <div class="table-head sub-head">
        <div>
          <h2>数据问题列表</h2>
          <p>当前筛选 {{ healthFilterLabel }}，共 {{ healthTotal }} 条</p>
        </div>
        <div class="health-filters">
          <button :class="{ active: healthFilter === 'problem' }" @click="setHealthFilter('problem')">问题</button>
          <button :class="{ active: healthFilter === 'anomaly' }" @click="setHealthFilter('anomaly')">异常</button>
          <button :class="{ active: healthFilter === 'failed' }" @click="setHealthFilter('failed')">失败</button>
          <button :class="{ active: healthFilter === 'no_trade' }" @click="setHealthFilter('no_trade')">停牌</button>
          <button :class="{ active: healthFilter === 'all' }" @click="setHealthFilter('all')">全部</button>
        </div>
      </div>

      <table v-if="healthItems.length" class="health-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>股票</th>
            <th>最新K线日</th>
            <th>目标交易日</th>
            <th>最近拉取时间</th>
            <th>问题原因</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in healthItems" :key="item.code">
            <td><span class="health-badge" :class="item.severity">{{ healthStatusLabel(item) }}</span></td>
            <td>
              <a
                class="stock-link"
                :href="baiduSearchUrl(item.code)"
                target="_blank"
                rel="noopener noreferrer"
                :data-test="`stock-search-${item.code}`"
              >
                {{ item.code }}
              </a>
              {{ item.name || '' }}
            </td>
            <td>{{ fmt(item.latest_kline_date) }}</td>
            <td>{{ fmt(item.target_trade_date) }}</td>
            <td>{{ fmt(item.latest_fetch_time) }}</td>
            <td class="reason-cell">{{ item.reason }}</td>
            <td>
              <div class="action-cell">
                <button class="link-button" :data-test="`inspect-health-row-${item.code}`" @click="inspectHealthRow(item)">
                查看
                </button>
                <button
                  v-if="item.needs_refetch"
                  class="link-button danger-action"
                  :disabled="isRefreshing(item.code)"
                  :data-test="`refresh-health-row-${item.code}`"
                  @click="refreshHealthRow(item)"
                >
                  {{ isRefreshing(item.code) ? '拉取中...' : '重新拉取' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        当前筛选下没有数据问题
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
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useApi } from '../composables/useApi.js'

const {
  getKlineHistory,
  getKlineHealth,
  refreshKlineData,
  refreshKlineHealth,
  startTickFlowFullRefresh,
  getTickFlowFullRefreshStatus,
  checkTickFlowFreshness,
} = useApi()

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
const healthSummary = ref(null)
const healthItems = ref([])
const healthTotal = ref(0)
const healthLoading = ref(false)
const healthError = ref('')
const healthFilter = ref('problem')
const refreshingCodes = ref({})
const bulkRefreshing = ref(false)
const bulkRefreshMessage = ref('')
const tickFlowStatus = ref(null)
const tickFlowStarting = ref(false)
const tickFlowError = ref('')
const probeCode = ref('000655')
const probeLoading = ref(false)
const probeError = ref('')
const probeResult = ref(null)
let tickFlowPollTimer = null

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / form.page_size)))
const healthFilterLabel = computed(() => {
  const labels = { problem: '问题', anomaly: '异常/需重拉', failed: '拉取失败', no_trade: '停牌/无交易', fresh: '最新', all: '全部' }
  return labels[healthFilter.value] || healthFilter.value
})
const bulkRefreshableCount = computed(() => {
  if (!healthSummary.value) return 0
  if (healthFilter.value === 'problem' || healthFilter.value === 'all') return healthSummary.value.needs_refetch || 0
  if (healthFilter.value === 'anomaly' || healthFilter.value === 'failed') return healthTotal.value || 0
  return healthItems.value.filter(item => item.needs_refetch).length
})
const tickFlowStatusLabel = computed(() => {
  const labels = {
    running: '正在全量重新拉取',
    completed: '全量重新拉取完成',
    completed_with_errors: '全量重拉完成，但有失败股票',
    failed: '全量重新拉取失败',
  }
  return labels[tickFlowStatus.value?.status] || tickFlowStatus.value?.status || '尚未启动'
})
const probeItems = computed(() => {
  if (!probeResult.value) return []
  return [probeResult.value.stock, ...(probeResult.value.indexes || [])].filter(Boolean)
})
const probeOverallLabel = computed(() => {
  const labels = {
    FRESH: '全部最新',
    STALE: '存在落后数据',
    PARTIAL_FAILURE: '部分请求失败',
    FAILED: '全部请求失败',
  }
  return labels[probeResult.value?.overall_status] || probeResult.value?.overall_status || '--'
})

function probeStatusLabel(status) {
  return { FRESH: '最新', STALE: '落后', FAILED: '请求失败' }[status] || status || '--'
}

function probeStatusClass(status) {
  return status === 'FRESH' ? 'ok' : status === 'STALE' ? 'warning' : 'danger'
}

async function runTickFlowProbe() {
  const code = probeCode.value.trim()
  if (!/^\d{6}$/.test(code)) {
    probeError.value = '请输入6位股票代码'
    return
  }
  if (probeLoading.value) return
  probeLoading.value = true
  probeError.value = ''
  try {
    const data = await checkTickFlowFreshness(code)
    if (data.ok === false) throw new Error(data.message || data.error || '新鲜度测试失败')
    probeResult.value = data
  } catch (err) {
    probeError.value = `TickFlow 新鲜度测试失败：${err?.message || '未知错误'}`
  } finally {
    probeLoading.value = false
  }
}

function clearTickFlowPoll() {
  if (tickFlowPollTimer) {
    clearTimeout(tickFlowPollTimer)
    tickFlowPollTimer = null
  }
}

function scheduleTickFlowPoll() {
  clearTickFlowPoll()
  if (!tickFlowStatus.value?.running) return
  tickFlowPollTimer = setTimeout(async () => {
    tickFlowPollTimer = null
    await loadTickFlowStatus(true)
  }, 2000)
}

async function loadTickFlowStatus(refreshHealthOnTerminal = false) {
  try {
    const data = await getTickFlowFullRefreshStatus()
    if (data.ok === false) throw new Error(data.message || data.error || 'TickFlow 状态查询失败')
    const wasRunning = Boolean(tickFlowStatus.value?.running)
    tickFlowStatus.value = data
    tickFlowError.value = ''
    if (data.running) {
      scheduleTickFlowPoll()
    } else {
      clearTickFlowPoll()
      if (refreshHealthOnTerminal && wasRunning) await loadKlineHealth()
    }
  } catch (err) {
    tickFlowError.value = `TickFlow 状态查询失败：${err?.message || '未知错误'}`
    if (tickFlowStatus.value?.running) scheduleTickFlowPoll()
  }
}

async function startTickFlowRefresh() {
  if (tickFlowStarting.value || tickFlowStatus.value?.running) return
  const confirmed = window.confirm(
    '将先备份数据库，再使用 TickFlow 对整个股票池强制重新拉取约 1100 根前复权日线，并同步重拉四个宽基指数。是否继续？',
  )
  if (!confirmed) return
  tickFlowStarting.value = true
  tickFlowError.value = ''
  try {
    const data = await startTickFlowFullRefresh()
    if (data.ok === false) throw new Error(data.message || data.error || 'TickFlow 全量任务启动失败')
    tickFlowStatus.value = data
    scheduleTickFlowPoll()
  } catch (err) {
    tickFlowError.value = `TickFlow 全量任务启动失败：${err?.message || '未知错误'}`
  } finally {
    tickFlowStarting.value = false
  }
}

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

function healthStatusLabel(item) {
  const labels = {
    fresh: '最新',
    no_trade: '停牌',
    anomaly: '异常',
    failed: '失败',
    missing: '缺失',
    stale: '过期',
  }
  return labels[item.health_status] || item.health_status || '--'
}

function baiduSearchUrl(code) {
  return `https://www.baidu.com/s?ie=UTF-8&wd=${encodeURIComponent(code)}`
}

function isRefreshing(code) {
  return Boolean(refreshingCodes.value[code])
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

async function loadKlineHealth() {
  healthLoading.value = true
  healthError.value = ''
  try {
    const data = await getKlineHealth({ status: healthFilter.value, page: 1, page_size: 100 })
    if (data.ok === false) {
      throw new Error(data.message || data.error || '健康检查失败')
    }
    healthSummary.value = data.summary || null
    healthItems.value = data.items || []
    healthTotal.value = data.total || 0
  } catch (err) {
    healthError.value = err?.message || '健康检查失败'
  } finally {
    healthLoading.value = false
  }
}

function setHealthFilter(nextFilter) {
  healthFilter.value = nextFilter
  loadKlineHealth()
}

function inspectHealthRow(item) {
  form.code = item.code
  loadPage(1)
}

async function refreshHealthRow(item) {
  if (!item?.code || isRefreshing(item.code)) return
  refreshingCodes.value = { ...refreshingCodes.value, [item.code]: true }
  healthError.value = ''
  try {
    const data = await refreshKlineData(item.code)
    if (data.ok === false) {
      throw new Error(data.message || data.error || '重新拉取失败')
    }
    form.code = item.code
    await Promise.all([loadKlineHealth(), loadPage(1)])
  } catch (err) {
    healthError.value = `${item.code} 重新拉取失败：${err?.message || '未知错误'}`
  } finally {
    const next = { ...refreshingCodes.value }
    delete next[item.code]
    refreshingCodes.value = next
  }
}

async function bulkRefreshHealth() {
  if (bulkRefreshing.value) return
  bulkRefreshing.value = true
  healthError.value = ''
  bulkRefreshMessage.value = ''
  try {
    const data = await refreshKlineHealth({ status: healthFilter.value })
    if (data.ok === false) {
      throw new Error(data.message || data.error || '批量重新拉取失败')
    }
    bulkRefreshMessage.value = `批量重拉完成：成功 ${data.succeeded_count || 0}，失败 ${data.failed_count || 0}，跳过 ${data.skipped_count || 0}`
    await loadKlineHealth()
  } catch (err) {
    healthError.value = `批量重新拉取失败：${err?.message || '未知错误'}`
  } finally {
    bulkRefreshing.value = false
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
  loadKlineHealth()
  loadPage(1)
  loadTickFlowStatus()
})

onBeforeUnmount(clearTickFlowPoll)
</script>

<style scoped>
.kline-page {
  padding: 22px 24px 40px;
  max-width: 1600px;
  margin: 0 auto;
  color: var(--text-primary);
}
.panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 16px 18px;
}
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  border-left: 2px solid var(--gold);
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--gold);
  font: 10px/1 var(--font-mono);
  letter-spacing: 0.16em;
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
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  font: 11px/1 var(--font-mono);
}
.status-pill.fresh {
  color: var(--success);
  border-color: rgba(32, 173, 114, 0.35);
  background: var(--success-glow);
}
.status-pill.stale {
  color: var(--danger);
  border-color: rgba(239, 91, 91, 0.35);
  background: rgba(239, 91, 91, 0.08);
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
  border-radius: var(--radius-sm);
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
  border-color: rgba(32, 173, 114, 0.35);
}
.summary-card.warning {
  border-color: rgba(239, 91, 91, 0.35);
}
.health-panel {
  margin-bottom: 16px;
}
.maintenance-divider {
  display: flex; align-items: baseline; gap: 10px; margin: 16px 0 8px;
  padding-top: 13px; border-top: 1px solid var(--border);
}
.maintenance-divider span { color: var(--text-secondary); font-size: 11px; font-weight: 700; letter-spacing: 0.08em; }
.maintenance-divider small { color: var(--text-muted); font-size: 10px; }
.tickflow-box {
  display: grid;
  gap: 10px;
  margin: 14px 0 16px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(16,24,36,0.42);
}
.tickflow-box-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.maintenance-action { flex-shrink: 0; color: var(--text-secondary) !important; }
.maintenance-action:hover:not(:disabled) { border-color: var(--warn-orange) !important; color: var(--warn-orange) !important; }
.tickflow-box p {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 13px;
}
.tickflow-progress {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  align-items: center;
}
.tickflow-progress span {
  color: var(--text-secondary);
  font-size: 13px;
}
.tickflow-failures {
  margin: 0;
  padding-left: 20px;
  color: var(--danger);
  font-size: 12px;
}
.tickflow-probe {
  margin: 0 0 16px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(16,24,36,0.42);
}
.probe-actions,
.probe-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
}
.probe-actions input {
  width: 140px;
}
.probe-summary {
  margin: 8px 0 14px;
  color: var(--text-secondary);
  font-size: 13px;
}
.probe-table th,
.probe-table td {
  text-align: left;
}
.health-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0 16px;
}
.health-card {
  text-align: left;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  padding: 14px;
}
button.health-card {
  cursor: pointer;
}
.health-card span {
  display: block;
  color: var(--text-secondary);
  font-size: 12px;
  margin-bottom: 8px;
}
.health-card strong {
  display: block;
  font-size: 18px;
}
.health-card.ok {
  border-color: rgba(32, 173, 114, 0.35);
}
.health-card.warning {
  border-color: rgba(234, 179, 8, 0.45);
}
.health-card.danger {
  border-color: rgba(239, 91, 91, 0.42);
}
.sub-head {
  margin-top: 8px;
}
.panel-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.btn-secondary,
.health-filters button,
.link-button {
  height: 32px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0 12px;
  cursor: pointer;
}
.health-filters {
  display: flex;
  align-items: center;
  gap: 8px;
}
.health-filters button.active {
  border-color: var(--accent);
  color: var(--accent);
}
.health-table th,
.health-table td {
  text-align: left;
}
.reason-cell {
  max-width: 340px;
  color: var(--text-secondary);
}
.health-badge {
  display: inline-flex;
  align-items: center;
  min-width: 44px;
  justify-content: center;
  border-radius: 2px;
  padding: 3px 7px;
  font-size: 12px;
}
.health-badge.ok {
  color: var(--success);
  background: var(--success-glow);
}
.health-badge.warning {
  color: #eab308;
  background: rgba(234, 179, 8, 0.12);
}
.health-badge.danger {
  color: var(--danger);
  background: rgba(239, 91, 91, 0.10);
}
.link-button {
  color: var(--accent);
}
.stock-link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
}
.stock-link:hover {
  text-decoration: underline;
}
.action-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.danger-action {
  color: var(--danger);
  border-color: rgba(239, 91, 91, 0.35);
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
  border-radius: var(--radius-sm);
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 0 10px;
}
.btn-primary,
.pager button {
  height: 34px;
  border: none;
  border-radius: var(--radius-sm);
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
  color: var(--danger);
}
.success-line {
  margin: 0 0 16px;
  color: var(--success);
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
  position: sticky;
  top: 0;
  z-index: 2;
  background: #0d1520;
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
  .query-panel,
  .health-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .summary-card.wide {
    grid-column: span 2;
  }
}
</style>
