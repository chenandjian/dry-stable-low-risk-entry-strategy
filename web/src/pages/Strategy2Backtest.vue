<template>
  <div class="s2-backtest">
    <h1>策略2 · 短线回测</h1>
    <p class="subtitle">使用本地数据库历史日线，验证策略2选股信号和3/5/10/20日短线表现。不会请求外部数据源。</p>

    <!-- Parameters -->
    <div class="params-bar">
      <label>开始日期 <input type="date" v-model="startDate"></label>
      <label>结束日期 <input type="date" v-model="endDate"></label>
      <label>股票代码 <input type="text" v-model="codesInput" placeholder="留空=全市场，逗号分隔"></label>
      <label title="限制回测股票数量，留空或0=全市场（约5000只，需数分钟）。默认200只快速验证。">最多测试 <input type="number" v-model.number="maxStocks" min="0" max="5000" step="100" placeholder="200"></label>
      <button class="btn-start" @click="startBacktest" :disabled="running || starting">{{ running ? '运行中' : '启动回测' }}</button>
    </div>
    <div class="params-hint">
      <strong>最多测试：</strong>默认 200 只股票（约 2 万次判断，秒级完成），用于快速验证策略是否有效。
      设 0 或清空则全市场回测（约 5000 只，~50 万次判断，需数分钟）。
    </div>

    <!-- Error -->
    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- Progress -->
    <div class="progress-bar" v-if="running || (task && task.status === 'completed')">
      <span :class="statusClass">{{ statusLabel }}</span>
      <span>{{ stats.processed_stocks || 0 }} / {{ stats.total_stocks || task?.total_stocks || 0 }}</span>
      <span>{{ stats.current_code }} {{ stats.current_name }}</span>
      <span>机会: {{ stats.opportunities_count || task?.opportunities_count || 0 }}</span>
      <span>数据不足: {{ stats.insufficient_stocks_count || task?.insufficient_stocks_count || 0 }}</span>
    </div>

    <!-- Summary -->
    <div class="panel" v-if="task && task.status === 'completed'">
      <h3>汇总报告</h3>
      <div class="summary-grid">
        <div class="metric"><span class="label">测试股票</span><span class="value">{{ task.total_stocks }}</span></div>
        <div class="metric"><span class="label">有机会股票</span><span class="value">{{ task.stocks_with_opportunities }}</span></div>
        <div class="metric"><span class="label">总机会数</span><span class="value">{{ task.opportunities_count }}</span></div>
        <div class="metric"><span class="label">数据不足</span><span class="value">{{ task.insufficient_stocks_count }}</span></div>
        <div class="metric"><span class="label">失败</span><span class="value">{{ task.failed_stocks_count || 0 }}</span></div>
        <div class="metric"><span class="label">耗时</span><span class="value">{{ fmtDuration(task.elapsed_seconds) }}</span></div>
      </div>

      <!-- Horizon stats -->
      <div v-if="horizonStats" class="horizon-table">
        <h4>短线表现</h4>
        <table>
          <thead>
            <tr><th>周期</th><th>样本</th><th>成功</th><th>成功率</th><th>失败</th><th>未决</th><th>平均收益</th><th>平均最大上涨</th><th>平均最大回撤</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in horizons" :key="h">
              <td>{{ h }}日</td>
              <td>{{ hs(h, 'observed') }}</td>
              <td class="green">{{ hs(h, 'success') }}</td>
              <td class="green">{{ hs(h, 'success_rate') }}%</td>
              <td class="red">{{ hs(h, 'failed') }}</td>
              <td>{{ hs(h, 'unresolved') }}</td>
              <td>{{ fmtPct(hs(h, 'avg_end_return')) }}</td>
              <td>{{ fmtPct(hs(h, 'avg_max_upside')) }}</td>
              <td class="red">{{ fmtPct(hs(h, 'avg_max_drawdown')) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Opportunities -->
    <div class="panel" v-if="opportunities.length">
      <h3>机会明细 ({{ opportunities.length }})</h3>
      <table class="opp-table">
        <thead>
          <tr><th>股票</th><th>首次命中</th><th>最后命中</th><th>连续</th><th>分数</th><th>最高分</th><th>风险比</th><th>3日</th><th>5日</th><th>10日</th><th>20日</th></tr>
        </thead>
        <tbody>
          <tr v-for="o in opportunities" :key="o.id">
            <td><span class="code">{{ o.code }}</span> <span class="name">{{ o.name }}</span></td>
            <td>{{ o.first_detected_date }}</td>
            <td>{{ o.last_detected_date }}</td>
            <td>{{ o.consecutive_hit_days }}</td>
            <td>{{ o.first_score }}</td>
            <td>{{ o.max_score }}</td>
            <td>{{ fmtPct(o.risk_ratio) }}</td>
            <td :class="resClass(o, '3')">{{ hResult(o, '3') }}</td>
            <td :class="resClass(o, '5')">{{ hResult(o, '5') }}</td>
            <td :class="resClass(o, '10')">{{ hResult(o, '10') }}</td>
            <td :class="resClass(o, '20')">{{ hResult(o, '20') }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Insufficient Stocks -->
    <div class="panel" v-if="insufficient.length">
      <h3>数据不足股票 ({{ insufficient.length }})</h3>
      <table>
        <thead><tr><th>股票</th><th>原因</th><th>可用天数</th><th>需要天数</th><th>最早</th><th>最晚</th></tr></thead>
        <tbody>
          <tr v-for="s in insufficient" :key="s.code">
            <td>{{ s.code }} {{ s.name }}</td>
            <td class="red">{{ s.reason_code }}</td>
            <td>{{ s.available_days }}</td>
            <td>{{ s.required_days }}</td>
            <td>{{ s.earliest_date }}</td>
            <td>{{ s.latest_date }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Task History -->
    <div class="panel">
      <h3>历史回测任务</h3>
      <div v-if="!tasks.length" class="empty">暂无回测记录</div>
      <div v-for="t in tasks" :key="t.id" class="task-row" @click="loadTask(t.id)">
        <span>{{ t.id }}</span>
        <span :class="t.status === 'completed' ? 'green' : t.status === 'failed' ? 'red' : ''">{{ t.status }}</span>
        <span>{{ t.started_at }}</span>
        <span>机会: {{ t.opportunities_count }}</span>
      </div>
    </div>
  </div>
</template>

<script>
import { useApi } from '../composables/useApi.js'

export default {
  name: 'Strategy2Backtest',
  data() {
    return {
      startDate: '2025-08-01', endDate: '2026-05-01',
      codesInput: '', maxStocks: 200,
      running: false, starting: false, error: '',
      task: null, tasks: [], opportunities: [], insufficient: [],
      stats: {}, pollTimer: null, horizons: ['3', '5', '10', '20'],
    }
  },
  computed: {
    statusLabel() {
      if (this.running) return '运行中'
      if (this.task?.status === 'completed') return '已完成'
      if (this.task?.status === 'failed') return '失败'
      return '--'
    },
    statusClass() {
      if (this.running) return 'st-running'
      if (this.task?.status === 'completed') return 'green'
      if (this.task?.status === 'failed') return 'red'
      return ''
    },
    horizonStats() { return null },  // populated by loadTask
  },
  async mounted() {
    await this.loadTasks()
  },
  beforeUnmount() { this.stopPoll() },
  methods: {
    async startBacktest() {
      if (!this.startDate || !this.endDate) { this.error = '请选择日期范围'; return }
      this.error = ''; this.starting = true
      const api = useApi()
      // 0、空字符串、null 均表示全市场，其余使用指定值
      let maxVal = this.maxStocks
      if (maxVal === '' || maxVal == null || Number(maxVal) === 0) maxVal = null
      const payload = { startDate: this.startDate, endDate: this.endDate, maxStocks: maxVal }
      if (this.codesInput.trim()) payload.codes = this.codesInput.split(',').map(s => s.trim()).filter(Boolean)
      const res = await api.startStrategy2Backtest(payload)
      if (res.ok) {
        this.running = true; this.task = null; this.opportunities = []; this.insufficient = []
        this.pollStatus()
      } else {
        this.error = res.message || res.error || '启动失败'
      }
      this.starting = false
    },
    pollStatus() {
      this.stopPoll()
      this.pollTimer = setInterval(async () => {
        const api = useApi()
        const s = await api.getStrategy2BacktestStatus()
        if (!s.running) { this.stopPoll(); this.running = false; await this.loadTasks(); return }
        this.stats = s.stats || {}
      }, 2000)
    },
    stopPoll() { if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null } },
    async loadTasks() {
      const api = useApi()
      const res = await api.getStrategy2BacktestTasks()
      this.tasks = res.tasks || []
    },
    async loadTask(taskId) {
      const api = useApi()
      this.task = await api.getStrategy2BacktestTask(taskId)
      const oRes = await api.getStrategy2BacktestOpportunities(taskId)
      this.opportunities = (oRes.opportunities || []).map(o => {
        try { o._h3 = JSON.parse(o.horizon_3 || '{}') } catch {}
        try { o._h5 = JSON.parse(o.horizon_5 || '{}') } catch {}
        try { o._h10 = JSON.parse(o.horizon_10 || '{}') } catch {}
        try { o._h20 = JSON.parse(o.horizon_20 || '{}') } catch {}
        return o
      })
      const iRes = await api.getStrategy2BacktestInsufficientStocks(taskId)
      this.insufficient = iRes.stocks || []
    },
    hs(h, key) {
      const stats = (this.task && this.task.horizon_stats) ? this.task.horizon_stats : {}
      const hData = stats[h]
      if (!hData) return '--'
      return hData[key] != null ? hData[key] : '--'
    },
    resultLabel(r) {
      if (r === 'SUCCESS') return '成功'
      if (r === 'FAILED') return '失败'
      if (r === 'UNRESOLVED') return '未决'
      if (r === 'UNOBSERVED') return '无数据'
      return r || '--'
    },
    hResult(o, h) {
      const data = o['_h' + h]
      if (!data) return '--'
      return this.resultLabel(data.result)
    },
    resClass(o, h) {
      const data = o['_h' + h]
      if (!data) return ''
      if (data.result === 'SUCCESS') return 'green'
      if (data.result === 'FAILED') return 'red'
      return ''
    },
    fmtPct(v) { if (v == null) return '--'; return (Number(v) * 100).toFixed(2) + '%' },
    fmtDuration(v) { if (v == null) return '--'; const s = Number(v); return `${Math.floor(s/60)}m ${Math.round(s%60)}s` },
  },
}
</script>

<style scoped>
.s2-backtest { padding: 24px; color: #e0e0e0; max-width: 1400px; margin: 0 auto; }
h1 { font-size: 1.5rem; color: #ffd700; margin-bottom: 4px; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 0.85rem; }
.params-bar { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; padding: 16px; background: #1a1a1a; border: 1px solid #333; border-radius: 6px; margin-bottom: 16px; }
.params-bar label { font-size: 12px; color: #aaa; }
.params-bar input { display: block; margin-top: 4px; padding: 6px 8px; background: #2a2a2a; border: 1px solid #444; color: #e0e0e0; border-radius: 4px; font-size: 13px; width: 130px; }
.params-bar input[type="number"] { width: 80px; }
.btn-start { padding: 8px 24px; background: var(--accent); color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; font-weight: 600; }
.btn-start:disabled { opacity: 0.5; cursor: not-allowed; }
.note { font-size: 11px; color: #666; }
.error-msg { color: #e44; padding: 8px 16px; margin-bottom: 12px; background: #2a0000; border-radius: 4px; }
.progress-bar { display: flex; gap: 20px; padding: 12px 16px; background: #1a1a2e; border: 1px solid #333; border-radius: 6px; margin-bottom: 16px; font-size: 13px; }
.st-running { color: var(--warn-orange); font-weight: 600; }
.panel { background: #1a1a1a; border: 1px solid #333; border-radius: 6px; padding: 16px; margin-bottom: 16px; }
.panel h3 { font-size: 14px; color: #aaa; margin-bottom: 12px; }
.panel h4 { font-size: 13px; color: #888; margin: 12px 0 8px; }
.summary-grid { display: flex; gap: 24px; flex-wrap: wrap; }
.metric { text-align: center; }
.metric .label { display: block; font-size: 11px; color: #888; }
.metric .value { display: block; font-size: 18px; font-weight: 700; color: var(--accent); margin-top: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th { background: #111; color: #888; padding: 6px 8px; text-align: left; border-bottom: 1px solid #333; }
td { padding: 6px 8px; border-bottom: 1px solid #222; }
.green { color: var(--down-green); }
.red { color: var(--up-red); }
.code { color: var(--accent); font-family: var(--font-mono); }
.name { color: #666; margin-left: 6px; }
.task-row { display: flex; gap: 20px; padding: 8px 12px; border-bottom: 1px solid #222; cursor: pointer; font-size: 0.8rem; }
.task-row:hover { background: rgba(79,125,255,0.05); }
.empty { text-align: center; padding: 30px; color: #666; }
</style>
