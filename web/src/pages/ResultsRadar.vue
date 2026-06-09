<template>
  <div class="page-content">
    <!-- Summary -->
    <div class="metrics-row">
      <MetricCard label="总候选" :value="candidates.length" color="blue" />
      <MetricCard label="A级 ≥80" :value="aCount" color="gold" />
      <MetricCard label="可低吸" :value="lowBuyCount" color="gold" />
      <MetricCard label="突破确认" :value="confirmCount" color="red" />
      <MetricCard label="平均评分" :value="avgScore" />
      <MetricCard label="最高评分" :value="maxScore" color="gold" />
    </div>

    <!-- Task Selector -->
    <div class="task-selector-bar">
      <label class="ts-label">扫描任务</label>
      <select v-model="selectedTaskId" @change="onTaskChange" class="ts-select">
        <option :value="null">-- 选择任务 --</option>
        <option v-for="t in tasks" :key="t.id" :value="t.id">
          {{ t.date }} · {{ t.candidates || 0 }}候选 · {{ t.status || '--' }}
        </option>
      </select>
    </div>

    <!-- Toolbar -->
    <div class="panel" style="border-radius: 6px 6px 0 0;">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="count">{{ filteredCandidates.length }} 只</span>
          <span class="sep">|</span>
          <button v-for="f in filters" :key="f.key"
            class="chip" :class="{ active: activeFilter === f.key }"
            @click="activeFilter = f.key"
          >{{ f.label }}</button>
        </div>
        <div class="toolbar-right">
          <button class="btn-secondary" @click="exportCSV">导出 CSV</button>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="panel" style="border-radius: 0 0 6px 6px; border-top: none;">
      <div class="table-wrap">
        <table class="radar-table">
          <thead>
            <tr>
              <th style="width:4px"></th>
              <th @click="sortBy = 'code'" class="sortable">代码</th>
              <th @click="sortBy = 'name'" class="sortable">名称</th>
              <th @click="sortBy = 'score'" class="sortable center">形态评分</th>
              <th class="center">形态</th>
              <th class="center">干稳结论</th>
              <th class="center">量干/价稳</th>
              <th class="right">RR</th>
              <th class="center">仓位</th>
              <th class="center">大盘</th>
              <th class="center">突破状态</th>
              <th @click="sortBy = 'latest_close'" class="sortable right">最新价</th>
              <th @click="sortBy = 'pivot'" class="sortable right">Pivot</th>
              <th class="right">距Pivot</th>
              <th class="center">杯体回撤深度</th>
              <th class="center">柄部回撤幅度</th>
              <th class="center">杯体周期</th>
              <th class="center">量能状态</th>
              <th class="center">放量倍数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in filteredCandidates" :key="c.code"
              :class="{ selected: selectedCode === c.code }"
              @click="goToStock(c.code)"
            >
              <td><span class="row-bar" :class="barClass(c)"></span></td>
              <td class="code-cell">{{ c.code }}</td>
              <td class="name-cell">{{ c.name }}</td>
              <td class="center">
                <span class="score-num" :class="scoreColorClass(c.score)">{{ c.score }}</span>
              </td>
              <td class="center">{{ c.pattern_type || '--' }}<span class="vcp-tag" v-if="c.vcp_contractions"> VCP{{ c.vcp_contractions }}T</span></td>
              <td class="center">
                <SignalBadge :type="verdictType(c)">
                  {{ c.dry_stable_verdict || c.rating || '观察' }}
                </SignalBadge>
              </td>
              <td class="center">{{ c.volume_dry_score ?? '--' }}/{{ c.price_stable_score ?? '--' }}</td>
              <td class="num blue">{{ c.rr1 != null ? Number(c.rr1).toFixed(1) : '--' }}</td>
              <td class="center">{{ c.position_advice || '--' }}</td>
              <td class="center" :class="marketClass(c.market_status)">{{ c.market_status || '一般' }}</td>
              <td class="center">
                <span :class="c.is_breakout ? 'st-breakout' : c.score >= 70 ? 'st-near' : 'st-watch'">
                  {{ c.is_breakout ? '◉ 已突破' : c.score >= 70 ? '● 接近突破' : '○ 观察' }}
                </span>
              </td>
              <td class="num">{{ c.latest_close?.toFixed(2) || '--' }}</td>
              <td class="num muted">{{ price(c.pivot || c.breakout_price) }}</td>
              <td class="num" :class="distClass(c)">{{ distPct(c) }}</td>
              <td class="center">{{ c.cup_depth_pct != null ? c.cup_depth_pct.toFixed(1) + '%' : '--' }}</td>
              <td class="center" :class="c.handle_depth_pct < 8 ? 'green' : c.handle_depth_pct > 12 ? 'red' : ''">
                {{ c.handle_depth_pct != null ? c.handle_depth_pct.toFixed(1) + '%' : '--' }}
              </td>
              <td class="num muted">{{ c.cup_duration }}</td>
              <td class="center">
                <SignalBadge :type="c.is_volume_breakout ? 'volume' : c.vol_multiplier >= 1 ? 'medium' : 'weak'">
                  {{ c.is_volume_breakout ? '放量确认' : c.vol_multiplier >= 1 ? '正常' : '不足' }}
                </SignalBadge>
              </td>
              <td class="num" :class="c.vol_multiplier >= 1.5 ? 'red' : ''">
                {{ c.vol_multiplier != null ? c.vol_multiplier.toFixed(1) + '×' : '--' }}
              </td>
            </tr>
            <tr v-if="filteredCandidates.length === 0">
              <td colspan="19" class="empty-row">无符合条件的候选</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import SignalBadge from '../components/SignalBadge.vue'

const router = useRouter()
const route = useRoute()
const { getCandidates, getScanTasks } = useApi()

const candidates = ref([])
const tasks = ref([])
const selectedTaskId = ref(null)
const selectedCode = ref('')
const activeFilter = ref('all')
const sortBy = ref('score')

const filters = [
  { key: 'all', label: '全部' },
  { key: 'aGrade', label: 'A级 ≥80' },
  { key: 'medium', label: '中等 70-79' },
  { key: 'lowBuy', label: '可低吸' },
  { key: 'confirm', label: '突破确认' },
  { key: 'breakout', label: '已突破' },
  { key: 'near', label: '接近突破' },
  { key: 'volume', label: '放量确认' },
]

const filteredCandidates = computed(() => {
  let list = [...candidates.value]
  if (activeFilter.value === 'aGrade') list = list.filter(c => c.score >= 80)
  else if (activeFilter.value === 'medium') list = list.filter(c => c.score >= 70 && c.score < 80)
  else if (activeFilter.value === 'lowBuy') list = list.filter(c => c.dry_stable_verdict === '可低吸')
  else if (activeFilter.value === 'confirm') list = list.filter(c => c.dry_stable_verdict === '突破确认')
  else if (activeFilter.value === 'breakout') list = list.filter(c => c.is_breakout)
  else if (activeFilter.value === 'near') list = list.filter(c => !c.is_breakout && c.score >= 70)
  else if (activeFilter.value === 'volume') list = list.filter(c => c.is_volume_breakout)

  list.sort((a, b) => {
    const field = sortBy.value
    const va = a[field]
    const vb = b[field]
    if (typeof va === 'string') return va.localeCompare(vb)
    return (vb || 0) - (va || 0)
  })
  return list
})

const aCount = computed(() => candidates.value.filter(c => c.score >= 80).length)
const lowBuyCount = computed(() => candidates.value.filter(c => c.dry_stable_verdict === '可低吸').length)
const confirmCount = computed(() => candidates.value.filter(c => c.dry_stable_verdict === '突破确认').length)
const avgScore = computed(() => {
  if (!candidates.value.length) return 0
  return Math.round(candidates.value.reduce((s, c) => s + c.score, 0) / candidates.value.length)
})
const maxScore = computed(() => candidates.value.reduce((m, c) => Math.max(m, c.score), 0))

function goToStock(code) {
  selectedCode.value = code
  const q = selectedTaskId.value ? `?task_id=${selectedTaskId.value}` : ''
  router.push(`/stock/${code}${q}`)
}
function barClass(c) { return c.score >= 80 ? 'bar-gold' : c.score >= 70 ? 'bar-blue' : 'bar-gray' }
function scoreColorClass(s) { return s >= 80 ? 'sc-gold' : s >= 70 ? 'sc-blue' : 'sc-muted' }
function price(v) { return v ? Number(v).toFixed(2) : '--' }
function verdictType(c) {
  const vk = c.verdict_key || ''
  if (vk === 'BUY_LOW' || c.dry_stable_verdict === '可低吸') return 'strong'
  if (vk === 'WATCH_BREAKOUT' || c.dry_stable_verdict === '突破确认') return 'confirm'
  if (vk.startsWith('WAIT_')) return 'wait'
  if (vk === 'REJECT' || c.dry_stable_verdict === '不建议买入') return 'weak'
  if (c.is_breakout) return 'breakout'
  return c.score >= 70 ? 'medium' : 'weak'
}
function marketClass(s) {
  if (s === '良好') return 'red'
  if (s === '较差') return 'green'
  return 'orange'
}
function distPct(c) {
  const pivot = c.pivot || c.breakout_price
  if (!pivot || !c.latest_close) return '--'
  return ((c.latest_close - pivot) / pivot * 100).toFixed(1) + '%'
}
function distClass(c) {
  const pivot = c.pivot || c.breakout_price
  if (!pivot || !c.latest_close) return ''
  const d = (c.latest_close - pivot) / pivot
  return d > 0 ? 'red' : d > -0.05 ? 'orange' : 'muted'
}
function exportCSV() {
  const header = '代码,名称,评分,形态,干稳结论,量干,价稳,RR,仓位,大盘,突破,放量,最新价,Pivot,杯体深度,柄部回撤,杯体天数,放量倍数'
  const rows = candidates.value.map(c => [
    c.code, c.name, c.score,
    c.pattern_type || '',
    c.dry_stable_verdict || '',
    c.volume_dry_score ?? '',
    c.price_stable_score ?? '',
    c.rr1 ?? '',
    c.position_advice || '',
    c.market_status || '',
    c.is_breakout ? '是' : '否',
    c.is_volume_breakout ? '是' : '否',
    c.latest_close?.toFixed(2) || '',
    (c.pivot || c.breakout_price)?.toFixed?.(2) || '',
    c.cup_depth_pct?.toFixed(1) || '',
    c.handle_depth_pct?.toFixed(1) || '',
    c.cup_duration || '',
    c.vol_multiplier?.toFixed(1) || '',
  ].join(','))
  const blob = new Blob(['﻿' + [header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'candidates.csv'; a.click()
  URL.revokeObjectURL(url)
}

// 加载任务列表
async function loadTasks() {
  try {
    const data = await getScanTasks()
    tasks.value = (data.tasks || []).filter(t => !t.running)
    // Prefer task_id from query param, then fall back to latest completed
    const queryTaskId = route.query.task_id
    if (queryTaskId) {
      const match = tasks.value.find(t => t.id === queryTaskId)
      if (match) selectedTaskId.value = match.id
    }
    if (!selectedTaskId.value && tasks.value.length) {
      const completed = tasks.value.find(t => t.status === 'completed')
      if (completed) selectedTaskId.value = completed.id
    }
    if (selectedTaskId.value) await loadCandidates()
  } catch (e) { console.error('Failed to load tasks:', e) }
}

// 任务切换时重新加载候选
async function onTaskChange() {
  await loadCandidates()
}

// 加载候选列表
async function loadCandidates() {
  try {
    const params = selectedTaskId.value ? { task_id: selectedTaskId.value } : {}
    const data = await getCandidates(params)
    candidates.value = data.candidates || []
  } catch (e) {
    console.error('Failed to load candidates:', e)
  }
}

onMounted(async () => {
  await loadTasks()
})
</script>

<style scoped>
.task-selector-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 16px; background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 6px; margin-bottom: 12px;
}
.ts-label { font-size: 13px; color: var(--text-muted); white-space: nowrap; }
.ts-select {
  flex: 1; max-width: 400px;
  padding: 6px 10px; border-radius: 4px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary); font-size: 13px;
}
.page-content { padding: 20px 24px; max-width: 1600px; margin: 0 auto; }
.metrics-row {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 16px;
}
.panel { background: var(--bg-panel); border: 1px solid var(--border); overflow: hidden; }
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 8px; }
.count { font-size: 12px; color: var(--text-muted); }
.sep { color: var(--border-light); font-size: 12px; }
.chip {
  font-size: 12px; padding: 4px 12px; border-radius: 4px;
  border: 1px solid var(--border); background: transparent; color: var(--text-secondary); cursor: pointer;
  font-weight: 500; transition: all 0.15s;
}
.chip:hover { border-color: var(--accent); color: var(--text-primary); }
.chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-secondary {
  background: transparent; color: var(--text-secondary); border: 1px solid var(--border);
  padding: 6px 14px; border-radius: 4px; font-size: 12px; cursor: pointer;
}
.btn-secondary:hover { border-color: var(--accent); color: var(--accent); }
.table-wrap { overflow-x: auto; }
.radar-table { width: 100%; border-collapse: collapse; min-width: 1200px; }
.radar-table th {
  padding: 10px 14px; font-size: 12px; font-weight: 500; color: var(--text-muted);
  border-bottom: 2px solid var(--border-light); white-space: nowrap; text-align: left;
}
.radar-table th.center { text-align: center; }
.radar-table th.right { text-align: right; }
.radar-table th.sortable { cursor: pointer; user-select: none; }
.radar-table th.sortable:hover { color: var(--text-secondary); }
.radar-table td {
  padding: 12px 14px; font-size: 13px; border-bottom: 1px solid rgba(31,42,58,0.4); white-space: nowrap;
}
.radar-table tbody tr { cursor: pointer; transition: background 0.1s; }
.radar-table tbody tr:hover { background: rgba(79,125,255,0.04); }
.radar-table tbody tr.selected { background: rgba(79,125,255,0.08); }
.code-cell { font-family: var(--font-mono); color: var(--accent); font-weight: 600; }
.name-cell { color: var(--text-primary); }
.num { font-family: var(--font-mono); text-align: right; }
.center { text-align: center; }
.muted { color: var(--text-muted); }
.red { color: var(--up-red); }
.blue { color: var(--accent); }
.orange { color: var(--warn-orange); }
.green { color: var(--down-green); }
.score-num { font-size: 16px; font-weight: 700; font-family: var(--font-mono); }
.sc-gold { color: var(--gold); }
.sc-blue { color: var(--text-primary); }
.sc-muted { color: var(--text-muted); }
.st-breakout { color: var(--up-red); font-weight: 600; }
.st-near { color: var(--warn-orange); font-weight: 600; }
.st-watch { color: var(--text-muted); }
.row-bar { display: inline-block; width: 3px; height: 24px; border-radius: 2px; vertical-align: middle; margin-right: 10px; }
.bar-gold { background: var(--gold); }
.bar-blue { background: var(--accent); }
.bar-gray { background: var(--text-muted); }
.empty-row { text-align: center; padding: 40px; color: var(--text-muted); }
.vcp-tag { font-size: 10px; color: var(--accent); font-weight: 600; }
</style>
