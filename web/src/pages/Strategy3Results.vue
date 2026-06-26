<template>
  <div class="strategy3-results">
    <h1>策略3 · 强势回踩二次启动</h1>
    <p class="subtitle">先证明趋势强，再等待健康回踩，只在缩量企稳后二次转强时入选。</p>

    <div class="task-bar">
      <select v-model="selectedTaskId" @change="loadCandidates">
        <option value="">-- 选择策略3任务 --</option>
        <option v-for="t in tasks" :key="t.id" :value="t.id">
          {{ t.id }} ({{ t.status }}) · {{ t.candidates || 0 }} 候选
        </option>
      </select>
      <span class="task-status" v-if="selectedTaskId">状态: {{ selectedTask?.status || '--' }}</span>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="summary-bar" v-if="candidates.length || failureCount > 0">
      <span>候选数: <strong>{{ candidates.length }}</strong></span>
      <span class="level-chip core">核心候选: {{ countByLevel('核心候选') }}</span>
      <span class="level-chip watch">观察候选: {{ countByLevel('观察候选') }}</span>
      <span v-if="failureCount > 0" class="failed-count">
        失败股票: <strong>{{ failureCount }}</strong>
        <router-link :to="`/?task=${selectedTaskId}&status=failed`" class="view-failures-link">查看失败股票</router-link>
      </span>
    </div>

    <div class="empty" v-if="!loading && !candidates.length">
      <p v-if="!selectedTaskId">请选择一个策略3任务查看候选结果。</p>
      <p v-else>当前任务没有策略3候选。</p>
    </div>

    <table class="candidates-table" v-if="candidates.length">
      <thead>
        <tr>
          <th>股票</th>
          <th>总分</th>
          <th>等级</th>
          <th>趋势</th>
          <th>回踩</th>
          <th>缩量企稳</th>
          <th>二次转强</th>
          <th>风险收益</th>
          <th>回踩幅度</th>
          <th>战术风险比</th>
          <th>结构风险比</th>
          <th>RR1</th>
          <th>战术支撑/止损/目标</th>
          <th>评估日</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="c in sortedCandidates" :key="c.code">
          <tr :class="{ core: c.level === '核心候选', expanded: expandedCode === c.code }" @click="toggleDetail(c)">
            <td><span class="code-link">{{ c.code }}</span><span class="name">{{ c.name }}</span></td>
            <td class="score">{{ c.total_score }}</td>
            <td><span class="level-badge" :class="levelClass(c.level)">{{ c.level || '--' }}</span></td>
            <td>{{ c.trend_score ?? 0 }}</td>
            <td>{{ c.pullback_score ?? 0 }}</td>
            <td>{{ c.volume_stability_score ?? 0 }}</td>
            <td>{{ c.second_breakout_score ?? 0 }}</td>
            <td>{{ c.risk_reward_score ?? 0 }}</td>
            <td>{{ formatPct(c.pullback_pct) }}</td>
            <td>{{ formatPct(c.tactical_risk_ratio ?? c.risk_ratio) }}</td>
            <td>{{ formatPct(c.structural_risk_ratio) }}</td>
            <td>{{ fmtNum(c.rr1, 2) }}</td>
            <td>{{ fmtPrice(c.tactical_support ?? c.support_price) }} / {{ fmtPrice(c.tactical_stop_loss ?? c.stop_loss) }} / {{ fmtPrice(c.target_1) }}</td>
            <td>{{ c.evaluation_date || '--' }}</td>
          </tr>
          <tr v-if="expandedCode === c.code" class="detail-row">
            <td colspan="14">
              <div class="detail-panel">
                <div class="detail-grid">
                  <div>
                    <h4>趋势与回踩</h4>
                    <div>MA5/10/20/60/120：{{ fmtPrice(c.ma5) }} / {{ fmtPrice(c.ma10) }} / {{ fmtPrice(c.ma20) }} / {{ fmtPrice(c.ma60) }} / {{ fmtPrice(c.ma120) }}</div>
                    <div>近期高点：{{ fmtPrice(c.recent_high) }} · 相对强度60日：{{ formatPct(c.relative_strength_60) }}</div>
                    <div>最近5日振幅：{{ formatPct(c.range_5) }} · 收盘收窄：{{ formatPct(c.close_range_5) }}</div>
                  </div>
                  <div>
                    <h4>量能与风险</h4>
                    <div>V5/V20：{{ fmtNum(c.volume_ratio_5_20, 3) }}</div>
                    <div>战术支撑：{{ fmtPrice(c.tactical_support ?? c.support_price) }} · 战术止损：{{ fmtPrice(c.tactical_stop_loss ?? c.stop_loss) }} · 第一目标：{{ fmtPrice(c.target_1) }}</div>
                    <div>战术风险比：{{ formatPct(c.tactical_risk_ratio ?? c.risk_ratio) }} · 战术RR1：{{ fmtNum(c.tactical_rr1 ?? c.rr1, 2) }}</div>
                    <div>结构支撑：{{ fmtPrice(c.structural_support) }} · 结构止损：{{ fmtPrice(c.structural_stop_loss) }} · 结构风险比：{{ formatPct(c.structural_risk_ratio) }}</div>
                    <div>支撑口径：{{ c.support_quality || '--' }}</div>
                  </div>
                  <div>
                    <h4>支撑区 V2</h4>
                    <div>状态：{{ c.support_status || '--' }} · 跌破：{{ c.break_status || '--' }} · 距关键支撑：{{ formatPct(c.nearest_support_distance) }}</div>
                    <div>短线支撑区：{{ fmtSupportZone(c.short_support_zone_low, c.short_support, c.short_support_zone_high) }}</div>
                    <div>关键支撑区：{{ fmtSupportZone(c.key_support_zone_low, c.key_support, c.key_support_zone_high) }}</div>
                    <div>强支撑区：{{ fmtSupportZone(c.strong_support_zone_low, c.strong_support, c.strong_support_zone_high) }}</div>
                    <div>来源：{{ fmtList(c.support_sources) }}</div>
                  </div>
                  <div>
                    <h4>量干跌不动质量</h4>
                    <div>V3/5/10/20：{{ fmtNum(c.v3) }} / {{ fmtNum(c.v5) }} / {{ fmtNum(c.v10) }} / {{ fmtNum(c.v20) }}</div>
                    <div>V5/V20：{{ fmtNum(c.volume_ratio_5_20, 3) }} · 5日涨跌：{{ formatPct(c.return_5) }} · 不创新低：{{ fmtBool(c.no_new_low) }}</div>
                    <div>支撑价：{{ fmtPrice(c.support_price_10) }} · 支撑测试：{{ c.support_test_count ?? 0 }} 次 · 支撑有效：{{ fmtBool(c.support_valid) }}</div>
                    <div>阴线实体收缩：{{ fmtBool(c.bear_body_shrink) }} · 下影线：{{ c.lower_shadow_count ?? 0 }} 根 · 阴线量占比：{{ formatPct(c.down_volume_ratio_5) }}</div>
                    <div>ATR5/20：{{ fmtNum(c.atr_ratio_5_20, 3) }} · 放量下跌：{{ fmtBool(c.has_big_down_volume) }}</div>
                  </div>
                  <div>
                    <h4>评分原因</h4>
                    <div v-for="(r, i) in (c.score_reasons || [])" :key="'sr'+i" class="reason-line">✓ {{ r }}</div>
                    <div v-if="!c.score_reasons?.length" class="muted">无评分原因</div>
                  </div>
                  <div v-if="c.reject_reasons?.length">
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
  name: 'Strategy3Results',
  data() {
    return {
      tasks: [],
      candidates: [],
      selectedTaskId: '',
      loading: false,
      expandedCode: null,
      failureCount: 0,
      error: '',
    }
  },
  computed: {
    selectedTask() {
      return this.tasks.find(t => t.id === this.selectedTaskId)
    },
    sortedCandidates() {
      return [...this.candidates].sort((a, b) => (b.total_score || 0) - (a.total_score || 0))
    },
  },
  async mounted() {
    const api = useApi()
    try {
      const res = await api.getStrategy3Tasks()
      this.tasks = res.tasks || []
    } catch (e) {
      this.error = '策略3任务加载失败'
      console.error('Failed to load strategy3 tasks:', e)
    }
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
      this.error = ''
      const api = useApi()
      try {
        const res = await api.getStrategy3Candidates(this.selectedTaskId)
        this.candidates = res.candidates || []
      } catch (e) {
        this.error = '策略3候选加载失败'
        console.error('Failed to load strategy3 candidates:', e)
      } finally {
        this.loading = false
      }
      try {
        const data = await api.getTaskStocks(this.selectedTaskId, { status: 'failed', page_size: 1 })
        this.failureCount = data.total || 0
      } catch (e) { /* ignore failure count */ }
    },
    countByLevel(level) {
      return this.candidates.filter(c => c.level === level).length
    },
    levelClass(level) {
      if (level === '核心候选') return 'level-core'
      if (level === '观察候选') return 'level-watch'
      return ''
    },
    formatPct(v) {
      if (v == null) return '--'
      return (Number(v) * 100).toFixed(2) + '%'
    },
    fmtPrice(v) {
      if (v == null) return '--'
      return Number(v).toFixed(2)
    },
    fmtNum(v, digits = 0) {
      if (v == null) return '--'
      return Number(v).toFixed(digits)
    },
    fmtBool(v) {
      if (v === true || v === 1) return '是'
      if (v === false || v === 0) return '否'
      return '--'
    },
    fmtSupportZone(low, price, high) {
      if (low == null && price == null && high == null) return '--'
      return `${this.fmtPrice(low)} - ${this.fmtPrice(price)} - ${this.fmtPrice(high)}`
    },
    fmtList(v) {
      if (Array.isArray(v) && v.length) return v.join(', ')
      if (typeof v === 'string' && v) return v
      return '--'
    },
    toggleDetail(c) {
      this.expandedCode = this.expandedCode === c.code ? null : c.code
    },
  },
}
</script>

<style scoped>
.strategy3-results { padding: 24px; color: #e0e0e0; }
h1 { font-size: 1.5rem; margin-bottom: 4px; color: #d6b35a; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 0.9rem; }
.task-bar { display: flex; gap: 12px; align-items: center; margin-bottom: 16px; }
.task-bar select { background: #2a2a2a; color: #e0e0e0; border: 1px solid #444; padding: 6px 12px; border-radius: 4px; }
.task-status { color: #aaa; font-size: 0.85rem; }
.summary-bar { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.level-chip, .level-badge { font-size: 0.8rem; padding: 2px 8px; border-radius: 3px; }
.level-core, .core { background: rgba(214, 179, 90, 0.14); color: #d6b35a; }
.level-watch, .watch { background: rgba(80, 130, 220, 0.16); color: #8bb4ff; }
.empty { text-align: center; padding: 60px; color: #666; }
.error { background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #ff8888; padding: 10px 12px; border-radius: 4px; margin-bottom: 12px; }
.candidates-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
.candidates-table th { background: #1a1a1a; color: #aaa; padding: 8px 10px; text-align: left; border-bottom: 1px solid #333; }
.candidates-table td { padding: 8px 10px; border-bottom: 1px solid #222; }
.candidates-table tr:hover { background: #1a1a1a; }
tr.core { border-left: 3px solid #d6b35a; }
.score { font-weight: bold; font-size: 1rem; }
.name { color: #888; margin-left: 8px; font-size: 0.8rem; }
.code-link { color: var(--accent); font-family: var(--font-mono); cursor: pointer; }
.detail-row td { padding: 0; }
.detail-panel { padding: 16px 20px; background: #111; border-top: 1px solid #333; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.detail-grid h4 { font-size: 0.8rem; color: #888; margin-bottom: 6px; text-transform: uppercase; }
.detail-grid div { font-size: 0.8rem; color: #ccc; line-height: 1.6; }
.reason-line { color: #aa8; padding: 1px 0; }
.reason-line.reject { color: #e44; }
.muted { color: #666; }
.failed-count { color: #e88; font-size: 0.85rem; }
.view-failures-link { color: var(--accent); margin-left: 8px; cursor: pointer; font-size: 0.8rem; }
.loading { text-align: center; padding: 40px; color: #666; }
</style>
