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
    <div class="progress-bar" v-if="running || task">
      <span :class="statusClass">{{ statusLabel }}</span>
      <span>{{ stats.processed_stocks || 0 }} / {{ stats.total_stocks || task?.total_stocks || 0 }}</span>
      <span>{{ stats.current_code }} {{ stats.current_name }}</span>
      <span>机会: {{ stats.opportunities_count || task?.opportunities_count || 0 }}</span>
      <span>数据不足: {{ stats.insufficient_stocks_count || task?.insufficient_stocks_count || 0 }}</span>
      <button v-if="canCancel" class="btn-action" :disabled="actionPending" @click.stop="runTaskAction('cancel')">取消</button>
      <button v-if="canResume" class="btn-action" :disabled="actionPending" @click.stop="runTaskAction('resume')">恢复</button>
      <button v-if="canRetryFailed" class="btn-action" :disabled="actionPending" @click.stop="runTaskAction('retry')">重试失败股票</button>
    </div>
    <div v-if="actionError" class="error-msg">{{ actionError }}</div>

    <div class="panel version-panel" v-if="task">
      <h3>可信度与版本</h3>
      <div class="summary-grid">
        <div class="metric"><span class="label">可信度</span><span class="value small" :class="credibilityClass">{{ task.credibility_status || '--' }}</span></div>
        <div class="metric"><span class="label">回测引擎</span><span class="value small">{{ task.backtest_engine_version || '--' }}</span></div>
        <div class="metric"><span class="label">策略引擎</span><span class="value small">{{ task.strategy_engine_version || '--' }}</span></div>
        <div class="metric"><span class="label">数据版本算法</span><span class="value small">{{ task.data_revision_version || '--' }}</span></div>
        <div class="metric"><span class="label">数据指纹</span><span class="value small code">{{ shortRevision }}</span></div>
        <div class="metric"><span class="label">执行模型</span><span class="value small">{{ task.execution_model || '--' }}</span></div>
        <div class="metric"><span class="label">数据快照</span><span class="value small">{{ task.data_snapshot_date || '--' }}</span></div>
      </div>
    </div>

    <!-- Summary -->
    <div class="panel" v-if="task && task.summary">
      <h3>汇总报告</h3>
      <div class="summary-grid">
        <div class="metric"><span class="label">测试股票</span><span class="value">{{ task.total_stocks }}</span></div>
        <div class="metric"><span class="label">有机会股票</span><span class="value">{{ task.stocks_with_opportunities }}</span></div>
        <div class="metric"><span class="label">总机会数</span><span class="value">{{ task.opportunities_count }}</span></div>
        <div class="metric"><span class="label">数据不足</span><span class="value">{{ task.insufficient_stocks_count }}</span></div>
        <div class="metric"><span class="label">失败</span><span class="value">{{ task.failed_stocks_count || 0 }}</span></div>
        <div class="metric"><span class="label">耗时</span><span class="value">{{ fmtDuration(task.elapsed_seconds) }}</span></div>
      </div>

      <div v-if="funnel" class="horizon-table">
        <h4>评估漏斗</h4>
        <table>
          <thead>
            <tr><th>评估日</th><th>流动性过滤</th><th>趋势过滤</th><th>一票否决</th><th>分数不足</th><th>风险过滤</th><th>无效数据</th><th>评估异常</th><th>原始信号</th><th>机会</th></tr>
          </thead>
          <tbody>
            <tr>
              <td>{{ funnel.evaluation_days }}</td><td>{{ funnel.liquidity_filtered_days }}</td>
              <td>{{ funnel.trend_filtered_days }}</td><td>{{ funnel.rejection_failed_days }}</td>
              <td>{{ funnel.score_failed_days }}</td><td>{{ funnel.risk_failed_days }}</td>
              <td>{{ funnel.invalid_data_days }}</td><td>{{ funnel.evaluation_error_days }}</td>
              <td>{{ funnel.raw_signals_count }}</td><td>{{ funnel.opportunities_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Horizon stats -->
      <div v-if="horizonStats" class="horizon-table">
        <h4>短线表现</h4>
        <div class="result-legend">
          <span class="green">● 成功</span> = 先触及 +5% 目标价（此前未触止损）
          <span class="red">● 失败</span> = 先触发策略止损（或同日同时触发）
          <span>● 未决</span> = 观察期内目标和止损均未触发
          <span style="color:#666;margin-left:8px">| 目标 = 入场价 × 1.05 &nbsp; 止损 = 前10日最低收盘价 × 0.97</span>
        </div>
        <table>
          <thead>
            <tr><th>周期</th><th>样本</th><th>成功</th><th>成功率</th><th>失败</th><th>未决</th><th>平均达标天数</th><th>平均止损天数</th><th>平均收益</th><th>平均最大上涨</th><th>平均最大回撤</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in horizons" :key="h">
              <td>{{ h }}日</td>
              <td>{{ hs(h, 'observed') }}</td>
              <td class="green">{{ hs(h, 'success') }}</td>
              <td class="green">{{ hs(h, 'success_rate') }}%</td>
              <td class="red">{{ hs(h, 'failed') }}</td>
              <td>{{ hs(h, 'unresolved') }}</td>
              <td>{{ hs(h, 'avg_days_to_target') }}</td>
              <td>{{ hs(h, 'avg_days_to_stop') }}</td>
              <td>{{ fmtPct(hs(h, 'avg_end_return')) }}</td>
              <td>{{ fmtPct(hs(h, 'avg_max_upside')) }}</td>
              <td class="red">{{ fmtPct(hs(h, 'avg_max_drawdown')) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="panel" v-if="failedStocks.length">
      <h3>失败股票 ({{ failedStocks.length }})</h3>
      <table>
        <thead><tr><th>股票</th><th>错误类型</th><th>错误详情</th><th>开始</th><th>结束</th></tr></thead>
        <tbody>
          <tr v-for="s in failedStocks" :key="s.code">
            <td>{{ s.code }} {{ s.name }}</td>
            <td class="red">{{ s.error_code }}</td>
            <td>{{ s.error_detail }}</td>
            <td>{{ s.started_at }}</td>
            <td>{{ s.finished_at }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Opportunities -->
    <div class="panel" v-if="oppsTotal > 0">
      <h3>机会明细 ({{ oppsTotal }}) <span v-if="oppsHasMore" class="muted">当前显示 {{ opportunities.length }} 条</span></h3>
      <table class="opp-table">
        <thead>
          <tr><th>股票</th><th>首次命中</th><th>最后命中</th><th>连续</th><th>分数</th><th>最高分</th><th>风险比</th><th title="成功=先触+5% / 失败=先触止损 / 未决=均未触发">3日</th><th title="成功=先触+5% / 失败=先触止损 / 未决=均未触发">5日</th><th title="成功=先触+5% / 失败=先触止损 / 未决=均未触发">10日</th><th title="成功=先触+5% / 失败=先触止损 / 未决=均未触发">20日</th></tr>
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
      <div class="pagination" v-if="oppsHasMore || oppPage > 1">
        <button :disabled="oppPage <= 1" @click="loadOpps(oppPage - 1)">上一页</button>
        <span>第 {{ oppPage }} 页 / 共 {{ Math.ceil(oppsTotal / oppLimit) }} 页</span>
        <button :disabled="!oppsHasMore" @click="loadOpps(oppPage + 1)">下一页</button>
      </div>
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
      <div class="history-controls">
        <select v-model="taskStatusFilter" @change="loadTasks(1)">
          <option value="">全部状态</option>
          <option value="completed">已完成</option>
          <option value="completed_with_errors">有失败</option>
          <option value="INTERRUPTED">已中断</option>
          <option value="CANCELED">已取消</option>
          <option value="DATA_REVISION_CHANGED">数据版本变化</option>
          <option value="ENGINE_REVISION_CHANGED">引擎版本变化</option>
        </select>
      </div>
      <div v-if="!tasks.length" class="empty">暂无回测记录</div>
      <div v-for="t in tasks" :key="t.id" class="task-row" @click="loadTask(t.id)">
        <span>{{ t.id }}</span>
        <span :class="t.status === 'completed' ? 'green' : t.status === 'failed' ? 'red' : ''">{{ t.status }}</span>
        <span>{{ t.started_at }}</span>
        <span>机会: {{ t.opportunities_count }}</span>
      </div>
      <div class="pagination" v-if="taskTotal > taskPageSize">
        <button :disabled="taskPage <= 1" @click="loadTasks(taskPage - 1)">上一页</button>
        <span>第 {{ taskPage }} 页 / 共 {{ Math.ceil(taskTotal / taskPageSize) }} 页</span>
        <button :disabled="taskPage * taskPageSize >= taskTotal" @click="loadTasks(taskPage + 1)">下一页</button>
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
      task: null, tasks: [], opportunities: [], insufficient: [], failedStocks: [],
      stats: {}, pollTimer: null, horizons: ['3', '5', '10', '20'],
      oppsTotal: 0, oppsHasMore: false, oppPage: 1, oppLimit: 100,
      activeTaskId: null, actionPending: false, actionError: '',
      taskPage: 1, taskPageSize: 20, taskTotal: 0, taskStatusFilter: '',
    }
  },
  computed: {
    statusLabel() {
      if (this.running) return '运行中'
      const labels = {
        completed: '已完成', completed_with_errors: '完成但有失败',
        failed: '失败', INTERRUPTED: '已中断', CANCELED: '已取消',
        DATA_REVISION_CHANGED: '数据版本变化', ENGINE_REVISION_CHANGED: '引擎版本变化',
      }
      return labels[this.task?.status] || this.task?.status || '--'
    },
    statusClass() {
      if (this.running) return 'st-running'
      if (this.task?.status === 'completed') return 'green'
      if (this.task?.status === 'failed') return 'red'
      return ''
    },
    horizonStats() {
      if (this.task?.summary?.horizon_stats) return this.task.summary.horizon_stats
      if (this.task?.horizon_stats) return this.task.horizon_stats
      return null
    },
    funnel() {
      return this.task?.summary?.funnel || null
    },
    canCancel() { return this.running && this.task?.id === this.activeTaskId },
    canResume() { return !this.running && ['INTERRUPTED', 'CANCELED'].includes(this.task?.status) },
    canRetryFailed() {
      return !this.running && Number(this.task?.failed_stocks_count || 0) > 0
        && !['DATA_REVISION_CHANGED', 'ENGINE_REVISION_CHANGED'].includes(this.task?.status)
    },
    credibilityClass() {
      if (this.task?.credibility_status === 'TRUSTED_BASELINE') return 'green'
      return 'red'
    },
    shortRevision() { return this.task?.data_revision_id?.slice(0, 12) || '--' },
  },
  async mounted() {
    await this.loadTasks()
    const api = useApi()
    const status = await api.getStrategy2BacktestStatus()
    if (status.running && status.taskId) {
      this.running = true
      this.activeTaskId = status.taskId
      this.stats = status.stats || {}
      await this.loadTask(status.taskId)
      this.pollStatus()
    }
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
        this.running = true; this.activeTaskId = res.task_id; this.task = { id: res.task_id, status: 'running' }
        this.opportunities = []; this.insufficient = []; this.failedStocks = []
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
        if (!s.running) {
          this.stopPoll(); this.running = false
          if (this.activeTaskId) await this.loadTask(this.activeTaskId)
          await this.loadTasks(this.taskPage)
          return
        }
        this.activeTaskId = s.taskId || this.activeTaskId
        this.stats = s.stats || {}
      }, 2000)
    },
    stopPoll() { if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null } },
    async loadTasks(page = 1) {
      const api = useApi()
      this.taskPage = page
      const params = new URLSearchParams({ page: String(page), page_size: String(this.taskPageSize) })
      if (this.taskStatusFilter) params.set('status', this.taskStatusFilter)
      const res = await api.getStrategy2BacktestTasks(params)
      this.tasks = res.tasks || []
      this.taskTotal = res.total || this.tasks.length
    },
    async loadTask(taskId) {
      const api = useApi()
      this.task = await api.getStrategy2BacktestTask(taskId)
      this.oppPage = 1
      await this.loadOpps(1)
      const iRes = await api.getStrategy2BacktestInsufficientStocks(taskId)
      this.insufficient = iRes.stocks || []
      const fRes = await api.getStrategy2BacktestStocks(taskId, 'FAILED')
      this.failedStocks = fRes.stocks || []
    },
    async loadOpps(page) {
      const api = useApi()
      this.oppPage = page
      const offset = (page - 1) * this.oppLimit
      const oRes = await api.getStrategy2BacktestOpportunities(this.task.id, { limit: this.oppLimit, offset })
      this.opportunities = (oRes.items || oRes.opportunities || []).map(o => {
        try { o._h3 = JSON.parse(o.horizon_3 || '{}') } catch {}
        try { o._h5 = JSON.parse(o.horizon_5 || '{}') } catch {}
        try { o._h10 = JSON.parse(o.horizon_10 || '{}') } catch {}
        try { o._h20 = JSON.parse(o.horizon_20 || '{}') } catch {}
        return o
      })
      this.oppsTotal = oRes.total || this.opportunities.length
      this.oppsHasMore = oRes.hasMore || false
    },
    async runTaskAction(action) {
      if (!this.task?.id) return
      this.actionPending = true; this.actionError = ''
      const api = useApi()
      const fn = action === 'cancel' ? api.cancelStrategy2Backtest
        : action === 'resume' ? api.resumeStrategy2Backtest
          : api.retryFailedStrategy2Backtest
      const res = await fn(this.task.id)
      if (!res.ok) {
        this.actionError = res.message || res.error || '操作失败'
      } else if (action !== 'cancel') {
        this.running = true; this.activeTaskId = this.task.id; this.pollStatus()
      } else {
        this.task.status = 'canceling'
      }
      this.actionPending = false
    },
    hs(h, key) {
      const stats = this.horizonStats
      if (!stats) return '--'
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
.metric .value.small { font-size: 12px; }
.btn-action { padding: 4px 10px; background: #2a2a2a; border: 1px solid #555; color: #ddd; border-radius: 3px; cursor: pointer; }
.btn-action:disabled { opacity: 0.5; cursor: not-allowed; }
.history-controls { margin-bottom: 10px; }
.history-controls select { padding: 5px 8px; background: #2a2a2a; border: 1px solid #444; color: #ddd; }
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
.pagination { display: flex; gap: 12px; align-items: center; justify-content: center; padding: 12px 0; font-size: 0.8rem; color: #aaa; }
.pagination button { padding: 4px 12px; background: #2a2a2a; border: 1px solid #444; color: #ccc; border-radius: 3px; cursor: pointer; }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.result-legend { font-size: 0.75rem; color: #888; margin-bottom: 10px; display: flex; gap: 20px; flex-wrap: wrap; }
</style>
