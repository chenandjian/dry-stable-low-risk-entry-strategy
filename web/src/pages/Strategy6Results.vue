<template>
  <div class="strategy6-results">
    <div class="page-header">
      <div>
        <h1>策略6 · 强势 VCP 尾部候选池</h1>
        <p>强势启动后有支撑横盘，尾部价稳量干且盈亏比合格的候选池。</p>
      </div>
      <select v-model="selectedTaskId" @change="loadCandidates">
        <option value="">选择策略6任务</option>
        <option v-for="task in tasks" :key="task.id" :value="task.id">
          {{ task.id }} · {{ task.status }} · {{ task.candidates || 0 }} 候选
        </option>
      </select>
      <button
        data-test="export-candidates"
        class="export-btn"
        :disabled="!candidates.length"
        @click="exportCandidates"
      >一键导出列表</button>
      <button
        data-test="export-excel-report"
        class="export-btn"
        :disabled="!selectedTaskId"
        @click="exportExcelReport"
      >导出日报Excel</button>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="summary-bar" v-if="candidates.length">
      <span>候选数 <strong>{{ candidates.length }}</strong></span>
      <span class="chip ready">就绪 {{ readyCandidates.length }}</span>
      <span class="chip key">重点 {{ keyCandidates.length }}</span>
      <span class="chip watch">观察 {{ watchCandidates.length }}</span>
      <span>最高分 {{ topScore }}</span>
      <span>最高RR2 {{ topRr2 }}</span>
    </div>

    <div class="empty" v-if="!loading && !selectedTaskId">请选择一个策略6任务查看结果。</div>
    <div class="empty" v-else-if="!loading && selectedTaskId && !candidates.length">当前任务没有策略6候选。</div>

    <section v-if="marketSnapshot" class="panel market-panel">
      <div class="panel-header">市场过滤数据</div>
      <div class="market-summary">
        <span>状态 <strong>{{ marketSnapshot.market_status || 'UNKNOWN' }}</strong></span>
        <span>20日市场涨幅 <strong>{{ pct(marketSnapshot.market_return_20) }}</strong></span>
        <span v-for="reason in marketSnapshot.market_reasons || []" :key="reason" class="tag info">{{ reason }}</span>
      </div>
      <div class="table-scroll">
        <table class="market-table">
          <thead>
            <tr>
              <th>指数</th><th>日期</th><th>收盘</th><th>MA20</th><th>MA50</th>
              <th>数据状态</th><th>20日涨幅</th><th>MA20上方</th><th>MA20≥MA50</th><th>放量下跌风险</th><th>来源</th><th>抓取时间</th><th>数据行数</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="idx in marketIndexes" :key="idx.symbol">
              <td>{{ idx.name || idx.symbol }} <span class="muted">{{ idx.symbol }}</span></td>
              <td>{{ idx.latest_date || '--' }}</td>
              <td>{{ fmt(idx.latest_close) }}</td>
              <td>MA20 {{ fmt(idx.ma20) }}</td>
              <td>{{ fmt(idx.ma50) }}</td>
              <td>{{ marketDataStatusText(idx.data_status) }}</td>
              <td>{{ pct(idx.return_20) }}</td>
              <td>{{ idx.above_ma20 ? '是' : '否' }}</td>
              <td>{{ idx.ma20_above_ma50 ? '是' : '否' }}</td>
              <td>{{ idx.volume_down_risk ? '是' : '否' }}</td>
              <td>{{ idx.source || '--' }}</td>
              <td>{{ idx.fetched_at || '--' }}</td>
              <td>{{ idx.rows_count ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="lifecycleAuditRows.length" class="panel">
      <div class="panel-header">生命周期退出/冷却审计</div>
      <div class="table-scroll">
        <table class="lifecycle-table">
          <thead><tr><th>股票</th><th>状态</th><th>首次入池</th><th>池龄</th><th>退出日期</th><th>退出原因</th><th>冷却至</th><th>重入次数</th></tr></thead>
          <tbody>
            <tr v-for="row in lifecycleAuditRows" :key="row.code">
              <td><span class="code">{{ row.code }}</span> {{ row.name }}</td>
              <td>{{ row.lifecycle_status }}</td>
              <td>{{ row.first_seen_date || '--' }}</td>
              <td>{{ row.days_in_pool ?? 0 }}日</td>
              <td>{{ row.exit_date || '--' }}</td>
              <td>{{ row.exit_reason || (row.reject_reasons || []).join(' / ') || '--' }}</td>
              <td>{{ row.cooldown_until_date || '--' }}</td>
              <td>{{ row.reentry_count ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-for="group in candidateGroups" :key="group.type" class="panel">
      <div class="panel-header">{{ group.title }}</div>
      <div class="table-scroll">
        <table class="candidate-table">
          <thead>
            <tr>
              <th>股票</th><th>现价</th><th>总分</th><th>分类</th><th>生命周期</th>
              <th>启动类型/等级</th><th>支撑状态</th><th>Key/前置支撑</th><th>买入区</th>
              <th>止损</th><th>客观目标1/2</th><th>客观RR2</th><th>形态</th><th>尾部路径/箱体</th><th>尾段/前20量比</th><th>市场/RS</th><th>入池</th><th>风险/警告</th><th>数据日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in group.items" :key="c.code" class="clickable" @click="selected = c">
              <td><span class="code">{{ c.code }}</span> {{ c.name }}</td>
              <td>{{ fmt(c.current_price) }}</td>
              <td class="score">{{ fmt(c.total_score, 0) }}</td>
              <td><span class="type-badge" :class="classFor(c)">{{ c.candidate_type }}</span></td>
              <td>{{ c.lifecycle_status || '--' }}</td>
              <td>{{ c.start_type || '--' }} / {{ c.start_grade || '--' }}</td>
              <td>{{ c.support_status || '--' }}</td>
              <td>{{ fmt(c.key_support_price) }} / {{ fmt(c.prior_key_support_price) }}</td>
              <td>{{ priceRange(c.buy_zone_low, c.buy_zone_high) }}</td>
              <td>{{ fmt(c.stop_loss_price) }}</td>
              <td>{{ fmt(c.objective_target_1 ?? c.target_price_1) }} / {{ fmt(c.objective_target_2 ?? c.target_price_2) }}</td>
              <td class="rr">{{ fmt(c.objective_rr_2 ?? c.risk_reward_ratio_2) }}</td>
              <td>{{ c.pattern_type || 'UNKNOWN' }}</td>
              <td>{{ c.tail_path || 'NONE' }} / {{ c.box_status || 'NO_BOX' }}</td>
              <td>{{ fmt(c.tail_volume_ratio ?? c.volume_ratio_5_20, 3) }}</td>
              <td>
                <div>{{ c.market_status || 'UNKNOWN' }}</div>
                <div class="muted">RS20 {{ pct(c.relative_strength_20) }}</div>
              </td>
              <td>
                <div>首次入池 {{ c.first_pool_date || '--' }}</div>
                <div class="muted">池龄 {{ c.pool_age_trading_days ?? 0 }}日</div>
              </td>
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
        <div><span>分类</span><strong>{{ selected.candidate_type }} / {{ selected.classification || '--' }}</strong></div>
        <div><span>生命周期</span><strong>{{ selected.lifecycle_status || '--' }}</strong></div>
        <div><span>强势启动</span><strong>{{ selected.start_type || '--' }} / {{ selected.start_grade || '--' }} / {{ pct(selected.start_day_return) }} · 启动后{{ selected.days_since_start ?? 0 }}日</strong></div>
        <div><span>启动日低点</span><strong>{{ fmt(selected.start_low) }}</strong></div>
        <div><span>支撑</span><strong>{{ selected.support_status || '--' }} · {{ selected.main_support_ma || '--' }} · 测试{{ selected.support_test_count ?? 0 }}次</strong></div>
        <div><span>战术价格</span><strong>支撑 {{ fmt(selected.key_support_price) }} · 前置支撑 {{ fmt(selected.prior_key_support_price) }} · 止损 {{ fmt(selected.stop_loss_price) }}</strong></div>
        <div><span>买入区</span><strong>{{ priceRange(selected.buy_zone_low, selected.buy_zone_high) }}</strong></div>
        <div><span>阶段</span><strong>{{ selected.phase_status || '--' }} · 整理 {{ selected.consolidation_start_date || '--' }} · 尾段 {{ selected.tail_start_date || '--' }}</strong></div>
        <div><span>形态</span><strong>{{ selected.pattern_type || 'UNKNOWN' }} · {{ selected.pivot_source || '--' }} · 收缩{{ selected.contraction_count ?? 0 }}次</strong></div>
        <div><span>支撑簇</span><strong>战术 {{ fmt(selected.tactical_support_price) }} · {{ (selected.support_cluster_sources || []).join(' / ') || '--' }}</strong></div>
        <div><span>客观目标</span><strong>{{ fmt(selected.objective_target_1 ?? selected.target_price_1) }} / {{ fmt(selected.objective_target_2 ?? selected.target_price_2) }} · RR {{ fmt(selected.objective_rr_1 ?? selected.risk_reward_ratio_1) }} / {{ fmt(selected.objective_rr_2 ?? selected.risk_reward_ratio_2) }}</strong></div>
        <div><span>执行R目标</span><strong>1.5R {{ fmt(selected.execution_target_1_5r) }} · 2R {{ fmt(selected.execution_target_2r) }} · 2.5R {{ fmt(selected.execution_target_2_5r) }} · 3.5R {{ fmt(selected.execution_target_3_5r) }}</strong></div>
        <div><span>执行窗口</span><strong>{{ selected.valid_from_date || '--' }} 至 {{ selected.valid_until_date || '--' }} · 限价 {{ fmt(selected.suggested_limit_price) }}</strong></div>
        <div><span>六维评分</span><strong>启动{{ selected.strong_start_score ?? 0 }} 形态{{ selected.pattern_score_component ?? 0 }} 支撑{{ selected.support_score ?? 0 }} 尾段{{ selected.tail_score ?? 0 }} 客观RR{{ selected.objective_rr_score ?? 0 }} RS/风险{{ selected.relative_strength_risk_score ?? 0 }}</strong></div>
        <div><span>尾部路径</span><strong>{{ selected.tail_path || 'NONE' }} · 原路径 {{ selected.original_tail_pass ? '通过' : '未通过' }}/{{ selected.original_tail_score ?? 0 }} · 箱体 {{ selected.box_tail_pass ? '通过' : '未通过' }}/{{ selected.box_tail_score ?? 0 }}</strong></div>
        <div><span>稳定箱体</span><strong>{{ selected.box_status || 'NO_BOX' }} · {{ selected.box_start_date || '--' }} 至 {{ selected.box_end_date || '--' }} · {{ selected.box_days ?? 0 }}日</strong></div>
        <div><span>箱体区间</span><strong>{{ priceRange(selected.box_low, selected.box_high) }} · 宽度 {{ pct(selected.box_width) }} · 位置 {{ pct(selected.box_position) }}</strong></div>
        <div><span>箱体承接</span><strong>下沿测试{{ selected.box_low_test_count ?? 0 }}次 · 上沿测试{{ selected.box_high_test_count ?? 0 }}次 · 中枢 {{ pct(selected.box_center_shift) }} · 后/前量 {{ fmt(selected.box_volume_contraction_ratio, 3) }}</strong></div>
        <div><span>紧密排列</span><strong>{{ selected.box_quality_tag || 'NONE' }} · {{ selected.compact_kline_pass ? '通过' : '未通过' }} · {{ selected.compact_kline_score ?? 0 }}/10 · 箱体质量 {{ selected.box_quality_score ?? 0 }}</strong></div>
        <div><span>紧密指标</span><strong>平均实体 {{ pct(selected.avg_body_ratio_5) }} · 收盘区间 {{ pct(selected.compact_close_range_5) }} · 重叠{{ selected.kline_overlap_pair_count ?? 0 }}组 · ATR比 {{ fmt(selected.atr_contraction_ratio, 3) }}</strong></div>
        <div><span>市场过滤</span><strong>{{ selected.market_status || 'UNKNOWN' }} · {{ selected.enable_market_filter ? '开启' : '关闭' }} · {{ selected.market_filter_mode || '--' }}</strong></div>
        <div><span>相对强度</span><strong>RS20 {{ pct(selected.relative_strength_20) }}</strong></div>
        <div><span>候选池</span><strong>首次入池 {{ selected.first_pool_date || '--' }} · 池龄 {{ selected.pool_age_trading_days ?? 0 }}日</strong></div>
        <div><span>退出/冷却</span><strong>{{ selected.exit_reason || '--' }} · 冷却至 {{ selected.cooldown_until_date || '--' }} · 重入 {{ selected.reentry_count ?? 0 }} 次</strong></div>
        <div><span>量能</span><strong>尾段 {{ fmt(selected.tail_avg_volume, 0) }} · 前置20日 {{ fmt(selected.pre_tail_avg_volume_20, 0) }} · 比值 {{ fmt(selected.tail_volume_ratio, 3) }}</strong></div>
        <div><span>版本</span><strong>{{ selected.strategy_version || '--' }} · {{ selected.config_hash || '--' }}</strong></div>
        <div><span>价格口径</span><strong>{{ selected.price_basis || 'FORWARD_ADJUSTED' }} · 未复权报价 {{ fmt(selected.current_price_raw) }}</strong></div>
        <div><span>涨跌幅</span><strong>5日 {{ pct(selected.return_5) }} · 10日 {{ pct(selected.return_10) }} · 20日 {{ pct(selected.return_20) }}</strong></div>
        <div><span>建议</span><strong>{{ selected.suggestion || '--' }}</strong></div>
      </div>
      <div class="tags">
        <span v-for="note in selected.execution_notes || []" :key="'e' + note" class="tag info">{{ note }}</span>
        <span v-for="tag in selected.risk_tags || []" :key="'r' + tag" class="tag risk">{{ tag }}</span>
        <span v-for="tag in selected.warn_tags || []" :key="'w' + tag" class="tag warn">{{ tag }}</span>
        <span v-for="tag in selected.reject_reasons || []" :key="'x' + tag" class="tag risk">{{ tag }}</span>
        <span v-for="tag in selected.score_reasons || []" :key="'s' + tag" class="tag info">{{ tag }}</span>
      </div>
    </section>

    <div class="loading" v-if="loading">加载中...</div>
  </div>
</template>

<script>
import { useApi } from '../composables/useApi.js'
import { downloadCsv } from '../utils/csvExport.js'

export default {
  name: 'Strategy6Results',
  data() {
    return {
      tasks: [],
      candidates: [],
      selectedTaskId: '',
      selected: null,
      marketSnapshot: null,
      lifecycleRows: [],
      loading: false,
      error: '',
    }
  },
  computed: {
    sortedCandidates() {
      return [...this.candidates].sort((a, b) => (b.total_score || 0) - (a.total_score || 0))
    },
    readyCandidates() {
      return this.sortedCandidates.filter(c => c.candidate_type === 'READY_CANDIDATE')
    },
    keyCandidates() {
      return this.sortedCandidates.filter(c => c.candidate_type === 'KEY_CANDIDATE')
    },
    watchCandidates() {
      return this.sortedCandidates.filter(c => c.candidate_type === 'WATCH_CANDIDATE')
    },
    candidateGroups() {
      return [
        { type: 'READY_CANDIDATE', title: '就绪候选 READY_CANDIDATE', items: this.readyCandidates },
        { type: 'KEY_CANDIDATE', title: '重点候选 KEY_CANDIDATE', items: this.keyCandidates },
        { type: 'WATCH_CANDIDATE', title: '观察候选 WATCH_CANDIDATE', items: this.watchCandidates },
      ].filter(group => group.items.length)
    },
    topScore() {
      return this.sortedCandidates[0]?.total_score ?? '--'
    },
    topRr2() {
      const best = this.sortedCandidates.reduce((max, c) => Math.max(max, Number(c.objective_rr_2 ?? c.risk_reward_ratio_2 ?? 0)), 0)
      return best ? best.toFixed(2) : '--'
    },
    marketIndexes() {
      return this.marketSnapshot?.indexes || []
    },
    lifecycleAuditRows() {
      return this.lifecycleRows.filter(row => row.blocked || ['FAILED', 'EXPIRED', 'COOLDOWN'].includes(row.lifecycle_status))
    },
  },
  async mounted() {
    const api = useApi()
    try {
      const res = await api.getStrategy6Tasks()
      this.tasks = res.tasks || []
    } catch (e) {
      this.error = '策略6任务加载失败'
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
        this.marketSnapshot = null
        this.lifecycleRows = []
        return
      }
      this.loading = true
      this.error = ''
      const api = useApi()
      const taskId = this.selectedTaskId
      try {
        const res = await api.getStrategy6Candidates(taskId)
        if (this.selectedTaskId !== taskId) return
        this.candidates = res.candidates || []
        this.selected = this.candidates[0] || null
      } catch (e) {
        if (this.selectedTaskId === taskId) {
          this.error = '策略6候选加载失败'
          this.loading = false
        }
        return
      }
      try {
        const snapshotRes = await api.getStrategy6MarketSnapshot(taskId)
        if (this.selectedTaskId !== taskId) return
        this.marketSnapshot = snapshotRes.snapshot || null
      } catch (e) {
        if (this.selectedTaskId === taskId) this.error = '市场指数快照加载失败，候选数据已保留'
      }
      try {
        const lifecycleRes = await api.getStrategy6Lifecycle(taskId)
        if (this.selectedTaskId !== taskId) return
        this.lifecycleRows = lifecycleRes.lifecycle || []
      } catch (e) {
        if (this.selectedTaskId === taskId) this.error = '生命周期审计加载失败，候选数据已保留'
      }
      if (this.selectedTaskId === taskId) this.loading = false
    },
    fmt(v, digits = 2) {
      if (v == null || v === '') return '--'
      const n = Number(v)
      return Number.isFinite(n) ? n.toFixed(digits) : '--'
    },
    pct(v) {
      if (v == null || v === '') return '--'
      const n = Number(v)
      return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : '--'
    },
    priceRange(low, high) {
      if (low == null && high == null) return '--'
      return `${this.fmt(low)} - ${this.fmt(high)}`
    },
    classFor(c) {
      if (c.candidate_type === 'READY_CANDIDATE') return 'ready'
      if (c.candidate_type === 'KEY_CANDIDATE') return 'key'
      if (c.candidate_type === 'WATCH_CANDIDATE') return 'watch'
      return 'rejected'
    },
    marketDataStatusText(status) {
      if (status === 'FRESH') return '新鲜'
      if (status === 'STALE') return '过期'
      return '缺失'
    },
    exportCandidates() {
      downloadCsv({
        filename: `strategy6-candidates-${this.selectedTaskId || 'latest'}.csv`,
        columns: [
          { header: '代码', value: c => c.code },
          { header: '名称', value: c => c.name },
          { header: '板块', value: c => c.sector_name || '' },
          { header: '候选类型', value: c => c.candidate_type || '' },
          { header: '生命周期', value: c => c.lifecycle_status || '' },
          { header: '首次入池', value: c => c.first_pool_date || '' },
          { header: '池龄交易日', value: c => c.pool_age_trading_days ?? '' },
          { header: '策略版本', value: c => c.strategy_version || '' },
          { header: '阶段状态', value: c => c.phase_status || '' },
          { header: '形态类型', value: c => c.pattern_type || '' },
          { header: '总分', value: c => c.total_score ?? '' },
          { header: '市场过滤', value: c => c.enable_market_filter ? '开启' : '关闭' },
          { header: '市场过滤模式', value: c => c.market_filter_mode || '' },
          { header: '市场状态', value: c => c.market_status || '' },
          { header: 'RS20', value: c => this.pct(c.relative_strength_20) },
          { header: '现价', value: c => this.fmt(c.current_price) },
          { header: '日涨跌', value: c => this.pct(c.daily_return) },
          { header: '5日涨幅', value: c => this.pct(c.return_5) },
          { header: '10日涨幅', value: c => this.pct(c.return_10) },
          { header: '20日涨幅', value: c => this.pct(c.return_20) },
          { header: '启动日', value: c => c.start_date || '' },
          { header: '启动类型', value: c => c.start_type || '' },
          { header: '启动等级', value: c => c.start_grade || '' },
          { header: '启动日低点', value: c => this.fmt(c.start_low) },
          { header: '启动后天数', value: c => c.days_since_start ?? '' },
          { header: '支撑状态', value: c => c.support_status || '' },
          { header: 'Key支撑', value: c => this.fmt(c.key_support_price) },
          { header: '前置支撑', value: c => this.fmt(c.prior_key_support_price) },
          { header: '战术支撑', value: c => this.fmt(c.tactical_support_price) },
          { header: '支撑区低', value: c => this.fmt(c.support_zone_low) },
          { header: '支撑区高', value: c => this.fmt(c.support_zone_high) },
          { header: '建议买入价', value: c => this.fmt(c.suggested_buy_price) },
          { header: '买入区低', value: c => this.fmt(c.buy_zone_low) },
          { header: '买入区高', value: c => this.fmt(c.buy_zone_high) },
          { header: '止损', value: c => this.fmt(c.stop_loss_price) },
          { header: '目标1', value: c => this.fmt(c.target_price_1) },
          { header: '目标2', value: c => this.fmt(c.target_price_2) },
          { header: '目标3', value: c => this.fmt(c.target_price_3) },
          { header: '客观目标1', value: c => this.fmt(c.objective_target_1 ?? c.target_price_1) },
          { header: '客观目标2', value: c => this.fmt(c.objective_target_2 ?? c.target_price_2) },
          { header: '客观RR1', value: c => this.fmt(c.objective_rr_1 ?? c.risk_reward_ratio_1) },
          { header: '客观RR2', value: c => this.fmt(c.objective_rr_2 ?? c.risk_reward_ratio_2) },
          { header: '1.5R目标', value: c => this.fmt(c.execution_target_1_5r) },
          { header: '2R目标', value: c => this.fmt(c.execution_target_2r) },
          { header: '2.5R目标', value: c => this.fmt(c.execution_target_2_5r) },
          { header: '3.5R目标', value: c => this.fmt(c.execution_target_3_5r) },
          { header: 'RR1', value: c => this.fmt(c.risk_reward_ratio_1) },
          { header: 'RR2', value: c => this.fmt(c.risk_reward_ratio_2) },
          { header: 'RR3', value: c => this.fmt(c.risk_reward_ratio_3) },
          { header: 'V5/V20', value: c => this.fmt(c.volume_ratio_5_20, 3) },
          { header: '原尾部通过', value: c => c.original_tail_pass ? '是' : '否' },
          { header: '原尾部分', value: c => c.original_tail_score ?? '' },
          { header: '箱体路径启用', value: c => c.box_tail_enabled ? '是' : '否' },
          { header: '箱体通过', value: c => c.box_tail_pass ? '是' : '否' },
          { header: '箱体分', value: c => c.box_tail_score ?? '' },
          { header: '箱体状态', value: c => c.box_status || '' },
          { header: '尾部通过', value: c => c.tail_pass ? '是' : '否' },
          { header: '尾部路径', value: c => c.tail_path || '' },
          { header: '箱体开始', value: c => c.box_start_date || '' },
          { header: '箱体结束', value: c => c.box_end_date || '' },
          { header: '箱体天数', value: c => c.box_days ?? '' },
          { header: '箱体上沿', value: c => this.fmt(c.box_high) },
          { header: '箱体下沿', value: c => this.fmt(c.box_low) },
          { header: '箱体宽度', value: c => this.pct(c.box_width) },
          { header: '箱体位置', value: c => this.pct(c.box_position) },
          { header: '箱体原始位置', value: c => this.pct(c.box_position_raw) },
          { header: '下沿测试数', value: c => c.box_low_test_count ?? '' },
          { header: '上沿测试数', value: c => c.box_high_test_count ?? '' },
          { header: '箱体前半量', value: c => c.box_first_half_volume ?? '' },
          { header: '箱体后半量', value: c => c.box_second_half_volume ?? '' },
          { header: '箱体量缩比', value: c => this.fmt(c.box_volume_contraction_ratio, 3) },
          { header: '前半中枢', value: c => this.fmt(c.first_half_median_close) },
          { header: '后半中枢', value: c => this.fmt(c.second_half_median_close) },
          { header: '箱体中枢变化', value: c => this.pct(c.box_center_shift) },
          { header: '箱体跌破原因', value: c => c.box_break_reason || '' },
          { header: '箱体选择原因', value: c => c.box_selection_reason || '' },
          { header: '紧密排列启用', value: c => c.compact_kline_enabled ? '是' : '否' },
          { header: '紧密排列通过', value: c => c.compact_kline_pass ? '是' : '否' },
          { header: '紧密排列分', value: c => c.compact_kline_score ?? '' },
          { header: '箱体质量分', value: c => c.box_quality_score ?? '' },
          { header: '箱体质量标签', value: c => c.box_quality_tag || '' },
          { header: '平均实体比', value: c => this.pct(c.avg_body_ratio_5) },
          { header: '最大实体比', value: c => this.pct(c.max_body_ratio_5) },
          { header: '紧密收盘区间', value: c => this.pct(c.compact_close_range_5) },
          { header: 'K线重叠组数', value: c => c.kline_overlap_pair_count ?? '' },
          { header: '平均K线重叠比', value: c => this.pct(c.avg_kline_overlap_ratio) },
          { header: '跳空数', value: c => c.gap_count_5 ?? '' },
          { header: '最大跳空比', value: c => this.pct(c.max_gap_ratio_5) },
          { header: 'ATR5', value: c => this.fmt(c.atr5) },
          { header: 'ATR20', value: c => this.fmt(c.atr20) },
          { header: 'ATR收缩比', value: c => this.fmt(c.atr_contraction_ratio, 3) },
          { header: '紧密排列原因', value: c => (c.compact_kline_reasons || []).join('|') },
          { header: '紧密排列风险', value: c => (c.compact_kline_risk_tags || []).join('|') },
          { header: '启动分', value: c => c.strong_start_score ?? '' },
          { header: '支撑分', value: c => c.support_score ?? '' },
          { header: '量干分', value: c => c.dry_stable_score ?? '' },
          { header: '盈亏比分', value: c => c.risk_reward_score ?? '' },
          { header: '风控分', value: c => c.risk_control_score ?? '' },
          { header: '风险标签', value: c => (c.risk_tags || []).join('|') },
          { header: '警告标签', value: c => (c.warn_tags || []).join('|') },
          { header: '否决原因', value: c => (c.reject_reasons || []).join('|') },
          { header: '建议', value: c => c.suggestion || '' },
          { header: '数据日', value: c => c.kline_latest_date || c.evaluation_date || '' },
        ],
        rows: this.candidates,
      })
    },
    async exportExcelReport() {
      if (!this.selectedTaskId) return
      this.error = ''
      const api = useApi()
      try {
        const blob = await api.downloadStrategy6Report(this.selectedTaskId)
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `strategy6-report-${this.selectedTaskId}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      } catch (e) {
        this.error = '策略6日报Excel导出失败'
      }
    },
  },
}
</script>

<style scoped>
.strategy6-results { padding: 20px; color: var(--text-primary); }
.page-header { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 16px; }
h1 { margin: 0 0 6px; font-size: 22px; }
p { margin: 0; color: var(--text-secondary); }
select { background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px; min-width: 340px; }
.export-btn { background: transparent; color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px 12px; cursor: pointer; }
.export-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.export-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.summary-bar { display: flex; gap: 12px; align-items: center; margin: 12px 0; color: var(--text-secondary); flex-wrap: wrap; }
.market-summary { padding: 12px 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; color: var(--text-secondary); border-bottom: 1px solid var(--border); }
.chip, .type-badge, .tag { border-radius: 999px; padding: 2px 8px; font-size: 12px; display: inline-block; margin: 1px 3px 1px 0; }
.chip.ready, .type-badge.ready { background: rgba(59, 130, 246, 0.18); color: #93c5fd; }
.chip.key, .type-badge.key { background: rgba(168, 85, 247, 0.18); color: #d8b4fe; }
.chip.watch, .type-badge.watch { background: rgba(234, 179, 8, 0.15); color: #fde68a; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; margin: 14px 0; overflow: hidden; }
.panel-header { padding: 12px 14px; border-bottom: 1px solid var(--border); font-weight: 700; color: var(--text-secondary); }
.table-scroll { overflow-x: auto; }
.candidate-table { width: 100%; min-width: 1520px; border-collapse: collapse; font-size: 13px; }
.market-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 13px; }
.lifecycle-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--border); padding: 9px 10px; text-align: left; }
th { color: var(--text-secondary); font-weight: 600; }
td { vertical-align: top; }
.clickable { cursor: pointer; }
.clickable:hover { background: rgba(255,255,255,0.03); }
.code { color: var(--accent); font-family: var(--font-mono); }
.score, .rr { color: var(--gold); font-weight: 700; }
.tag.risk { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
.tag.warn { background: rgba(249, 115, 22, 0.16); color: #fdba74; }
.tag.info { background: rgba(79,125,255,0.15); color: #93c5fd; }
.detail-panel { padding-bottom: 12px; }
.detail-grid { padding: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
.detail-grid div { display: flex; flex-direction: column; gap: 3px; }
.detail-grid span { color: var(--text-secondary); font-size: 12px; }
.detail-grid strong { color: var(--text-primary); }
.tags { padding: 0 14px; }
.empty, .loading, .error-banner { padding: 16px; color: var(--text-secondary); }
.error-banner { border: 1px solid rgba(239,68,68,0.4); color: #fca5a5; background: rgba(239,68,68,0.08); border-radius: 6px; }
</style>
