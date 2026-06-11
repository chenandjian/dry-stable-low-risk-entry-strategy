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
    <div class="summary-bar" v-if="candidates.length || failureCount > 0">
      <span v-if="candidates.length">候选数: <strong>{{ candidates.length }}</strong></span>
      <span v-for="lv in levels" :key="lv" class="level-chip" :class="levelClass(lv)">
        {{ lv }}: {{ countByLevel(lv) }}
      </span>
      <span v-if="failureCount > 0" class="failed-count">
        失败股票: <strong>{{ failureCount }}</strong>
        <router-link :to="`/?task=${selectedTaskId}&status=failed`" class="view-failures-link">查看失败股票</router-link>
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
          <th>量干</th>
          <th>价稳</th>
          <th>走势趋势</th>
          <th>风险比</th>
          <th>风险等级</th>
          <th>支撑</th>
          <th>止损</th>
          <th>详情</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="c in candidates" :key="c.code">
          <tr :class="{ 'golden': c.total_score >= 80, 'expanded': expandedCode === c.code }"
              @click="toggleDetail(c)">
            <td>
              <span class="code-link">{{ c.code }}</span>
              <span class="name">{{ c.name }}</span>
            </td>
            <td class="score">{{ c.total_score }}</td>
            <td><span class="level-badge" :class="levelClass(c.level)">{{ c.level || '--' }}</span></td>
            <td>{{ c.volume_dry_score }}</td>
            <td>{{ c.price_stable_score }}</td>
            <td><span class="trend-type">{{ trendLabel(c.trend_type) }}</span></td>
            <td>{{ formatPct(c.risk_ratio) }}</td>
            <td>{{ c.risk_level }}</td>
            <td>{{ c.key_support?.toFixed(2) }}</td>
            <td>{{ c.stop_loss?.toFixed(2) }}</td>
            <td class="expand-cell">{{ expandedCode === c.code ? '▾' : '▸' }}</td>
          </tr>
          <tr v-if="expandedCode === c.code" class="detail-row">
            <td colspan="11">
              <div class="detail-panel">
                <div class="detail-grid">
                  <div class="detail-section">
                    <h4>指标</h4>
                    <div>V3: {{ fmtNum(c.v3) }} &nbsp; V5: {{ fmtNum(c.v5) }} &nbsp; V10: {{ fmtNum(c.v10) }} &nbsp; V20: {{ fmtNum(c.v20) }}</div>
                    <div>V5/V20: {{ c.volume_ratio_5_20?.toFixed(3) }} &nbsp; 分位: {{ c.volume_percentile?.toFixed(1) }}% ({{ c.volume_percentile_days }}日)</div>
                    <div>range_5: {{ formatPct(c.range_5) }} &nbsp; close_range_5: {{ formatPct(c.close_range_5) }}</div>
                    <div>return_3: {{ formatPct(c.return_3) }} &nbsp; return_5: {{ formatPct(c.return_5) }}</div>
                  </div>
                  <div class="detail-section">
                    <h4>走势趋势 V2</h4>
                    <div>趋势: {{ trendLabel(c.trend_type) }}
                      &nbsp; 短中: {{ c.short_mid_score ?? '--' }}/8
                      &nbsp; 长期: {{ c.long_score ?? '--' }}/3
                      &nbsp; 总分: {{ c.total_evidence_score ?? '--' }}/11</div>
                    <div>MA20: {{ fmtPrice(c.ma20) }} &nbsp; MA60: {{ fmtPrice(c.ma60) }} &nbsp; MA120: {{ fmtPrice(c.ma120) }}</div>
                    <div>MA20斜率: {{ formatPct(c.ma20_slope) }} &nbsp; MA60斜率: {{ formatPct(c.ma60_slope) }}</div>
                    <div>60日高点回撤: {{ formatPct(c.drawdown_from_high_60) }} &nbsp; 120日高点回撤: {{ formatPct(c.drawdown_from_high_120) }}</div>
                    <div>20日中枢变化: {{ formatPct(c.center_shift_20) }} &nbsp; 40日中枢变化: {{ formatPct(c.center_shift_40) }}</div>
                    <div>60日区间位置: {{ fmtPosition(c.price_position_60) }} &nbsp; 60日线性趋势: {{ formatPct(c.linear_trend_60) }}</div>
                    <div v-if="c.downtrend_conditions?.length" class="muted">证据: {{ c.downtrend_conditions }}</div>
                  </div>
                  <div class="detail-section">
                    <h4>风险</h4>
                    <div>买入: {{ c.buy_zone_low?.toFixed(2) }} ~ {{ c.buy_zone_high?.toFixed(2) }}</div>
                    <div>止损: {{ c.stop_loss?.toFixed(2) }} &nbsp; 风险比: {{ formatPct(c.risk_ratio) }}</div>
                    <div>评估日: {{ c.evaluation_date }}</div>
                  </div>
                  <div class="detail-section">
                    <h4>评分原因</h4>
                    <div v-for="(r, i) in (c.score_reasons || [])" :key="'sr'+i" class="reason-line">✓ {{ r }}</div>
                    <div v-if="!c.score_reasons?.length" class="muted">无评分原因</div>
                  </div>
                  <div class="detail-section" v-if="c.reject_reasons?.length">
                    <h4>否决原因</h4>
                    <div v-for="(r, i) in (c.reject_reasons || [])" :key="'rr'+i" class="reason-line reject">✗ {{ r }}</div>
                  </div>
                </div>
              </div>
            </td>
          </tr>
        </template>
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
      expandedCode: null,
      failureCount: 0,
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
    // FINAL-S2-003: Auto-select task from query parameter
    const queryTaskId = this.$route.query.task
    if (queryTaskId && this.tasks.some(t => t.id === queryTaskId)) {
      this.selectedTaskId = queryTaskId
      await this.loadCandidates()
    }
  },
  methods: {
    async loadCandidates() {
      if (!this.selectedTaskId) { this.candidates = []; this.failureCount = 0; return }
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
      // ROUND2-S2-002: also load failure count
      try {
        const api = useApi()
        const data = await api.getTaskStocks(this.selectedTaskId, { status: 'failed', page_size: 1 })
        this.failureCount = data.total || 0
      } catch (e) { /* ignore */ }
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
    fmtPrice(v) {
      if (v == null) return '--'
      return Number(v).toFixed(2)
    },
    fmtPosition(v) {
      if (v == null) return '--'
      return (Number(v) * 100).toFixed(0) + '%'
    },
    trendLabel(v) {
      if (!v) return '--'
      if (v === 'UPTREND_OR_SIDEWAYS') return '上涨或横盘'
      if (v === 'DOWNTREND') return '下降趋势'
      return v
    },
    formatPct(v) {
      if (v == null) return '--'
      return (v * 100).toFixed(2) + '%'
    },
    fmtNum(v) {
      if (v == null) return '--'
      if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
      if (v >= 1e4) return (v / 1e4).toFixed(1) + '万'
      return v.toFixed(0)
    },
    toggleDetail(c) {
      this.expandedCode = this.expandedCode === c.code ? null : c.code
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
.code-link { color: var(--accent); font-family: var(--font-mono); cursor: pointer; }
.expand-cell { color: #666; font-size: 1.2rem; text-align: center; cursor: pointer; }
tr.expanded { background: #1a1a2e; }
tr.expanded .expand-cell { color: var(--accent); }
.detail-row td { padding: 0; }
.detail-panel { padding: 16px 20px; background: #111; border-top: 1px solid #333; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.detail-section h4 { font-size: 0.8rem; color: #888; margin-bottom: 6px; text-transform: uppercase; }
.detail-section div { font-size: 0.8rem; color: #ccc; line-height: 1.6; }
.reason-line { font-size: 0.8rem; color: #aa8; padding: 1px 0; }
.reason-line.reject { color: #e44; }
.muted { color: #666; }
.failed-count { color: #e88; font-size: 0.85rem; }
.view-failures-link { color: var(--accent); margin-left: 8px; cursor: pointer; font-size: 0.8rem; }
</style>
