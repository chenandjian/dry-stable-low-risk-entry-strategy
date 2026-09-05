<template>
  <div class="panel">
    <div class="panel-header">
      <span>扫描引擎</span>
      <span class="status" :class="running ? 'running' : ''">
        {{ running ? '● 扫描中' : '○ 待机' }}
      </span>
    </div>

    <div v-if="running" class="scan-body">
      <div class="status-line">
        <div class="pulse"></div>
        <div class="info">
          <div class="title">{{ statusText }}</div>
          <div class="sub">{{ progressText }}</div>
        </div>
      </div>
      <div class="progress-row">
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
        </div>
        <span class="progress-pct">{{ progressPct }}%</span>
      </div>
      <div class="current-stock">
        <span class="label">{{ currentLabel }}</span>
        <span class="code">{{ currentCode }}</span>
        <span class="name">{{ currentName }}</span>
        <span class="speed">{{ skipText }}</span>
      </div>
      <div class="scan-meta">
        <span>{{ sourceText }}</span>
        <span>最新交易日 {{ latestTradeDate || '--' }}</span>
      </div>
    </div>

    <div class="panel-header sub">
      <span>扫描日志</span>
      <span class="toggle" @click="logExpanded = !logExpanded">{{ logExpanded ? '收起' : '展开' }}</span>
    </div>
    <div v-if="logExpanded" class="log-lines">
      <div v-for="(line, i) in logLines" :key="i" class="log-line">
        <span class="ts">{{ line.time }}</span>
        <span :class="line.type">{{ line.text }}</span>
      </div>
    </div>
    <div v-if="!running" class="scan-controls">
      <button class="btn-primary" @click="$emit('startStrategy6')" title="策略6: 强势VCP尾部候选池">
        启动策略6扫描
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
const props = defineProps({
  running: Boolean,
  scanned: Number,
  total: Number,
  currentCode: String,
  currentName: String,
  skipped: Number,
  failed: Number,
  candidates: Number,
  latestTradeDate: String,
  stockPoolSource: String,
  phase: String,
  dataProcessed: Number,
  dataTotal: Number,
  indexProcessed: Number,
  indexTotal: Number,
  logLines: { type: Array, default: () => [] },
})
defineEmits(['startStrategy6'])

const logExpanded = ref(true)
const isDataAcquisition = computed(() => props.phase === 'data_acquisition')
const isIndexAcquisition = computed(() => props.phase === 'index_acquisition')
const activeProcessed = computed(() => {
  if (isDataAcquisition.value) return props.dataProcessed || 0
  if (isIndexAcquisition.value) return props.indexProcessed || 0
  return props.scanned || 0
})
const activeTotal = computed(() => {
  if (isDataAcquisition.value) return props.dataTotal || 0
  if (isIndexAcquisition.value) return props.indexTotal || 0
  return props.total || 0
})
const progressPct = computed(() => activeTotal.value > 0
  ? Math.round(activeProcessed.value / activeTotal.value * 100)
  : 0)
const progressText = computed(() => {
  const total = activeTotal.value
  const processed = activeProcessed.value
  const action = isDataAcquisition.value ? '已拉取' : isIndexAcquisition.value ? '已更新' : '已处理'
  return `${action} ${processed} / ${total || '--'} · 剩余 ${Math.max(0, total - processed)}${isIndexAcquisition.value ? '个' : '只'}`
})
const statusText = computed(() => {
  if (!props.running) return ''
  if (isDataAcquisition.value) return 'TickFlow 批量行情拉取中'
  if (isIndexAcquisition.value) return 'TickFlow 宽基指数更新中'
  if (props.phase === 'preparing') return '扫描任务准备中'
  return '扫描任务进行中'
})
const currentLabel = computed(() => isDataAcquisition.value
  ? '当前拉取'
  : isIndexAcquisition.value ? '当前指数' : '当前扫描')
const skipText = computed(() => (isDataAcquisition.value || isIndexAcquisition.value)
  ? '完成后自动进入策略计算'
  : `跳过 ${props.skipped || 0} · 失败 ${props.failed || 0} · 候选 ${props.candidates || 0}`)
const sourceText = computed(() => props.stockPoolSource ? `股票池 ${props.stockPoolSource}` : '股票池 --')
</script>

<style scoped>
.panel {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 11px 16px; border-bottom: 1px solid var(--border);
  font-size: 11px; font-weight: 650; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.08em;
}
.panel-header.sub { text-transform: none; letter-spacing: 0; font-weight: 500; }
.status { font-size: 11px; color: var(--text-muted); }
.status.running { color: var(--warn-orange); }
.toggle { font-size: 10px; color: var(--accent); cursor: pointer; }
.scan-body { padding: 16px; }
.status-line { display: flex; align-items: center; gap: 12px; }
.pulse {
  width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
  background: var(--warn-orange); box-shadow: 0 0 8px rgba(249,115,22,0.3);
  animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
.title { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.sub { font-size: 12px; color: var(--text-muted); }
.progress-row { display: flex; align-items: center; gap: 10px; margin: 12px 0; }
.progress-bar { flex: 1; height: 3px; background: var(--border); overflow: hidden; }
.progress-pct { font-family: var(--font-mono); font-size: 11px; color: var(--accent); min-width: 32px; text-align: right; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--gold), var(--accent)); transition: width 0.3s; }
.current-stock { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.scan-meta { display: flex; justify-content: space-between; margin-top: 8px; font-size: 11px; color: var(--text-muted); }
.label { color: var(--text-muted); }
.code { color: var(--accent); font-family: var(--font-mono); }
.name { color: var(--text-primary); }
.speed { color: var(--text-muted); font-size: 12px; margin-left: auto; }
.log-lines { padding: 8px 0; max-height: 200px; overflow-y: auto; }
.log-line { padding: 3px 16px; font-family: var(--font-mono); font-size: 11px; color: var(--text-muted); }
.log-line .ts { color: #3A4A5E; margin-right: 8px; }
.log-line .found { color: var(--gold); }
.log-line .skip { color: var(--down-green); }
.log-line .error { color: var(--up-red); }
.scan-controls { padding: 10px 16px; display: flex; gap: 8px; }
.btn-primary {
  background: var(--accent); color: #fff; border: 1px solid var(--accent);
  padding: 8px 20px; border-radius: var(--radius-sm); font-size: 13px; font-weight: 600; cursor: pointer;
  transition: background 0.15s;
}
.btn-primary:hover { background: #3D6BEE; }
</style>
