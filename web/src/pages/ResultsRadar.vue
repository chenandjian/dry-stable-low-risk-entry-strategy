<template>
  <div class="page-content">
    <!-- Summary -->
    <div class="metrics-row">
      <MetricCard label="总候选" :value="candidates.length" color="blue" />
      <MetricCard label="A级 ≥80" :value="aCount" color="gold" />
      <MetricCard label="已突破" :value="breakoutCount" color="red" />
      <MetricCard label="接近突破" :value="nearCount" color="orange" />
      <MetricCard label="平均评分" :value="avgScore" />
      <MetricCard label="最高评分" :value="maxScore" color="gold" />
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
              <th class="center">信号等级</th>
              <th class="center">突破状态</th>
              <th @click="sortBy = 'latest_close'" class="sortable right">最新价</th>
              <th @click="sortBy = 'breakout_price'" class="sortable right">突破位</th>
              <th class="right">距突破位</th>
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
              <td class="center">
                <SignalBadge :type="c.score >= 80 ? 'strong' : c.score >= 70 ? 'medium' : 'weak'">
                  {{ c.score >= 80 ? '强候选' : c.score >= 70 ? '中等候选' : '弱候选' }}
                </SignalBadge>
              </td>
              <td class="center">
                <span :class="c.is_breakout ? 'st-breakout' : c.score >= 70 ? 'st-near' : 'st-watch'">
                  {{ c.is_breakout ? '◉ 已突破' : c.score >= 70 ? '● 接近突破' : '○ 观察' }}
                </span>
              </td>
              <td class="num">{{ c.latest_close?.toFixed(2) || '--' }}</td>
              <td class="num muted">{{ c.breakout_price?.toFixed(2) || '--' }}</td>
              <td class="num" :class="distClass(c)">{{ distPct(c) }}</td>
              <td class="center">{{ c.cup_depth_pct?.toFixed(1) }}%</td>
              <td class="center" :class="c.handle_depth_pct < 8 ? 'green' : c.handle_depth_pct > 12 ? 'red' : ''">
                {{ c.handle_depth_pct?.toFixed(1) }}%
              </td>
              <td class="num muted">{{ c.cup_duration }}</td>
              <td class="center">
                <SignalBadge :type="c.is_volume_breakout ? 'volume' : c.vol_multiplier >= 1 ? 'medium' : 'weak'">
                  {{ c.is_volume_breakout ? '放量确认' : c.vol_multiplier >= 1 ? '正常' : '不足' }}
                </SignalBadge>
              </td>
              <td class="num" :class="c.vol_multiplier >= 1.5 ? 'red' : ''">
                {{ c.vol_multiplier?.toFixed(1) }}×
              </td>
            </tr>
            <tr v-if="filteredCandidates.length === 0">
              <td colspan="14" class="empty-row">无符合条件的候选</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'
import MetricCard from '../components/MetricCard.vue'
import SignalBadge from '../components/SignalBadge.vue'

const router = useRouter()
const { getCandidates } = useApi()

const candidates = ref([])
const selectedCode = ref('')
const activeFilter = ref('all')
const sortBy = ref('score')

const filters = [
  { key: 'all', label: '全部' },
  { key: 'aGrade', label: 'A级 ≥80' },
  { key: 'medium', label: '中等 70-79' },
  { key: 'breakout', label: '已突破' },
  { key: 'near', label: '接近突破' },
  { key: 'volume', label: '放量确认' },
]

const filteredCandidates = computed(() => {
  let list = [...candidates.value]
  if (activeFilter.value === 'aGrade') list = list.filter(c => c.score >= 80)
  else if (activeFilter.value === 'medium') list = list.filter(c => c.score >= 70 && c.score < 80)
  else if (activeFilter.value === 'breakout') list = list.filter(c => c.is_breakout)
  else if (activeFilter.value === 'near') list = list.filter(c => !c.is_breakout && c.score >= 70)
  else if (activeFilter.value === 'volume') list = list.filter(c => c.is_volume_breakout)

  list.sort((a, b) => {
    if (sortBy.value === 'score') return b.score - a.score
    return (b[sortBy.value] || 0) - (a[sortBy.value] || 0)
  })
  return list
})

const aCount = computed(() => candidates.value.filter(c => c.score >= 80).length)
const breakoutCount = computed(() => candidates.value.filter(c => c.is_breakout).length)
const nearCount = computed(() => candidates.value.filter(c => !c.is_breakout && c.score >= 70).length)
const avgScore = computed(() => {
  if (!candidates.value.length) return 0
  return Math.round(candidates.value.reduce((s, c) => s + c.score, 0) / candidates.value.length)
})
const maxScore = computed(() => candidates.value.reduce((m, c) => Math.max(m, c.score), 0))

function goToStock(code) { selectedCode.value = code; router.push(`/stock/${code}`) }
function barClass(c) { return c.score >= 80 ? 'bar-gold' : c.score >= 70 ? 'bar-blue' : 'bar-gray' }
function scoreColorClass(s) { return s >= 80 ? 'sc-gold' : s >= 70 ? 'sc-blue' : 'sc-muted' }
function distPct(c) {
  if (!c.breakout_price || !c.latest_close) return '--'
  return ((c.latest_close - c.breakout_price) / c.breakout_price * 100).toFixed(1) + '%'
}
function distClass(c) {
  if (!c.breakout_price || !c.latest_close) return ''
  const d = (c.latest_close - c.breakout_price) / c.breakout_price
  return d > 0 ? 'red' : d > -0.05 ? 'orange' : 'muted'
}
function exportCSV() { window.open('/api/candidates?format=csv') }

onMounted(async () => {
  const data = await getCandidates()
  candidates.value = data.candidates || []
})
</script>

<style scoped>
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
</style>
