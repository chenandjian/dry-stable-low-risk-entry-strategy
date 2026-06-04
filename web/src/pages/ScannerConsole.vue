<template>
  <div class="page-content">
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
          暂无候选发现 · 点击右上角"开始扫描"
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
        :logLines="logLines"
        @start="handleStartScan"
        @stop="handleStopScan"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import DiscoveryItem from '../components/DiscoveryItem.vue'
import ScanEngine from '../components/ScanEngine.vue'

const router = useRouter()
const { startScan, getScanStatus, getCandidates } = useApi()

const scanning = ref(false)
const scanError = ref('')
const scanProgress = reactive({ scanned: 0, total: 5128, currentCode: '--', currentName: '--', skipped: 0 })
const logLines = ref([])
const discoveries = ref([])
const metrics = reactive({ candidates: 0, aGrade: 0, breakout: 0, nearBreakout: 0, volumeOk: 0, topScore: 0 })

const topSignalSub = computed(() => discoveries.value.filter(d => d.score >= 80).map(d => d.name).slice(0, 3).join(' · ') || '--')
const topScoreSub = computed(() => {
  const top = discoveries.value.reduce((max, d) => d.score > max.score ? d : max, { score: 0, name: '--' })
  return top.name
})

let pollTimer = null

function goToStock(code) {
  router.push(`/stock/${code}`)
}

async function handleStartScan() {
  scanError.value = ''
  try {
    const res = await startScan()
    if (res.error) {
      const messages = {
        'Scan already running': '扫描已在运行中，请等待当前扫描完成',
      }
      scanError.value = messages[res.error] || res.error
      return
    }
    scanning.value = true
    pollTimer = setInterval(pollStatus, 1000)
  } catch (e) {
    scanError.value = '无法连接到后端服务，请确认 python main.py serve 已启动'
    console.error('Start scan failed:', e)
  }
}

async function handleStopScan() {
  scanning.value = false
  if (pollTimer) clearInterval(pollTimer)
}

async function pollStatus() {
  try {
    const status = await getScanStatus()
    if (!status.running && scanning.value) {
      scanning.value = false
      if (pollTimer) clearInterval(pollTimer)
      loadResults()
    }
    if (status.stats) {
      scanProgress.scanned = status.stats.scanned || 0
      scanProgress.total = status.stats.total_stocks || 5128
      scanProgress.skipped = status.stats.skipped || 0
      scanProgress.currentCode = status.stats.current_code || '--'
      scanProgress.currentName = status.stats.current_name || '--'
    }
    // 实时更新候选发现
    if (status.stats.discoveries) {
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
      updateMetrics()
    }
  } catch (e) {
    scanError.value = '状态查询失败'
    console.error(e)
  }
}

async function loadResults() {
  try {
    const data = await getCandidates()
    discoveries.value = (data.candidates || []).map(c => ({
      code: c.code,
      name: c.name,
      score: c.score,
      rating: c.score >= 80 ? 'strong' : c.score >= 70 ? 'medium' : 'weak',
      status: statusFor(c),
      detail: formatDetail(c),
    }))
    updateMetrics()
  } catch (e) {
    console.error('Load results failed:', e)
  }
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
  if (c.dry_stable_verdict === '可低吸') return 'near'
  if (c.dry_stable_verdict === '突破确认' || c.is_breakout) return 'breakout'
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
  await loadResults()
  // Check if a scan is already running
  try {
    const status = await getScanStatus()
    if (status.running) {
      scanning.value = true
      if (status.stats) {
        scanProgress.scanned = status.stats.scanned || 0
        scanProgress.total = status.stats.total_stocks || 5128
        scanProgress.currentCode = status.stats.current_code || '--'
        scanProgress.currentName = status.stats.current_name || '--'
      }
      pollTimer = setInterval(pollStatus, 1000)
    }
  } catch (e) { console.error('Check status on mount failed:', e) }
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
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
}
.error-banner {
  background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3);
  border-radius: 6px; padding: 12px 16px; margin-bottom: 12px;
  color: var(--up-red); font-size: 13px;
}
</style>
