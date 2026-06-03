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
  scanning.value = true
  try {
    const res = await startScan()
    pollTimer = setInterval(pollStatus, 1000)
  } catch (e) {
    scanning.value = false
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
    }
  } catch (e) {
    // ignore
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
      status: c.is_breakout ? 'breakout' : c.score >= 70 ? 'near' : 'watch',
      detail: formatDetail(c),
    }))
    updateMetrics()
  } catch (e) {
    // ignore
  }
}

function formatDetail(c) {
  const parts = []
  if (c.cup_duration) parts.push(`杯体${c.cup_duration}d`)
  if (c.cup_depth_pct) parts.push(`回撤${c.cup_depth_pct}%`)
  if (c.vol_multiplier) parts.push(`放量${c.vol_multiplier}×`)
  return parts.join(' · ') || '--'
}

function updateMetrics() {
  const list = discoveries.value
  metrics.candidates = list.length
  metrics.aGrade = list.filter(d => d.score >= 80).length
  metrics.breakout = list.filter(d => d.status === 'breakout').length
  metrics.nearBreakout = list.filter(d => d.status === 'near').length
  metrics.volumeOk = list.filter(d => d.score >= 70).length
  metrics.topScore = list.reduce((max, d) => Math.max(max, d.score), 0)
}

onMounted(loadResults)
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
</style>
