<template>
  <div class="strategy5-results">
    <div class="page-header">
      <div>
        <h1>策略5 · 短线强势冲刺盘整支撑</h1>
        <p>寻找已经短线转强、接近阶段新高，并仍贴近 MA 支撑的重点/观察候选。</p>
      </div>
      <select v-model="selectedTaskId" @change="loadCandidates">
        <option value="">选择策略5任务</option>
        <option v-for="task in tasks" :key="task.id" :value="task.id">
          {{ task.id }} · {{ task.status }} · {{ task.candidates || 0 }} 候选
        </option>
      </select>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="summary-bar" v-if="candidates.length">
      <span>候选数 <strong>{{ candidates.length }}</strong></span>
      <span class="chip key">重点 {{ keyCandidates.length }}</span>
      <span class="chip watch">观察 {{ watchCandidates.length }}</span>
      <span>最高分 {{ topScore }}</span>
    </div>

    <div class="empty" v-if="!loading && !selectedTaskId">请选择一个策略5任务查看结果。</div>
    <div class="empty" v-else-if="!loading && selectedTaskId && !candidates.length">当前任务没有策略5候选。</div>

    <section v-for="group in candidateGroups" :key="group.type" class="panel">
      <div class="panel-header">{{ group.title }}</div>
      <div class="table-scroll">
        <table class="candidate-table">
          <thead>
            <tr>
              <th>股票</th><th>收盘</th><th>总分</th><th>分类</th><th>支撑状态</th><th>主支撑</th>
              <th>支撑距</th><th>支撑分</th><th>量干</th><th>强度触发</th><th>新高触发</th><th>20/50日涨幅</th>
              <th>5/10日振幅</th><th>60日成交额</th><th>风险/警告</th><th>数据日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in group.items" :key="c.code" class="clickable" @click="selected = c">
              <td><span class="code">{{ c.code }}</span> {{ c.name }}</td>
              <td>{{ fmt(c.close) }}</td>
              <td class="score">{{ fmt(c.total_score) }}</td>
              <td><span class="type-badge" :class="c.classification">{{ c.candidate_type }}</span></td>
              <td>{{ c.support_status }}</td>
              <td>{{ c.main_support_ma || '--' }}</td>
              <td>{{ pct(c.main_support_distance) }}</td>
              <td>{{ c.support_score ?? 0 }}</td>
              <td><span class="dry-badge" :class="dryClass(c.volume_dry_level)">{{ dryText(c) }}</span></td>
              <td>{{ c.strength_trigger || '--' }}</td>
              <td>{{ c.high_trigger || '--' }}</td>
              <td>{{ pct(c.recent_20d_return) }} / {{ pct(c.recent_50d_return) }}</td>
              <td>{{ pct(c.amplitude_5d) }} / {{ pct(c.amplitude_10d) }}</td>
              <td>{{ fmt(c.avg_turnover_60d) }}</td>
              <td>
                <span v-for="tag in c.risk_tags || []" :key="'r'+tag" class="tag risk">{{ tag }}</span>
                <span v-for="tag in c.warn_tags || []" :key="'w'+tag" class="tag warn">{{ tag }}</span>
              </td>
              <td>{{ c.kline_latest_date || c.evaluation_date || '--' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="selected" class="panel detail-panel">
      <div class="panel-header">候选详情 · {{ selected.code }} {{ selected.name }}</div>
      <div class="detail-grid">
        <div><span>分类</span><strong>{{ selected.candidate_type }} / {{ selected.classification }}</strong></div>
        <div><span>支撑</span><strong>{{ selected.support_status }} · {{ selected.main_support_ma }} · {{ selected.support_score }}</strong></div>
        <div><span>触发</span><strong>{{ selected.strength_trigger || '--' }} / {{ selected.high_trigger || '--' }}</strong></div>
        <div><span>量干</span><strong>{{ dryText(selected) }}</strong></div>
        <div><span>量比</span><strong>V5/V20 {{ fmt(selected.volume_ratio_5_20, 3) }} · V5/V50 {{ fmt(selected.volume_ratio_5_50, 3) }}</strong></div>
        <div><span>近期涨幅</span><strong>{{ pct(selected.recent_5d_return) }} / {{ pct(selected.recent_10d_return) }} / {{ pct(selected.recent_20d_return) }} / {{ pct(selected.recent_50d_return) }}</strong></div>
        <div><span>振幅</span><strong>{{ pct(selected.amplitude_5d) }} / {{ pct(selected.amplitude_10d) }}</strong></div>
        <div><span>20日回撤</span><strong>{{ pct(selected.drawdown_from_20d_high) }}</strong></div>
        <div><span>新高比例</span><strong>{{ fmt(selected.near_120d_high_ratio, 3) }}</strong></div>
        <div><span>数据</span><strong>{{ selected.data_source || '--' }} · {{ selected.kline_latest_date || selected.evaluation_date || '--' }}</strong></div>
      </div>
      <div class="tags">
        <span v-for="tag in selected.risk_tags || []" :key="'r' + tag" class="tag risk">{{ tag }}</span>
        <span v-for="tag in selected.warn_tags || []" :key="'w' + tag" class="tag warn">{{ tag }}</span>
        <span v-for="tag in selected.volume_dry_reasons || []" :key="'dr' + tag" class="tag dry">{{ tag }}</span>
        <span v-for="tag in selected.volume_dry_warnings || []" :key="'dw' + tag" class="tag warn">{{ tag }}</span>
        <span v-for="tag in selected.volume_dry_rejects || []" :key="'dx' + tag" class="tag risk">{{ tag }}</span>
      </div>
    </section>

    <div class="loading" v-if="loading">加载中...</div>
  </div>
</template>

<script>
import { useApi } from '../composables/useApi.js'

export default {
  name: 'Strategy5Results',
  data() {
    return {
      tasks: [],
      candidates: [],
      selectedTaskId: '',
      selected: null,
      loading: false,
      error: '',
    }
  },
  computed: {
    sortedCandidates() {
      return [...this.candidates].sort((a, b) => (b.total_score || 0) - (a.total_score || 0))
    },
    keyCandidates() {
      return this.sortedCandidates.filter(c => c.candidate_type === 'KEY_CANDIDATE')
    },
    watchCandidates() {
      return this.sortedCandidates.filter(c => c.candidate_type === 'WATCH_CANDIDATE')
    },
    candidateGroups() {
      return [
        { type: 'KEY_CANDIDATE', title: '重点候选 KEY_CANDIDATE', items: this.keyCandidates },
        { type: 'WATCH_CANDIDATE', title: '观察候选 WATCH_CANDIDATE', items: this.watchCandidates },
      ].filter(group => group.items.length)
    },
    topScore() {
      return this.sortedCandidates[0]?.total_score ?? '--'
    },
  },
  async mounted() {
    const api = useApi()
    try {
      const res = await api.getStrategy5Tasks()
      this.tasks = res.tasks || []
    } catch (e) {
      this.error = '策略5任务加载失败'
    }
    const queryTaskId = this.$route?.query?.task || new URLSearchParams(window.location.search).get('task')
    const defaultTaskId = queryTaskId || (this.tasks.length === 1 ? this.tasks[0].id : '')
    if (defaultTaskId) {
      if (!this.tasks.some(t => t.id === defaultTaskId)) {
        this.tasks = [{ id: defaultTaskId, status: 'selected', candidates: 0 }, ...this.tasks]
      }
      this.selectedTaskId = defaultTaskId
      await this.loadCandidates()
    }
  },
  methods: {
    async loadCandidates() {
      if (!this.selectedTaskId) {
        this.candidates = []
        this.selected = null
        return
      }
      this.loading = true
      this.error = ''
      const api = useApi()
      try {
        const res = await api.getStrategy5Candidates(this.selectedTaskId)
        this.candidates = res.candidates || []
        this.selected = this.candidates[0] || null
      } catch (e) {
        this.error = '策略5候选加载失败'
      } finally {
        this.loading = false
      }
    },
    pct(v) {
      if (v == null) return '--'
      return `${(Number(v) * 100).toFixed(2)}%`
    },
    fmt(v, digits = 2) {
      if (v == null) return '--'
      return Number(v).toFixed(digits)
    },
    dryText(c) {
      if (c?.volume_dry_score == null && !c?.volume_dry_level) return '--'
      return `${c.volume_dry_score ?? 0} / ${c.volume_dry_level || '--'}`
    },
    dryClass(level) {
      if (level === 'EXTREME_DRY' || level === 'HEALTHY_DRY') return 'good'
      if (level === 'WATCH_DRY') return 'watch'
      if (level === 'BAD_DRY') return 'bad'
      return ''
    },
  },
}
</script>

<style scoped>
.strategy5-results { padding: 20px; color: var(--text-primary); }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
h1 { margin: 0 0 6px; font-size: 22px; }
p { margin: 0; color: var(--text-secondary); }
select { background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px; min-width: 320px; }
.summary-bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; color: var(--text-secondary); }
.chip, .type-badge, .tag, .dry-badge { border-radius: 999px; padding: 2px 8px; font-size: 12px; display: inline-block; margin: 1px 3px 1px 0; }
.chip.key, .type-badge.highlight { background: rgba(34, 197, 94, 0.15); color: #86efac; }
.chip.watch, .type-badge.observe { background: rgba(234, 179, 8, 0.15); color: #fde68a; }
.dry-badge.good, .tag.dry { background: rgba(34, 197, 94, 0.15); color: #86efac; }
.dry-badge.watch { background: rgba(234, 179, 8, 0.15); color: #fde68a; }
.dry-badge.bad { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; margin: 14px 0; overflow: hidden; }
.panel-header { padding: 12px 14px; border-bottom: 1px solid var(--border); font-weight: 700; color: var(--text-secondary); }
.candidate-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.table-scroll { overflow-x: auto; }
.candidate-table { min-width: 1320px; }
th, td { border-bottom: 1px solid var(--border); padding: 9px 10px; text-align: left; }
th { color: var(--text-secondary); font-weight: 600; }
td { vertical-align: top; }
.clickable { cursor: pointer; }
.clickable:hover { background: rgba(255,255,255,0.03); }
.code { color: var(--accent); font-family: var(--font-mono); }
.score { color: var(--gold); font-weight: 700; }
.tag.risk { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
.tag.warn { background: rgba(249, 115, 22, 0.16); color: #fdba74; }
.detail-panel { padding-bottom: 12px; }
.detail-grid { padding: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; }
.detail-grid div { display: flex; flex-direction: column; gap: 3px; }
.detail-grid span { color: var(--text-secondary); font-size: 12px; }
.detail-grid strong { color: var(--text-primary); }
.tags { padding: 0 14px; }
.empty, .loading, .error-banner { padding: 16px; color: var(--text-secondary); }
.error-banner { border: 1px solid rgba(239,68,68,0.4); color: #fca5a5; background: rgba(239,68,68,0.08); border-radius: 6px; }
</style>
