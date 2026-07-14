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
          {{ task.id }} · {{ label('taskStatus', task.status) }} · {{ task.candidates || 0 }} 候选
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
        <span>状态 <strong>{{ label('marketStatus', marketSnapshot.market_status || 'UNKNOWN') }}</strong></span>
        <span>20日市场涨幅 <strong>{{ pct(marketSnapshot.market_return_20) }}</strong></span>
        <span v-for="reason in marketSnapshot.market_reasons || []" :key="reason" class="tag info">{{ label('marketReason', reason) }}</span>
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
              <td>{{ label('source', idx.source) }}</td>
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
              <td>{{ label('lifecycleStatus', row.lifecycle_status) }}</td>
              <td>{{ row.first_seen_date || '--' }}</td>
              <td>{{ row.days_in_pool ?? 0 }}日</td>
              <td>{{ row.exit_date || '--' }}</td>
              <td>{{ row.exit_reason ? label('tag', row.exit_reason) : joinedLabels('tag', row.reject_reasons, ' / ') }}</td>
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
              <th>股票</th><th>现价</th><th>总分</th><th>入场/质量</th><th>分类</th><th>生命周期</th>
              <th>启动类型/等级</th><th>支撑状态</th><th>关键/前置支撑</th><th>执行区间/状态</th>
              <th>止损</th><th>客观目标1/2</th><th>客观RR2</th><th>形态</th><th>权威路径/Brooks</th><th>尾段/前20量比</th><th>市场/RS</th><th>入池</th><th>风险/警告</th><th>数据日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in group.items" :key="c.code" :data-test="`candidate-row-${c.code}`" class="clickable" @click="selected = c">
              <td><span class="code">{{ c.code }}</span> {{ c.name }}</td>
              <td>{{ fmt(c.current_price) }}</td>
              <td class="score">{{ fmt(c.total_score, 0) }}</td>
              <td>
                <div>{{ entryArchetypeText(c) }}</div>
                <div class="muted">整理 {{ qualityValue(c, 'setup_quality_score') }} · 支撑 {{ qualityValue(c, 'support_reaction_score') }}</div>
              </td>
              <td><span :data-test="`candidate-type-${c.code}`" class="type-badge" :class="classFor(c)">{{ candidateTypeText(c) }}</span></td>
              <td :data-test="`candidate-lifecycle-${c.code}`">{{ lifecycleText(c) }}</td>
              <td>{{ label('startType', c.start_type) }} / {{ label('startGrade', c.start_grade) }}</td>
              <td>{{ label('supportStatus', c.support_status) }}</td>
              <td>{{ fmt(c.key_support_price) }} / {{ fmt(c.prior_key_support_price) }}</td>
              <td :data-test="`candidate-buy-zone-${c.code}`">{{ executionZoneText(c) }}</td>
              <td>{{ fmt(c.stop_loss_price) }}</td>
              <td>{{ fmt(c.objective_target_1 ?? c.target_price_1) }} / {{ fmt(c.objective_target_2 ?? c.target_price_2) }}</td>
              <td class="rr">{{ fmt(c.objective_rr_2 ?? c.risk_reward_ratio_2) }}</td>
              <td>{{ label('patternType', c.pattern_type || 'UNKNOWN') }}</td>
              <td>
                <div>{{ label('tailPathSummary', authoritativeSummary(c)) }}</div>
                <div class="muted">主路径 {{ label('tailPrimaryPath', authoritativePrimary(c)) }}</div>
                <div v-if="c.brooks_tail_enabled" class="muted">{{ label('brooksStatus', c.brooks_status || 'BROOKS_WATCH') }} · {{ brooksTradeState(c) }}</div>
                <div v-else class="muted">旧路径 {{ label('tailPath', c.tail_path || 'NONE') }}</div>
              </td>
              <td>{{ tailVolumeDisplay(c) }}</td>
              <td>
                <div>{{ label('marketStatus', c.market_status || 'UNKNOWN') }}</div>
                <div class="muted">RS20 {{ pct(c.relative_strength_20) }}</div>
              </td>
              <td>
                <div>首次入池 {{ c.first_pool_date || '--' }}</div>
                <div class="muted">池龄 {{ c.pool_age_trading_days ?? 0 }}日</div>
              </td>
              <td>
                <span v-for="tag in c.risk_tags || []" :key="'r'+tag" class="tag risk">{{ label('tag', tag) }}</span>
                <span v-for="tag in c.warn_tags || []" :key="'w'+tag" class="tag warn">{{ label('tag', tag) }}</span>
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
        <div><span>分类</span><strong>{{ candidateTypeText(selected) }} / {{ isExecutionWaiting(selected) ? '观察' : label('classification', selected.classification) }}</strong></div>
        <div><span>生命周期</span><strong>{{ lifecycleText(selected) }}</strong></div>
        <div><span>强势启动</span><strong>{{ label('startType', selected.start_type) }} / {{ label('startGrade', selected.start_grade) }} / {{ pct(selected.start_day_return) }} · 启动后{{ selected.days_since_start ?? 0 }}日</strong></div>
        <div><span>启动日低点</span><strong>{{ fmt(selected.start_low) }}</strong></div>
        <div><span>支撑</span><strong>{{ label('supportStatus', selected.support_status) }} · {{ selected.main_support_ma || '--' }} · 测试{{ selected.support_test_count ?? 0 }}次</strong></div>
        <div><span>战术价格</span><strong>支撑 {{ fmt(selected.key_support_price) }} · 前置支撑 {{ fmt(selected.prior_key_support_price) }} · 止损 {{ fmt(selected.stop_loss_price) }}</strong></div>
        <div data-test="detail-execution-zone"><span>{{ isExecutionWaiting(selected) ? '入场状态' : '买入区' }}</span><strong>{{ executionZoneText(selected) }}</strong></div>
        <div data-test="detail-entry-archetype"><span>入场类型</span><strong>{{ entryArchetypeText(selected) }}</strong></div>
        <div><span>阶段</span><strong>{{ label('phaseStatus', selected.phase_status) }} · 整理 {{ selected.consolidation_start_date || '--' }} · 尾段 {{ selected.tail_start_date || '--' }} · {{ isQualityV2(selected) ? label('tailSegmentationStatus', selected.tail_segmentation_status) : '--' }}</strong></div>
        <div><span>形态</span><strong>{{ label('patternType', selected.pattern_type || 'UNKNOWN') }} · {{ label('pivotSource', selected.pivot_source) }} · 收缩{{ selected.contraction_count ?? 0 }}次</strong></div>
        <div><span>支撑簇</span><strong>战术 {{ fmt(selected.tactical_support_price) }} · {{ joinedLabels('supportSource', selected.support_cluster_sources, ' / ') }}</strong></div>
        <div><span>客观目标</span><strong>{{ fmt(selected.objective_target_1 ?? selected.target_price_1) }} / {{ fmt(selected.objective_target_2 ?? selected.target_price_2) }} · RR {{ fmt(selected.objective_rr_1 ?? selected.risk_reward_ratio_1) }} / {{ fmt(selected.objective_rr_2 ?? selected.risk_reward_ratio_2) }}</strong></div>
        <div><span>执行R目标</span><strong>1.5R {{ fmt(selected.execution_target_1_5r) }} · 2R {{ fmt(selected.execution_target_2r) }} · 2.5R {{ fmt(selected.execution_target_2_5r) }} · 3.5R {{ fmt(selected.execution_target_3_5r) }}</strong></div>
        <div><span>执行窗口</span><strong>{{ isExecutionWaiting(selected) ? '等待交易触发确认' : `${selected.valid_from_date || '--'} 至 ${selected.valid_until_date || '--'} · 限价 ${fmt(selected.suggested_limit_price)}` }}</strong></div>
        <div data-test="detail-quality-v2"><span>质量评分（V2）</span><strong>启动质量 {{ qualityValue(selected, 'start_event_quality_score') }} · 整理质量 {{ qualityValue(selected, 'setup_quality_score') }} · 支撑反应 {{ qualityValue(selected, 'support_reaction_score') }} · 路径证据 {{ qualityValue(selected, 'path_evidence_score') }}</strong></div>
        <div><span>六维评分</span><strong>启动{{ selected.strong_start_score ?? 0 }} 形态{{ selected.pattern_score_component ?? 0 }} 支撑{{ selected.support_score ?? 0 }} 尾段{{ selected.tail_score ?? 0 }} 客观RR{{ selected.objective_rr_score ?? 0 }} RS/风险{{ selected.relative_strength_risk_score ?? 0 }}</strong></div>
        <div><span>权威三路径</span><strong>{{ label('tailPathSummary', authoritativeSummary(selected)) }} · 主路径 {{ label('tailPrimaryPath', authoritativePrimary(selected)) }} · 通过 {{ joinedLabels('tailPrimaryPath', authoritativePaths(selected), ' / ') }} · {{ selected.multi_path_confirmed ? '多路径确认' : '单路径或未通过' }}</strong></div>
        <div><span>旧尾部路径（原始/箱体）</span><strong>{{ label('tailPath', selected.tail_path || 'NONE') }} · 原路径 {{ selected.original_tail_pass ? '通过' : '未通过' }}/{{ selected.original_tail_score ?? 0 }} · 箱体 {{ selected.box_tail_pass ? '通过' : '未通过' }}/{{ selected.box_tail_score ?? 0 }}</strong></div>
        <div><span>稳定箱体</span><strong>{{ label('boxStatus', selected.box_status || 'NO_BOX') }} · {{ selected.box_start_date || '--' }} 至 {{ selected.box_end_date || '--' }} · {{ selected.box_days ?? 0 }}日</strong></div>
        <div><span>箱体区间</span><strong>{{ priceRange(selected.box_low, selected.box_high) }} · 宽度 {{ pct(selected.box_width) }} · 位置 {{ pct(selected.box_position) }}</strong></div>
        <div><span>箱体承接</span><strong>下沿测试{{ selected.box_low_test_count ?? 0 }}次 · 上沿测试{{ selected.box_high_test_count ?? 0 }}次 · 中枢 {{ pct(selected.box_center_shift) }} · 后/前量 {{ fmt(selected.box_volume_contraction_ratio, 3) }}</strong></div>
        <div><span>紧密排列</span><strong>{{ label('boxQualityTag', selected.box_quality_tag || 'NONE') }} · {{ selected.compact_kline_pass ? '通过' : '未通过' }} · {{ selected.compact_kline_score ?? 0 }}/10 · 箱体质量 {{ selected.box_quality_score ?? 0 }}</strong></div>
        <div><span>紧密指标</span><strong>平均实体 {{ pct(selected.avg_body_ratio_5) }} · 收盘区间 {{ pct(selected.compact_close_range_5) }} · 重叠{{ selected.kline_overlap_pair_count ?? 0 }}组 · ATR比 {{ fmt(selected.atr_contraction_ratio, 3) }}</strong></div>
        <div><span>市场过滤</span><strong>{{ label('marketStatus', selected.market_status || 'UNKNOWN') }} · {{ selected.enable_market_filter ? '开启' : '关闭' }} · {{ label('marketFilterMode', selected.market_filter_mode) }}</strong></div>
        <div><span>相对强度</span><strong>RS20 {{ pct(selected.relative_strength_20) }}</strong></div>
        <div><span>候选池</span><strong>首次入池 {{ selected.first_pool_date || '--' }} · 池龄 {{ selected.pool_age_trading_days ?? 0 }}日</strong></div>
        <div><span>退出/冷却</span><strong>{{ label('tag', selected.exit_reason) }} · 冷却至 {{ selected.cooldown_until_date || '--' }} · 重入 {{ selected.reentry_count ?? 0 }} 次</strong></div>
        <div><span>量能</span><strong>{{ tailVolumeDisplay(selected, true) }}</strong></div>
        <div><span>版本</span><strong>{{ selected.strategy_version || '--' }} · {{ selected.config_hash || '--' }}</strong></div>
        <div><span>价格口径</span><strong>{{ label('priceBasis', selected.price_basis || 'FORWARD_ADJUSTED') }} · 未复权报价 {{ fmt(selected.current_price_raw) }}</strong></div>
        <div><span>涨跌幅</span><strong>5日 {{ pct(selected.return_5) }} · 10日 {{ pct(selected.return_10) }} · 20日 {{ pct(selected.return_20) }}</strong></div>
        <div data-test="detail-suggestion"><span>建议</span><strong>{{ isExecutionWaiting(selected) ? '观察/等待触发' : (selected.suggestion || '--') }}</strong></div>
      </div>
      <div class="brooks-evidence">
        <div class="subsection-title">Brooks价格行为证据</div>
        <div v-if="!selected.brooks_tail_enabled" class="brooks-empty">{{ label('brooksStatus', 'BROOKS_DISABLED') }}</div>
        <template v-else>
          <div class="brooks-summary">
            <strong>{{ label('brooksStatus', selected.brooks_status || 'BROOKS_WATCH') }}</strong>
            <span>评分 {{ selected.brooks_tail_score ?? 0 }}/20</span>
            <span>{{ selected.brooks_tail_pass ? '观察结构通过' : '观察结构未通过' }}</span>
            <span>{{ selected.brooks_tail_premium ? '优质结构' : '普通结构' }}</span>
            <span :class="brooksTradeConfirmed(selected) ? 'brooks-ready' : 'brooks-wait'">{{ brooksTradeState(selected) }}</span>
          </div>
          <div class="brooks-grid">
            <div><span>上涨背景</span><strong>{{ label('brooksContext', brooksDetail(selected).context?.context_type || 'INVALID_CONTEXT') }} · {{ passText(brooksDetail(selected).bull_context_pass ?? brooksDetail(selected).context?.passed) }}</strong></div>
            <div><span>卖压衰竭</span><strong>{{ passText(brooksDetail(selected).selling_pressure_exhausted ?? brooksDetail(selected).selling_pressure?.exhausted) }} · 强空方K线 {{ brooksDetail(selected).selling_pressure?.strong_bear_bar_count ?? 0 }} · 跟进 {{ brooksDetail(selected).selling_pressure?.bear_follow_through_count ?? 0 }}</strong></div>
            <div><span>价格稳定</span><strong>{{ passText(brooksDetail(selected).price_stable_pass) }}</strong></div>
            <div><span>量能萎缩</span><strong>{{ passText(brooksDetail(selected).volume_dry_pass) }}</strong></div>
            <div><span>支撑未破</span><strong>{{ passText(brooksDetail(selected).support_not_broken) }}</strong></div>
            <div><span>结构识别</span><strong>{{ joinedLabels('brooksSetup', brooksDetail(selected).structure?.setup_types, ' / ') }}</strong></div>
            <div><span>紧密分类</span><strong>{{ label('brooksCompact', brooksDetail(selected).compact_structure?.structure_type || 'NO_COMPACT') }} · 方向变化 {{ brooksDetail(selected).compact_structure?.direction_change_count ?? 0 }} · 长影线 {{ brooksDetail(selected).compact_structure?.long_shadow_bar_count ?? 0 }}</strong></div>
            <div><span>交易触发</span><strong>{{ brooksTradeState(selected) }} · {{ label('brooksTriggerType', selected.brooks_trade_trigger_type || brooksDetail(selected).trade_trigger?.trigger_type) }} · 触发价 {{ fmt(brooksTriggerPrice(selected)) }} · 有效至 {{ brooksTriggerValidUntil(selected) }}</strong></div>
          </div>
          <div class="tags brooks-tags">
            <span v-for="reason in brooksReasonItems(selected, 'reasons')" :key="'br'+reason" class="tag info">{{ label('tag', reason) }}</span>
            <span v-for="risk in brooksReasonItems(selected, 'risk_tags')" :key="'bk'+risk" class="tag warn">{{ label('tag', risk) }}</span>
            <span v-for="reject in brooksReasonItems(selected, 'reject_reasons')" :key="'bx'+reject" class="tag risk">{{ label('tag', reject) }}</span>
          </div>
        </template>
      </div>
      <div class="tags">
        <span v-for="note in isExecutionWaiting(selected) ? [] : (selected.execution_notes || [])" :key="'e' + note" class="tag info">{{ label('executionNote', note) }}</span>
        <span v-for="reason in selected.setup_quality_reasons || []" :key="'q' + reason" class="tag info">{{ label('tag', reason) }}</span>
        <span v-for="reason in selected.support_reaction_reasons || []" :key="'u' + reason" class="tag info">{{ label('tag', reason) }}</span>
        <span v-for="tag in selected.setup_quality_risk_tags || []" :key="'qr' + tag" class="tag warn">{{ label('tag', tag) }}</span>
        <span v-for="tag in selected.support_reaction_risk_tags || []" :key="'ur' + tag" class="tag warn">{{ label('tag', tag) }}</span>
        <span v-for="tag in selected.risk_tags || []" :key="'r' + tag" class="tag risk">{{ label('tag', tag) }}</span>
        <span v-for="tag in selected.warn_tags || []" :key="'w' + tag" class="tag warn">{{ label('tag', tag) }}</span>
        <span v-for="tag in selected.reject_reasons || []" :key="'x' + tag" class="tag risk">{{ label('tag', tag) }}</span>
        <span v-for="tag in selected.score_reasons || []" :key="'s' + tag" class="tag info">{{ label('tag', tag) }}</span>
      </div>
    </section>

    <div class="loading" v-if="loading">加载中...</div>
  </div>
</template>

<script>
import { useApi } from '../composables/useApi.js'
import { downloadCsv } from '../utils/csvExport.js'
import { strategy6Label, strategy6Labels } from '../utils/strategy6Labels.js'

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
      return this.sortedCandidates.filter(c => this.effectiveCandidateType(c) === 'READY_CANDIDATE')
    },
    keyCandidates() {
      return this.sortedCandidates.filter(c => this.effectiveCandidateType(c) === 'KEY_CANDIDATE')
    },
    watchCandidates() {
      return this.sortedCandidates.filter(c => this.effectiveCandidateType(c) === 'WATCH_CANDIDATE')
    },
    candidateGroups() {
      return [
        { type: 'READY_CANDIDATE', title: '就绪候选', items: this.readyCandidates },
        { type: 'KEY_CANDIDATE', title: '重点候选', items: this.keyCandidates },
        { type: 'WATCH_CANDIDATE', title: '观察候选', items: this.watchCandidates },
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
    label(group, value) {
      return strategy6Label(group, value)
    },
    joinedLabels(group, values, separator = ' / ') {
      const translated = strategy6Labels(group, values)
      return translated.length ? translated.join(separator) : '--'
    },
    brooksDetail(candidate) {
      return candidate?.brooks_result && typeof candidate.brooks_result === 'object'
        ? candidate.brooks_result
        : {}
    },
    authoritativePaths(candidate) {
      if (Array.isArray(candidate?.tail_paths)) return candidate.tail_paths
      const paths = []
      if (candidate?.original_tail_pass) paths.push('ORIGINAL')
      if (candidate?.box_tail_pass) paths.push('BOX')
      return paths
    },
    authoritativeSummary(candidate) {
      if (candidate?.tail_path_summary) return candidate.tail_path_summary
      const paths = this.authoritativePaths(candidate)
      if (paths.length > 1) return 'MULTI'
      return paths[0] || 'NONE'
    },
    authoritativePrimary(candidate) {
      if (candidate?.tail_primary_path) return candidate.tail_primary_path
      const paths = this.authoritativePaths(candidate)
      return paths.includes('BOX') ? 'BOX' : (paths[0] || 'NONE')
    },
    passText(value) {
      return value === true ? '通过' : (value === false ? '未通过' : '无数据')
    },
    brooksTradeState(candidate) {
      if (!candidate?.brooks_tail_enabled) return '未启用或旧任务无数据'
      return this.brooksTradeConfirmed(candidate) ? '交易触发已确认' : '观察/等待触发'
    },
    brooksTradeConfirmed(candidate) {
      if (candidate?.brooks_trade_ready !== true) return false
      const detail = this.brooksDetail(candidate)
      if (candidate?.start_grade === 'B' || detail.context?.watch_only === true) return false
      if (detail.compact_structure?.structure_type === 'BARB_WIRE' || detail.compact_structure?.barb_wire_risk === true) return false
      return true
    },
    isBrooksOnlyWaiting(candidate) {
      const paths = this.authoritativePaths(candidate)
      return paths.length === 1 && paths[0] === 'BROOKS' && !this.brooksTradeConfirmed(candidate)
    },
    isExecutionWaiting(candidate) {
      return this.isBrooksOnlyWaiting(candidate) || candidate?.entry_archetype === 'WAIT_BREAKOUT'
    },
    isQualityV2(candidate) {
      return candidate?.score_model_version === 'S6_QUALITY_V2'
    },
    qualityValue(candidate, field) {
      if (!this.isQualityV2(candidate)) return '--'
      return candidate?.[field] ?? '--'
    },
    entryArchetypeText(candidate) {
      return this.isQualityV2(candidate) ? this.label('entryArchetype', candidate?.entry_archetype) : '--'
    },
    effectiveCandidateType(candidate) {
      return this.isExecutionWaiting(candidate) ? 'WATCH_CANDIDATE' : (candidate?.candidate_type || 'WATCH_CANDIDATE')
    },
    candidateTypeText(candidate) {
      return this.label('candidateType', this.effectiveCandidateType(candidate))
    },
    lifecycleText(candidate) {
      return this.isExecutionWaiting(candidate) ? '观察/等待触发' : this.label('lifecycleStatus', candidate?.lifecycle_status)
    },
    executionZoneText(candidate) {
      return this.isExecutionWaiting(candidate) ? '等待触发' : this.priceRange(candidate?.buy_zone_low, candidate?.buy_zone_high)
    },
    brooksTriggerPrice(candidate) {
      const detail = this.brooksDetail(candidate)
      const trigger = detail.trade_trigger || {}
      const structure = detail.structure || {}
      const triggerType = candidate?.brooks_trade_trigger_type || trigger.trigger_type || ''
      const firstValid = values => values.find(value => value != null && value !== '' && Number.isFinite(Number(value)))
      const generic = firstValid([candidate?.brooks_trigger_price, trigger.trigger_price])
      if (generic != null) return Number(generic)
      if (triggerType !== 'BROOKS_SUPPORT_READY') return null
      const legacySecondEntry = firstValid([structure.second_entry_trigger_price])
      return legacySecondEntry == null ? null : Number(legacySecondEntry)
    },
    brooksTriggerValidUntil(candidate) {
      return candidate?.brooks_trigger_valid_until || this.brooksDetail(candidate).trade_trigger?.trigger_valid_until || '--'
    },
    brooksReasonItems(candidate, key) {
      const detail = this.brooksDetail(candidate)
      const groups = [detail, detail.context, detail.selling_pressure, detail.structure, detail.compact_structure, detail.trade_trigger]
      return [...new Set(groups.flatMap(group => Array.isArray(group?.[key]) ? group[key] : []))]
    },
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
    tailVolumeDisplay(candidate, detailed = false) {
      const tailAvg = Number(candidate?.tail_avg_volume)
      const baselineAvg = Number(candidate?.pre_tail_avg_volume_20)
      const ratio = Number(candidate?.tail_volume_ratio)
      const hasTailMeasurement = (
        Number.isFinite(tailAvg) && tailAvg > 0
        && Number.isFinite(baselineAvg) && baselineAvg > 0
        && Number.isFinite(ratio)
      )
      if (hasTailMeasurement) {
        if (!detailed) return this.fmt(ratio, 3)
        return `尾段 ${this.fmt(tailAvg, 0)} · 前置20日 ${this.fmt(baselineAvg, 0)} · 比值 ${this.fmt(ratio, 3)}`
      }
      const rawV5v20 = candidate?.volume_ratio_5_20
      if (rawV5v20 != null && rawV5v20 !== '') {
        const v5v20 = Number(rawV5v20)
        if (Number.isFinite(v5v20)) return `未形成尾段（V5/V20 ${this.fmt(v5v20, 3)}）`
      }
      return '未形成尾段'
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
      const type = this.effectiveCandidateType(c)
      if (type === 'READY_CANDIDATE') return 'ready'
      if (type === 'KEY_CANDIDATE') return 'key'
      if (type === 'WATCH_CANDIDATE') return 'watch'
      return 'rejected'
    },
    marketDataStatusText(status) {
      return this.label('marketDataStatus', status || 'MISSING')
    },
    exportCandidates() {
      downloadCsv({
        filename: `strategy6-candidates-${this.selectedTaskId || 'latest'}.csv`,
        columns: [
          { header: '代码', value: c => c.code },
          { header: '名称', value: c => c.name },
          { header: '板块', value: c => c.sector_name || '' },
          { header: '候选类型', value: c => this.candidateTypeText(c) },
          { header: '候选类型原始值', value: c => this.effectiveCandidateType(c) },
          { header: '生命周期', value: c => this.lifecycleText(c) },
          { header: '生命周期原始值', value: c => this.isExecutionWaiting(c) ? 'SETUP_FORMING' : (c.lifecycle_status || '') },
          { header: '首次入池', value: c => c.first_pool_date || '' },
          { header: '池龄交易日', value: c => c.pool_age_trading_days ?? '' },
          { header: '策略版本', value: c => c.strategy_version || '' },
          { header: '评分模型版本', value: c => c.score_model_version || '' },
          { header: '入场类型', value: c => this.entryArchetypeText(c) === '--' ? '' : this.entryArchetypeText(c) },
          { header: '入场类型原始值', value: c => this.isQualityV2(c) ? (c.entry_archetype || '') : '' },
          { header: '启动事件质量分', value: c => this.isQualityV2(c) ? (c.start_event_quality_score ?? '') : '' },
          { header: '整理质量分', value: c => this.isQualityV2(c) ? (c.setup_quality_score ?? '') : '' },
          { header: '支撑反应分', value: c => this.isQualityV2(c) ? (c.support_reaction_score ?? '') : '' },
          { header: '路径证据分', value: c => this.isQualityV2(c) ? (c.path_evidence_score ?? '') : '' },
          { header: '尾段划分', value: c => this.isQualityV2(c) ? this.label('tailSegmentationStatus', c.tail_segmentation_status) : '' },
          { header: '尾段划分原始值', value: c => this.isQualityV2(c) ? (c.tail_segmentation_status || '') : '' },
          { header: '尾段划分分数', value: c => this.isQualityV2(c) ? (c.tail_segmentation_score ?? '') : '' },
          { header: '阶段状态', value: c => this.label('phaseStatus', c.phase_status) },
          { header: '阶段状态原始值', value: c => c.phase_status || '' },
          { header: '形态类型', value: c => this.label('patternType', c.pattern_type) },
          { header: '形态类型原始值', value: c => c.pattern_type || '' },
          { header: '总分', value: c => c.total_score ?? '' },
          { header: '市场过滤', value: c => c.enable_market_filter ? '开启' : '关闭' },
          { header: '市场过滤模式', value: c => this.label('marketFilterMode', c.market_filter_mode) },
          { header: '市场过滤模式原始值', value: c => c.market_filter_mode || '' },
          { header: '市场状态', value: c => this.label('marketStatus', c.market_status) },
          { header: '市场状态原始值', value: c => c.market_status || '' },
          { header: 'RS20', value: c => this.pct(c.relative_strength_20) },
          { header: '现价', value: c => this.fmt(c.current_price) },
          { header: '日涨跌', value: c => this.pct(c.daily_return) },
          { header: '5日涨幅', value: c => this.pct(c.return_5) },
          { header: '10日涨幅', value: c => this.pct(c.return_10) },
          { header: '20日涨幅', value: c => this.pct(c.return_20) },
          { header: '启动日', value: c => c.start_date || '' },
          { header: '启动类型', value: c => this.label('startType', c.start_type) },
          { header: '启动类型原始值', value: c => c.start_type || '' },
          { header: '启动等级', value: c => c.start_grade || '' },
          { header: '启动日低点', value: c => this.fmt(c.start_low) },
          { header: '启动后天数', value: c => c.days_since_start ?? '' },
          { header: '支撑状态', value: c => this.label('supportStatus', c.support_status) },
          { header: '支撑状态原始值', value: c => c.support_status || '' },
          { header: '关键支撑', value: c => this.fmt(c.key_support_price) },
          { header: '前置支撑', value: c => this.fmt(c.prior_key_support_price) },
          { header: '战术支撑', value: c => this.fmt(c.tactical_support_price) },
          { header: '支撑区低', value: c => this.fmt(c.support_zone_low) },
          { header: '支撑区高', value: c => this.fmt(c.support_zone_high) },
          { header: '建议买入价', value: c => this.isExecutionWaiting(c) ? this.executionZoneText(c) : this.fmt(c.suggested_buy_price) },
          { header: '买入区低', value: c => this.isExecutionWaiting(c) ? '' : this.fmt(c.buy_zone_low) },
          { header: '买入区高', value: c => this.isExecutionWaiting(c) ? '' : this.fmt(c.buy_zone_high) },
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
          { header: '箱体状态', value: c => this.label('boxStatus', c.box_status) },
          { header: '箱体状态原始值', value: c => c.box_status || '' },
          { header: '尾部通过', value: c => c.tail_pass ? '是' : '否' },
          { header: '尾部路径', value: c => this.label('tailPath', c.tail_path) },
          { header: '尾部路径原始值', value: c => c.tail_path || '' },
          { header: '权威路径汇总', value: c => this.label('tailPathSummary', this.authoritativeSummary(c)) },
          { header: '权威路径汇总原始值', value: c => this.authoritativeSummary(c) },
          { header: '主路径', value: c => this.label('tailPrimaryPath', this.authoritativePrimary(c)) },
          { header: '主路径原始值', value: c => this.authoritativePrimary(c) },
          { header: '通过路径', value: c => strategy6Labels('tailPrimaryPath', this.authoritativePaths(c)).join('|') },
          { header: '通过路径原始值', value: c => this.authoritativePaths(c).join('|') },
          { header: '通过路径数', value: c => c.passed_path_count ?? this.authoritativePaths(c).length },
          { header: '多路径确认', value: c => c.multi_path_confirmed ? '是' : '否' },
          { header: 'Brooks路径启用', value: c => c.brooks_tail_enabled ? '是' : '否' },
          { header: 'Brooks通过', value: c => c.brooks_tail_pass ? '是' : '否' },
          { header: 'Brooks分', value: c => c.brooks_tail_score ?? '' },
          { header: 'Brooks优质', value: c => c.brooks_tail_premium ? '是' : '否' },
          { header: 'Brooks状态', value: c => this.label('brooksStatus', c.brooks_status || 'BROOKS_DISABLED') },
          { header: 'Brooks状态原始值', value: c => c.brooks_status || 'BROOKS_DISABLED' },
          { header: 'Brooks交易状态', value: c => this.brooksTradeState(c) },
          { header: 'Brooks触发类型', value: c => this.label('brooksTriggerType', c.brooks_trade_trigger_type) },
          { header: 'Brooks触发类型原始值', value: c => c.brooks_trade_trigger_type || '' },
          { header: 'Brooks触发有效期', value: c => this.brooksTriggerValidUntil(c) === '--' ? '' : this.brooksTriggerValidUntil(c) },
          { header: '上涨背景', value: c => this.passText(this.brooksDetail(c).bull_context_pass ?? this.brooksDetail(c).context?.passed) },
          { header: '卖压衰竭', value: c => this.passText(this.brooksDetail(c).selling_pressure_exhausted ?? this.brooksDetail(c).selling_pressure?.exhausted) },
          { header: '价格稳定', value: c => this.passText(this.brooksDetail(c).price_stable_pass) },
          { header: '量能萎缩', value: c => this.passText(this.brooksDetail(c).volume_dry_pass) },
          { header: '支撑未破', value: c => this.passText(this.brooksDetail(c).support_not_broken) },
          { header: 'Brooks背景', value: c => this.label('brooksContext', this.brooksDetail(c).context?.context_type) },
          { header: 'Brooks背景原始值', value: c => this.brooksDetail(c).context?.context_type || '' },
          { header: 'Brooks结构', value: c => strategy6Labels('brooksSetup', this.brooksDetail(c).structure?.setup_types).join('|') },
          { header: 'Brooks结构原始值', value: c => (this.brooksDetail(c).structure?.setup_types || []).join('|') },
          { header: 'Brooks紧密分类', value: c => this.label('brooksCompact', this.brooksDetail(c).compact_structure?.structure_type) },
          { header: 'Brooks紧密分类原始值', value: c => this.brooksDetail(c).compact_structure?.structure_type || '' },
          { header: 'Brooks触发价', value: c => this.fmt(this.brooksTriggerPrice(c)) },
          { header: 'Brooks原因', value: c => strategy6Labels('tag', this.brooksReasonItems(c, 'reasons')).join('|') },
          { header: 'Brooks原因原始值', value: c => this.brooksReasonItems(c, 'reasons').join('|') },
          { header: 'Brooks风险', value: c => strategy6Labels('tag', this.brooksReasonItems(c, 'risk_tags')).join('|') },
          { header: 'Brooks风险原始值', value: c => this.brooksReasonItems(c, 'risk_tags').join('|') },
          { header: 'Brooks否决原因', value: c => strategy6Labels('tag', this.brooksReasonItems(c, 'reject_reasons')).join('|') },
          { header: 'Brooks否决原因原始值', value: c => this.brooksReasonItems(c, 'reject_reasons').join('|') },
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
          { header: '箱体跌破原因', value: c => c.box_break_reason ? this.label('tag', c.box_break_reason) : '' },
          { header: '箱体跌破原因原始值', value: c => c.box_break_reason || '' },
          { header: '箱体选择原因', value: c => c.box_selection_reason ? this.label('tag', c.box_selection_reason) : '' },
          { header: '箱体选择原因原始值', value: c => c.box_selection_reason || '' },
          { header: '紧密排列启用', value: c => c.compact_kline_enabled ? '是' : '否' },
          { header: '紧密排列通过', value: c => c.compact_kline_pass ? '是' : '否' },
          { header: '紧密排列分', value: c => c.compact_kline_score ?? '' },
          { header: '箱体质量分', value: c => c.box_quality_score ?? '' },
          { header: '箱体质量标签', value: c => this.label('boxQualityTag', c.box_quality_tag) },
          { header: '箱体质量标签原始值', value: c => c.box_quality_tag || '' },
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
          { header: '紧密排列原因', value: c => strategy6Labels('tag', c.compact_kline_reasons).join('|') },
          { header: '紧密排列原因原始值', value: c => (c.compact_kline_reasons || []).join('|') },
          { header: '紧密排列风险', value: c => strategy6Labels('tag', c.compact_kline_risk_tags).join('|') },
          { header: '紧密排列风险原始值', value: c => (c.compact_kline_risk_tags || []).join('|') },
          { header: '启动分', value: c => c.strong_start_score ?? '' },
          { header: '支撑分', value: c => c.support_score ?? '' },
          { header: '量干分', value: c => c.dry_stable_score ?? '' },
          { header: '盈亏比分', value: c => c.risk_reward_score ?? '' },
          { header: '风控分', value: c => c.risk_control_score ?? '' },
          { header: '风险标签', value: c => strategy6Labels('tag', c.risk_tags).join('|') },
          { header: '风险标签原始值', value: c => (c.risk_tags || []).join('|') },
          { header: '警告标签', value: c => strategy6Labels('tag', c.warn_tags).join('|') },
          { header: '警告标签原始值', value: c => (c.warn_tags || []).join('|') },
          { header: '否决原因', value: c => strategy6Labels('tag', c.reject_reasons).join('|') },
          { header: '否决原因原始值', value: c => (c.reject_reasons || []).join('|') },
          { header: '建议', value: c => this.isExecutionWaiting(c) ? this.lifecycleText(c) : (c.suggestion || '') },
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
.brooks-evidence { margin: 0 14px 14px; padding: 14px; border: 1px solid rgba(77, 163, 255, 0.25); border-radius: 8px; background: rgba(77, 163, 255, 0.04); }
.subsection-title { color: var(--text-primary); font-weight: 700; margin-bottom: 10px; }
.brooks-empty { color: var(--text-secondary); }
.brooks-summary { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; margin-bottom: 12px; color: var(--text-secondary); }
.brooks-summary strong { color: var(--text-primary); }
.brooks-ready { color: #36b37e; font-weight: 700; }
.brooks-wait { color: #e6a23c; font-weight: 700; }
.brooks-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }
.brooks-grid div { display: flex; flex-direction: column; gap: 3px; }
.brooks-grid span { color: var(--text-secondary); font-size: 12px; }
.brooks-grid strong { color: var(--text-primary); }
.brooks-tags { margin-top: 10px; }
.tags { padding: 0 14px; }
.empty, .loading, .error-banner { padding: 16px; color: var(--text-secondary); }
.error-banner { border: 1px solid rgba(239,68,68,0.4); color: #fca5a5; background: rgba(239,68,68,0.08); border-radius: 6px; }
</style>
