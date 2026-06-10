<template>
  <div class="page-content">
    <!-- Market Status Bar -->
    <div class="status-bar">
      <span class="market-status">
        <span class="status-dot" :class="marketStatusClass"></span>
        {{ marketStatusText }}
      </span>
      <span class="status-sep">|</span>
      <span class="current-time">{{ currentTime }}</span>
    </div>
    <!-- Metrics Row -->
    <div class="metrics-row">
      <MetricCard label="今日候选" :value="metrics.candidates" sub="扫描结果" color="blue" />
      <MetricCard label="A级信号 ≥80" :value="metrics.aGrade" :sub="topSignalSub" color="gold" />
      <MetricCard label="突破确认" :value="metrics.breakout" sub="放量突破" color="red" />
      <MetricCard label="接近突破" :value="metrics.nearBreakout" sub="距突破 &lt; 5%" color="orange" />
      <MetricCard label="量能确认" :value="metrics.volumeOk" sub="柄部缩量 · 突破放量" />
      <MetricCard label="最高评分" :value="metrics.topScore" :sub="topScoreSub" color="gold" />
    </div>

    <!-- Error message -->
    <div v-if="scanError" class="error-banner">
      ⚠ {{ scanError }}
    </div>

    <!-- Two Column -->
    <div class="two-col">
      <!-- Discovery Panel -->
      <div class="panel">
        <div class="panel-header">
          <span>◉ 最新发现 · 候选信号</span>
          <span class="sub-title">按发现时间排序</span>
        </div>
        <div v-if="discoveries.length === 0" class="empty-state">
          <template v-if="scanning">
            扫描进行中，当前暂未发现符合条件的杯柄结构候选<br/>
            <span class="empty-sub">系统将持续识别形态评分、突破位与量能确认信号</span>
          </template>
          <template v-else>
            暂无扫描结果<br/>
            <span class="empty-sub">点击右侧「开始扫描」，启动全市场杯柄结构识别</span>
          </template>
        </div>
        <DiscoveryItem
          v-for="d in discoveries"
          :key="d.code"
          :code="d.code"
          :name="d.name"
          :score="d.score"
          :rating="d.rating"
          :status="d.status"
          :detail="d.detail"
          @click="goToStock(d.code)"
        />
      </div>

      <!-- Scan Engine -->
      <ScanEngine
        :running="scanning"
        :scanned="scanProgress.scanned"
        :total="scanProgress.total"
        :currentCode="scanProgress.currentCode"
        :currentName="scanProgress.currentName"
        :skipped="scanProgress.skipped"
        :failed="scanProgress.failed"
        :candidates="scanProgress.candidates"
        :latestTradeDate="scanProgress.latestTradeDate"
        :stockPoolSource="scanProgress.stockPoolSource"
        :logLines="logLines"
        @start="handleStartScan"
        @start-strategy2="handleStartStrategy2Scan"
      />
    </div>

    <div class="panel failure-panel" v-if="scanProgress.taskId && failures.length > 0">
      <div class="panel-header">
        <span>失败股票 · {{ failures.length }}</span>
        <button class="retry-btn" :disabled="scanning" @click="handleRetryFailed">重新拉取</button>
      </div>
      <div v-for="f in failures" :key="f.code" class="failure-row">
        <span class="code">{{ f.code }}</span>
        <span>{{ f.name }}</span>
        <span class="muted">{{ f.status_reason || f.error_detail || '--' }}</span>
        <span class="muted">主源 {{ f.primary_attempts || 0 }} · 备源 {{ f.fallback_attempts || 0 }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import DiscoveryItem from '../components/DiscoveryItem.vue'
import ScanEngine from '../components/ScanEngine.vue'

const router = useRouter()
const route = useRoute()
const { startScan, startStrategy2Scan, getScanStatus, getCandidates, getTaskStocks, retryFailedStocks } = useApi()

// Market status & clock
const currentTime = ref('')
const marketStatusText = ref('')
const marketStatusClass = ref('')

function updateTime() {
  const now = new Date()
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const ss = String(now.getSeconds()).padStart(2, '0')
  currentTime.value = `${hh}:${mm}:${ss}`

  const day = now.getDay()
  const totalMinutes = now.getHours() * 60 + now.getMinutes()
  const isWeekday = day >= 1 && day <= 5

  // Trading sessions in minutes: 9:30-11:30, 13:00-15:00
  const MORNING_OPEN  = 9 * 60 + 30   // 570
  const MORNING_CLOSE = 11 * 60 + 30  // 690
  const AFTERNOON_OPEN  = 13 * 60     // 780
  const AFTERNOON_CLOSE = 15 * 60     // 900

  const inSession = (totalMinutes >= MORNING_OPEN && totalMinutes <= MORNING_CLOSE)
                 || (totalMinutes >= AFTERNOON_OPEN && totalMinutes <= AFTERNOON_CLOSE)

  if (isWeekday && inSession) {
    marketStatusText.value = '开盘中'
    marketStatusClass.value = 'open'
  } else if (isWeekday && totalMinutes > AFTERNOON_CLOSE) {
    marketStatusText.value = '已收盘'
    marketStatusClass.value = 'closed'
  } else {
    marketStatusText.value = '未开盘'
    marketStatusClass.value = 'pre'
  }
}

const scanning = ref(false)
const scanError = ref('')
const scanProgress = reactive({
  taskId: '',
  scanned: 0,
  total: 0,
  currentCode: '--',
  currentName: '--',
  skipped: 0,
  failed: 0,
  candidates: 0,
  latestTradeDate: '',
  stockPoolSource: '',
})
const logLines = ref([])
const discoveries = ref([])
const failures = ref([])
const metrics = reactive({ candidates: 0, aGrade: 0, breakout: 0, nearBreakout: 0, volumeOk: 0, topScore: 0 })

const topSignalSub = computed(() => discoveries.value.filter(d => d.score >= 80).map(d => d.name).slice(0, 3).join(' · ') || '--')
const topScoreSub = computed(() => {
  const top = discoveries.value.reduce((max, d) => d.score > max.score ? d : max, { score: 0, name: '--' })
  return top.name
})

let pollTimer = null
let clockTimer = null
let lastLogScanned = 0

function addLog(type, text) {
  const now = new Date()
  const ts = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`
  logLines.value.push({ time: ts, type, text })
  if (logLines.value.length > 50) logLines.value.shift()
}

function goToStock(code) {
  router.push(`/stock/${code}`)
}

async function handleStartScan() {
  scanError.value = ''
  try {
    const res = await startScan()
    if (!res.ok || res.error) {
      if (res.statusCode === 409) {
        scanError.value = `扫描已在运行中：${res.runningTaskId || res.running_task_id || '--'}`
      } else {
        scanError.value = res.error || '启动扫描失败'
      }
      return
    }
    scanProgress.taskId = res.task_id
    scanProgress.total = res.total_stocks || 0
    scanProgress.stockPoolSource = res.stock_pool_source || ''
    failures.value = []
    logLines.value = []
    lastLogScanned = 0
    scanning.value = true
    addLog('info', `扫描启动 · 全市场 ${scanProgress.total} 只 · 数据源 ${scanProgress.stockPoolSource || '--'}`)
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(pollStatus, 1000)
  } catch (e) {
    scanError.value = '无法连接到后端服务，请确认 python main.py serve 已启动'
    console.error('Start scan failed:', e)
  }
}

async function handleStartStrategy2Scan() {
  scanError.value = ''
  try {
    const res = await startStrategy2Scan()
    if (!res.ok || res.error) {
      if (res.statusCode === 409) {
        scanError.value = `策略2扫描冲突：${res.message || res.runningTaskId || '--'}`
      } else {
        scanError.value = res.message || res.error || '策略2启动扫描失败'
      }
      return
    }
    scanProgress.taskId = res.taskId
    scanProgress.total = 0
    scanProgress.stockPoolSource = ''
    failures.value = []
    logLines.value = []
    lastLogScanned = 0
    scanning.value = true
    addLog('info', `策略2扫描启动 · taskId ${res.taskId}`)
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(pollStatus, 1000)
  } catch (e) {
    scanError.value = '无法连接到后端服务'
    console.error('Strategy2 start scan failed:', e)
  }
}

function applyStats(status) {
  const stats = status.stats || {}
  scanProgress.taskId = status.task_id || scanProgress.taskId
  scanProgress.scanned = stats.processed || stats.scanned || 0
  scanProgress.total = stats.total_stocks || scanProgress.total || 0
  scanProgress.skipped = stats.skipped || 0
  scanProgress.failed = stats.failed || stats.failed_count || 0
  scanProgress.candidates = stats.candidates_found || stats.candidates_count || 0
  scanProgress.currentCode = stats.current_code || '--'
  scanProgress.currentName = stats.current_name || '--'
  scanProgress.latestTradeDate = stats.latest_trade_date || ''
  scanProgress.stockPoolSource = stats.stock_pool_source || scanProgress.stockPoolSource || ''
}

async function pollStatus() {
  try {
    const status = await getScanStatus()
    applyStats(status)
    // Progress log every ~50 stocks
    if (scanProgress.scanned - lastLogScanned >= 50) {
      lastLogScanned = scanProgress.scanned
      const pct = scanProgress.total > 0 ? Math.round(scanProgress.scanned / scanProgress.total * 100) : 0
      addLog('info', `进度 ${pct}% · 已处理 ${scanProgress.scanned} / ${scanProgress.total} · 候选 ${scanProgress.candidates}`)
    }
    if (!status.running && scanning.value) {
      scanning.value = false
      if (pollTimer) clearInterval(pollTimer)
      addLog('found', `扫描完成 · 发现 ${scanProgress.candidates} 个候选 · 跳过 ${scanProgress.skipped} · 失败 ${scanProgress.failed}`)
      await loadResults()
      await loadFailures()
    }
    // 实时更新候选发现
    if (status.stats?.discoveries) {
      status.stats.discoveries.forEach(d => {
        if (!discoveries.value.find(e => e.code === d.code)) {
          discoveries.value.unshift({
            code: d.code,
            name: d.name,
            score: d.score,
            rating: d.score >= 80 ? 'strong' : d.score >= 70 ? 'medium' : 'weak',
            status: statusFor(d),
            detail: formatDetail(d),
          })
        }
      })
      discoveries.value = dedupeDiscoveries(discoveries.value)
      updateMetrics()
    }
    if (scanProgress.failed) await loadFailures()
  } catch (e) {
    scanError.value = '状态查询失败'
    console.error(e)
  }
}

async function loadResults() {
  try {
    const data = await getCandidates()
    discoveries.value = dedupeDiscoveries((data.candidates || []).map(c => ({
      code: c.code,
      name: c.name,
      score: c.score,
      rating: c.score >= 80 ? 'strong' : c.score >= 70 ? 'medium' : 'weak',
      status: statusFor(c),
      detail: formatDetail(c),
    })))
    updateMetrics()
  } catch (e) {
    console.error('Load results failed:', e)
  }
}

async function loadFailures() {
  if (!scanProgress.taskId) return
  try {
    const data = await getTaskStocks(scanProgress.taskId, { status: 'failed', page_size: 20 })
    failures.value = data.stocks || []
  } catch (e) {
    console.error('Load failures failed:', e)
  }
}

async function handleRetryFailed() {
  if (!scanProgress.taskId) return
  const res = await retryFailedStocks(scanProgress.taskId)
  if (!res.ok || res.error) {
    scanError.value = res.statusCode === 409 ? `扫描已在运行中：${res.running_task_id || '--'}` : (res.error || '重拉失败股票失败')
    return
  }
  if (res.retry_count === 0) {
    scanError.value = '没有需要重拉的失败股票'
    return
  }
  scanning.value = true
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(pollStatus, 1000)
}

function dedupeDiscoveries(list) {
  const byCode = new Map()
  list.forEach(item => byCode.set(item.code, item))
  return Array.from(byCode.values())
}

function formatDetail(c) {
  const parts = []
  if (c.dry_stable_verdict) parts.push(c.dry_stable_verdict)
  if (c.volume_dry_score != null) parts.push(`量干${c.volume_dry_score}/10`)
  if (c.price_stable_score != null) parts.push(`价稳${c.price_stable_score}/10`)
  if (c.rr1) parts.push(`RR${Number(c.rr1).toFixed(1)}`)
  if (c.position_advice) parts.push(`仓位${c.position_advice}`)
  if (c.market_status) parts.push(`大盘${c.market_status}`)
  if (c.cup_duration) parts.push(`杯体${c.cup_duration}d`)
  if (c.cup_depth_pct) parts.push(`回撤${c.cup_depth_pct}%`)
  if (c.vol_multiplier) parts.push(`放量${Number(c.vol_multiplier).toFixed(1)}×`)
  return parts.join(' · ') || '--'
}

function statusFor(c) {
  const vk = c.verdict_key || ''
  // Strategy verdict takes priority over pattern breakout flag
  if (vk === 'BUY_LOW' || c.dry_stable_verdict === '可低吸') return 'near'
  if (vk === 'WATCH_BREAKOUT' || c.dry_stable_verdict === '突破确认') return 'confirm'
  if (vk.startsWith('WAIT_')) return 'wait'
  if (vk === 'REJECT' || c.dry_stable_verdict === '不建议买入') return 'watch'
  // Fallback: pattern-level flags
  if (c.is_breakout) return 'breakout'
  return c.score >= 70 ? 'near' : 'watch'
}

function updateMetrics() {
  const list = discoveries.value
  metrics.candidates = list.length
  metrics.aGrade = list.filter(d => d.score >= 80).length
  metrics.breakout = list.filter(d => d.status === 'breakout').length
  metrics.nearBreakout = list.filter(d => d.status === 'near').length
  metrics.volumeOk = list.filter(d => d.detail.includes('量干7') || d.detail.includes('量干8') || d.detail.includes('量干9') || d.detail.includes('量干10')).length
  metrics.topScore = list.reduce((max, d) => Math.max(max, d.score), 0)
}

onMounted(async () => {
  // If navigated from TaskCenter with ?task=..., load failures for that task
  const queryTaskId = route.query.task
  if (queryTaskId) {
    scanProgress.taskId = queryTaskId
    await loadFailures()
  }

  await loadResults()
  // Check if a scan is already running
  try {
    const status = await getScanStatus()
    applyStats(status)
    if (status.running) {
      scanning.value = true
      pollTimer = setInterval(pollStatus, 1000)
    }
    if (!queryTaskId) {
      await loadFailures()
    }
  } catch (e) { console.error('Check status on mount failed:', e) }
  updateTime()
  clockTimer = setInterval(updateTime, 1000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 1440px; margin: 0 auto; }
.metrics-row {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 20px;
}
@media (max-width: 1200px) { .metrics-row { grid-template-columns: repeat(3, 1fr); } }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 960px) { .two-col { grid-template-columns: 1fr; } }
.panel {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
}
.sub-title { font-weight: 400; font-size: 11px; }
.empty-state {
  padding: 40px 16px; text-align: center; color: var(--text-muted); font-size: 13px;
  line-height: 1.8;
}
.empty-sub { font-size: 12px; color: #3A4A5E; }
.error-banner {
  background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
  border-radius: 6px; padding: 12px 16px; margin-bottom: 12px;
  color: var(--up-red); font-size: 13px;
}
.failure-panel { margin-top: 12px; }
.retry-btn { background: transparent; color: var(--accent); border: 1px solid var(--accent); border-radius: 4px; padding: 4px 10px; cursor: pointer; }
.retry-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.failure-row { display: grid; grid-template-columns: 90px 120px 1fr 140px; gap: 8px; padding: 8px 16px; border-top: 1px solid var(--border); font-size: 12px; }
.failure-row .code { color: var(--accent); font-family: var(--font-mono); }
.muted { color: var(--text-muted); }
.status-bar {
  display: flex; align-items: center; justify-content: flex-end; gap: 10px;
  margin-bottom: 12px; font-size: 13px;
}
.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px;
}
.status-dot.open { background: var(--down-green); box-shadow: 0 0 6px rgba(34,197,94,0.4); }
.status-dot.closed { background: var(--gold); }
.status-dot.pre { background: var(--text-muted); }
.status-sep { color: var(--border); }
.current-time { color: var(--text-primary); font-family: var(--font-mono); font-size: 14px; }
</style>
