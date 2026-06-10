<template>
  <div class="strategy2-results">
    <h1>策略2 · 极致量干价稳</h1>
    <p class="subtitle">独立量价评估 — 不依赖杯柄/VCP形态识别</p>

    <!-- Task Selector -->
    <div class="task-bar">
      <select v-model="selectedTaskId" @change="loadCandidates">
        <option value="">-- 选择任务 --</option>
        <option v-for="t in tasks" :key="t.id" :value="t.id">
          {{ t.id }} ({{ t.status }}) · {{ t.candidates || 0 }} 候选
        </option>
      </select>
      <span class="task-status" v-if="selectedTaskId">状态: {{ selectedTask?.status || '--' }}</span>
    </div>

    <!-- Summary -->
    <div class="summary-bar" v-if="candidates.length">
      <span>候选数: <strong>{{ candidates.length }}</strong></span>
      <span v-for="lv in levels" :key="lv" class="level-chip" :class="levelClass(lv)">
        {{ lv }}: {{ countByLevel(lv) }}
      </span>
    </div>

    <!-- Empty State -->
    <div class="empty" v-if="!loading && !candidates.length">
      <p v-if="!selectedTaskId">请选择一个策略2任务查看候选结果。</p>
      <p v-else>当前策略2任务没有符合条件的候选。</p>
    </div>

    <!-- Candidates Table -->
    <table class="candidates-table" v-if="candidates.length">
      <thead>
        <tr>
          <th>股票</th>
          <th>总分</th>
          <th>等级</th>
          <th>量干分</th>
          <th>价稳分</th>
          <th>风险比</th>
          <th>风险等级</th>
          <th>支撑价</th>
          <th>买入区间</th>
          <th>止损价</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in candidates" :key="c.code"
            :class="{ 'golden': c.total_score >= 80 }">
          <td>
            <router-link :to="`/stock/${c.code}`">{{ c.code }}</router-link>
            <span class="name">{{ c.name }}</span>
          </td>
          <td class="score">{{ c.total_score }}</td>
          <td><span class="level-badge" :class="levelClass(c.level)">{{ c.level || '--' }}</span></td>
          <td>{{ c.volume_dry_score }}</td>
          <td>{{ c.price_stable_score }}</td>
          <td>{{ formatPct(c.risk_ratio) }}</td>
          <td>{{ c.risk_level }}</td>
          <td>{{ c.key_support?.toFixed(2) }}</td>
          <td>{{ c.buy_zone_low?.toFixed(2) }}~{{ c.buy_zone_high?.toFixed(2) }}</td>
          <td>{{ c.stop_loss?.toFixed(2) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="loading" v-if="loading">加载中...</div>
  </div>
</template>

<script>
import { useApi } from '../composables/useApi.js'

export default {
  name: 'Strategy2Results',
  data() {
    return {
      tasks: [],
      candidates: [],
      selectedTaskId: '',
      loading: false,
      levels: ['终极状态', '极致量干价稳', '重点观察', '普通观察'],
    }
  },
  computed: {
    selectedTask() {
      return this.tasks.find(t => t.id === this.selectedTaskId)
    },
  },
  async mounted() {
    const api = useApi()
    try {
      const res = await api.getStrategy2Tasks()
      this.tasks = res.tasks || []
    } catch (e) {
      console.error('Failed to load strategy2 tasks:', e)
    }
  },
  methods: {
    async loadCandidates() {
      if (!this.selectedTaskId) { this.candidates = []; return }
      this.loading = true
      try {
        const api = useApi()
        const res = await api.getStrategy2Candidates(this.selectedTaskId)
        this.candidates = res.candidates || []
      } catch (e) {
        console.error('Failed to load strategy2 candidates:', e)
      } finally {
        this.loading = false
      }
    },
    countByLevel(level) {
      return this.candidates.filter(c => c.level === level).length
    },
    levelClass(level) {
      if (!level) return ''
      if (level.includes('终极')) return 'level-ultimate'
      if (level.includes('极致')) return 'level-extreme'
      if (level.includes('重点')) return 'level-key'
      if (level.includes('普通')) return 'level-normal'
      return ''
    },
    formatPct(v) {
      if (v == null) return '--'
      return (v * 100).toFixed(2) + '%'
    },
  },
}
</script>

<style scoped>
.strategy2-results { padding: 24px; color: #e0e0e0; }
h1 { font-size: 1.5rem; margin-bottom: 4px; color: #ffd700; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 0.9rem; }
.task-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.task-bar select { background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; padding: 6px 12px; border-radius: 4px; }
.task-status { color: #aaa; font-size: 0.85rem; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.level-chip { font-size: 0.8rem; padding: 2px 8px; border-radius: 3px; }
.level-ultimate { background: #4a0000; color: #ff4444; }
.level-extreme { background: #4a3000; color: #ffaa00; }
.level-key { background: #1a3a1a; color: #66cc66; }
.level-normal { background: #1a1a3a; color: #6699cc; }
.empty { text-align: center; padding: 60px; color: #666; }
.candidates-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
.candidates-table th { background: #1a1a1a; color: #aaa; padding: 8px 10px; text-align: left; border-bottom: 1px solid #333; }
.candidates-table td { padding: 8px 10px; border-bottom: 1px solid #222; }
.candidates-table tr:hover { background: #1a1a1a; }
tr.golden { border-left: 3px solid #ffd700; }
.score { font-weight: bold; font-size: 1.1rem; }
.level-badge { padding: 2px 8px; border-radius: 3px; font-size: 0.8rem; }
.name { color: #888; margin-left: 8px; font-size: 0.8rem; }
.loading { text-align: center; padding: 40px; color: #666; }
</style>
