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
        <span class="label">当前扫描</span>
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
      <button class="btn-primary" @click="$emit('start')" title="策略1: 杯柄/VCP形态识别">
        启动策略1扫描
      </button>
      <button class="btn-secondary" @click="$emit('startStrategy2')" title="策略2: 极致量干价稳">
        启动策略2扫描
      </button>
      <button class="btn-secondary strategy3" @click="$emit('startStrategy3')" title="策略3: 强势回踩二次启动">
        启动策略3扫描
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
  logLines: { type: Array, default: () => [] },
})
defineEmits(['start', 'startStrategy2', 'startStrategy3'])

const logExpanded = ref(true)
const progressPct = computed(() => props.total > 0 ? Math.round(props.scanned / props.total * 100) : 0)
const progressText = computed(() => {
  const total = props.total || 0
  const scanned = props.scanned || 0
  return `已处理 ${scanned} / ${total || '--'} · 剩余 ${Math.max(0, total - scanned)}只`
})
const statusText = computed(() => props.running ? '扫描任务进行中' : '')
const skipText = computed(() => `跳过 ${props.skipped || 0} · 失败 ${props.failed || 0} · 候选 ${props.candidates || 0}`)
const sourceText = computed(() => props.stockPoolSource ? `股票池 ${props.stockPoolSource}` : '股票池 --')
</script>

<style scoped>
.panel {
  background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden;
}
.panel-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: 0.5px;
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
.progress-bar { flex: 1; height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.progress-pct { font-family: var(--font-mono); font-size: 11px; color: var(--accent); min-width: 32px; text-align: right; }
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), #79A0FF); border-radius: 2px; transition: width 0.3s; }
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
  background: var(--accent); color: #fff; border: none;
  padding: 8px 20px; border-radius: 4px; font-size: 13px; font-weight: 600; cursor: pointer;
  transition: background 0.15s;
}
.btn-primary:hover { background: #3D6BEE; }
.btn-secondary {
  background: transparent; color: var(--text-secondary); border: 1px solid var(--border);
  padding: 6px 14px; border-radius: 4px; font-size: 12px; cursor: pointer;
}
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
.btn-secondary.strategy3 { color: #d6b35a; border-color: rgba(214,179,90,0.5); }
.btn-secondary.strategy3:hover { border-color: #d6b35a; color: #f0ca6a; }
</style>
