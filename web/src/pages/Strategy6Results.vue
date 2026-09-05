<template>
  <div class="strategy6-results">
    <div class="page-header">
      <div class="page-title-block">
        <span class="terminal-kicker">STRATEGY 6 / SIGNAL DESK</span>
        <h1>策略6 · 强势 VCP 尾部候选池</h1>
        <p>强势启动后有支撑横盘，尾部价稳量干且盈亏比合格的候选池。</p>
      </div>
      <div class="header-controls">
      <div ref="taskPicker" class="task-picker" @click.stop>
        <button
          data-test="strategy6-task-trigger"
          class="task-select-trigger"
          :aria-expanded="taskDropdownOpen"
          @click="taskDropdownOpen = !taskDropdownOpen"
        >
          <span>{{ selectedTask ? taskDisplayText(selectedTask) : '选择策略6任务' }}</span>
          <span class="task-select-arrow">{{ taskDropdownOpen ? '▲' : '▼' }}</span>
        </button>
        <div v-if="taskDropdownOpen" data-test="strategy6-task-dropdown" class="task-dropdown">
          <div class="task-options">
            <button
              v-for="task in pagedTasks"
              :key="task.id"
              :data-test="`strategy6-task-option-${task.id}`"
              class="task-option"
              :class="{ selected: task.id === selectedTaskId }"
              @click="selectTask(task)"
            >{{ taskDisplayText(task) }}</button>
            <div v-if="!pagedTasks.length" class="task-option-empty">暂无策略6任务</div>
          </div>
          <div v-if="tasks.length > taskPageSize" class="task-pagination">
            <button
              data-test="strategy6-task-prev"
              :disabled="taskPage <= 1"
              @click="changeTaskPage(-1)"
            >上一页</button>
            <span data-test="strategy6-task-page-info">第 {{ taskPage }} / {{ taskPageCount }} 页 · 共 {{ tasks.length }} 个任务</span>
            <button
              data-test="strategy6-task-next"
              :disabled="taskPage >= taskPageCount"
              @click="changeTaskPage(1)"
            >下一页</button>
          </div>
        </div>
      </div>
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
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <div class="summary-bar" v-if="candidates.length">
      <span>候选数 <strong>{{ tradingCandidates.length }}</strong></span>
      <span class="chip vcp">VCP观察 {{ vcpCandidates.length }}</span>
      <span class="chip ready">就绪 {{ readyCandidates.length }}</span>
      <span class="chip key">重点 {{ keyCandidates.length }}</span>
      <span class="chip watch">观察 {{ watchCandidates.length }}</span>
      <span>最高分 {{ topScore }}</span>
      <span>最高RR2 {{ topRr2 }}</span>
    </div>

    <div class="empty" v-if="!loading && !selectedTaskId">请选择一个策略6任务查看结果。</div>
    <div class="empty" v-else-if="!loading && selectedTaskId && !candidates.length && !trendSqueezeScreen.length">当前任务没有策略6候选。</div>

    <section v-if="marketSnapshot" class="panel market-panel">
      <div class="panel-header">
        <span>市场过滤数据</span>
        <strong class="market-state">{{ label('marketStatus', marketSnapshot.market_status || 'UNKNOWN') }}</strong>
      </div>
      <div class="market-summary">
        <span>20日市场涨幅 <strong>{{ pct(marketSnapshot.market_return_20) }}</strong></span>
        <span v-for="reason in marketSnapshot.market_reasons || []" :key="reason" class="tag info">{{ label('marketReason', reason) }}</span>
      </div>
      <div class="market-index-grid">
        <article v-for="idx in marketIndexes" :key="`pulse-${idx.symbol}`" class="market-index-card">
          <div class="index-card-head">
            <div><strong>{{ idx.name || idx.symbol }}</strong><span>{{ idx.symbol }}</span></div>
            <span class="data-state" :class="{ fresh: idx.data_status === 'FRESH' }">{{ marketDataStatusText(idx.data_status) }}</span>
          </div>
          <div class="index-price">{{ fmt(idx.latest_close) }}</div>
          <div class="index-return" :class="{ up: Number(idx.return_20) >= 0, down: Number(idx.return_20) < 0 }">
            20日 {{ pct(idx.return_20) }}
          </div>
          <div class="index-meta">
            <span>MA20 {{ fmt(idx.ma20) }}</span>
            <span>MA50 {{ fmt(idx.ma50) }}</span>
            <span>{{ idx.latest_date || '--' }}</span>
          </div>
        </article>
      </div>
      <details class="market-raw-data">
        <summary>查看四指数原始数据与抓取审计</summary>
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
      </details>
    </section>

    <section v-if="selectedTaskId" class="panel trend-squeeze-screen-panel">
      <div class="panel-header">
        <span>强势趋势收缩初筛池</span>
        <div class="panel-header-actions">
          <span class="panel-count">{{ trendSqueezeScreen.length }}</span>
          <button
            data-test="export-trend-squeeze-screen"
            class="export-btn"
            :disabled="!trendSqueezeScreen.length"
            @click="exportTrendSqueezeScreen"
          >下载初筛股票</button>
        </div>
      </div>
      <div class="panel-note">独立保存通过“强势趋势 + 高位波动收缩”七项门槛的全部股票；不代表已通过强势启动、尾部、支撑和盈亏比主链。</div>
      <div v-if="trendSqueezeScreen.length" class="table-scroll">
        <table class="trend-screen-table">
          <thead>
            <tr>
              <th>股票</th><th>评价日</th><th>现价</th><th>EMA150 / EMA200</th><th>52周低 / 高</th>
              <th>距低点 / 高位比</th><th>BB / KC</th><th>后续主链结果</th><th>后续拦截原因</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stock in trendSqueezeScreen" :key="`trend-screen-${stock.code}`" :data-test="`trend-screen-row-${stock.code}`">
              <td><span class="code">{{ stock.code }}</span> {{ stock.name }}</td>
              <td>{{ stock.evaluation_date || '--' }}</td>
              <td>{{ fmt(stock.trend_close) }}</td>
              <td>{{ fmt(stock.trend_ema150) }} / {{ fmt(stock.trend_ema200) }}</td>
              <td>{{ fmt(stock.trend_low_250) }} / {{ fmt(stock.trend_high_250) }}</td>
              <td>{{ pct(Number(stock.trend_close_to_low_ratio || 0) - 1) }} / {{ pct(stock.trend_close_to_high_ratio) }}</td>
              <td>BB {{ priceRange(stock.trend_bb_lower, stock.trend_bb_upper) }}<br><span class="muted">KC {{ priceRange(stock.trend_kc_lower, stock.trend_kc_upper) }}</span></td>
              <td>{{ trendScreenOutcomeText(stock) }}</td>
              <td>{{ joinedLabels('tag', stock.downstream_reject_reasons) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="panel-empty">该任务未生成独立初筛池；旧任务需要重新扫描策略6。</div>
    </section>

    <section v-for="group in candidateGroups" :key="group.type" class="panel">
      <div class="panel-header"><span>{{ group.title }}</span><span class="panel-count">{{ group.items.length }}</span></div>
      <div class="table-scroll">
        <table class="candidate-table">
          <thead>
            <tr>
              <th>股票</th><th>现价</th><th>总分</th><th>TTM状态</th><th>入场/质量</th><th>分类</th><th>生命周期</th>
              <th>启动类型/等级</th><th>支撑状态</th><th>关键/前置支撑</th><th>执行区间/状态</th>
              <th>止损</th><th>客观目标1/2</th><th>客观RR2</th><th>形态</th><th>实体支撑底评分</th><th>最新交易日K线形态</th><th>权威路径/Brooks</th><th>尾段/前20量比</th><th>连续收跌结构</th><th>市场/RS</th><th>入池</th><th>风险/警告</th><th>数据日</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in group.items" :key="c.code" :data-test="`candidate-row-${c.code}`" class="clickable" @click="selected = c">
              <td><span class="code">{{ c.code }}</span> {{ c.name }}</td>
              <td>{{ fmt(c.current_price) }}</td>
              <td class="score">{{ fmt(c.total_score, 0) }}</td>
              <td :data-test="`candidate-ttm-${c.code}`">{{ ttmSummary(c) }}</td>
              <td>
                <div>{{ entryArchetypeText(c) }}</div>
                <div class="muted">整理 {{ qualityValue(c, 'setup_quality_score') }} · 支撑 {{ qualityValue(c, 'support_reaction_score') }}</div>
              </td>
              <td>
                <span :data-test="`candidate-type-${c.code}`" class="type-badge" :class="classFor(c)">{{ candidateTypeText(c) }}</span>
                <div v-if="marketDowngradeText(c)" class="downgrade-note">{{ marketDowngradeText(c) }}</div>
              </td>
              <td :data-test="`candidate-lifecycle-${c.code}`">{{ lifecycleText(c) }}</td>
              <td>{{ label('startType', c.start_type) }} / {{ label('startGrade', c.start_grade) }}</td>
              <td>{{ label('supportStatus', c.support_status) }}</td>
              <td>{{ fmt(c.key_support_price) }} / {{ fmt(c.prior_key_support_price) }}</td>
              <td :data-test="`candidate-buy-zone-${c.code}`">{{ executionZoneText(c) }}</td>
              <td>{{ fmt(c.stop_loss_price) }}</td>
              <td>{{ fmt(c.objective_target_1 ?? c.target_price_1) }} / {{ fmt(c.objective_target_2 ?? c.target_price_2) }}</td>
              <td class="rr">{{ fmt(c.objective_rr_2 ?? c.risk_reward_ratio_2) }}</td>
              <td>{{ label('patternType', c.pattern_type || 'UNKNOWN') }}</td>
              <td :data-test="`candidate-body-support-${c.code}`">{{ bodySupportSummary(c) }}</td>
              <td :data-test="`candidate-latest-pattern-${c.code}`">{{ latestBarPatternSummary(c) }}</td>
              <td>
                <div>{{ label('tailPathSummary', authoritativeSummary(c)) }}</div>
                <div class="muted">主路径 {{ label('tailPrimaryPath', authoritativePrimary(c)) }}</div>
                <div v-if="c.brooks_tail_enabled" class="muted">{{ label('brooksStatus', c.brooks_status || 'BROOKS_WATCH') }} · {{ brooksTradeState(c) }}</div>
                <div v-else class="muted">旧路径 {{ label('tailPath', c.tail_path || 'NONE') }}</div>
              </td>
              <td>{{ tailVolumeDisplay(c) }}</td>
              <td :data-test="`candidate-consecutive-down-${c.code}`">{{ consecutiveDownStructureText(c) }}</td>
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

    <section v-for="group in vcpGroups" :key="group.key" class="panel vcp-panel">
      <div class="panel-header"><span>{{ group.title }}</span><span class="panel-count">{{ group.rows.length }}</span></div>
      <template v-if="group.rows.length">
        <div class="panel-note">仅跟踪本轮VCP起点后曾进入策略6正式候选的股票；过度延伸只保留跟踪，不代表立即买入。</div>
        <div v-if="vcpQualityNotice" class="panel-note">{{ vcpQualityNotice }}</div>
        <div class="table-scroll">
        <table class="candidate-table vcp-table">
          <thead>
            <tr>
              <th>股票</th><th>VCP形态分/等级</th><th>VCP状态</th><th>收缩次数</th><th>VCP支点</th><th>结构低点</th>
              <th>距支点</th><th>突破日期</th><th>实体支撑底评分</th><th>最新交易日K线形态</th><th>连续收跌结构</th><th>历史正式候选</th><th>策略总分</th><th>TTM状态</th><th>原交易分类</th><th>风险提示</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in group.rows"
              :key="c.code"
              :data-test="`vcp-row-${c.code}`"
              class="clickable"
              @click="selected = c"
            >
              <td><span class="code">{{ c.code }}</span> {{ c.name }}</td>
              <td>
                <template v-if="hasVcpQuality(c)">
                  <strong class="score">{{ c.vcp_quality_score }}分</strong>
                  <div class="muted">{{ label('vcpQualityGrade', c.vcp_quality_grade) }}</div>
                </template>
                <span v-else class="muted">未评分</span>
              </td>
              <td>{{ label('vcpStatus', c.vcp_lifecycle_status) }}</td>
              <td>{{ c.vcp_contraction_count ?? 0 }}</td>
              <td>{{ fmt(c.vcp_pivot_price) }}</td>
              <td>{{ fmt(c.vcp_structure_low) }}</td>
              <td>{{ pct(c.vcp_distance_to_pivot_pct) }}</td>
              <td>{{ c.vcp_breakout_date || '--' }}</td>
              <td :data-test="`vcp-body-support-${c.code}`">{{ bodySupportSummary(c) }}</td>
              <td :data-test="`vcp-latest-pattern-${c.code}`">{{ latestBarPatternSummary(c) }}</td>
              <td :data-test="`vcp-consecutive-down-${c.code}`">{{ consecutiveDownStructureText(c) }}</td>
              <td>
                <div>{{ c.vcp_history_candidate_date || '--' }} · {{ label('candidateType', c.vcp_history_candidate_type) }}</div>
                <div class="muted">{{ fmt(c.vcp_history_candidate_score, 0) }}分 · {{ label('source', c.vcp_history_source) }}</div>
              </td>
              <td class="score">{{ fmt(c.total_score, 0) }}</td>
              <td :data-test="`vcp-ttm-${c.code}`">{{ ttmSummary(c) }}</td>
              <td>{{ candidateTypeText(c) }}</td>
              <td>
                <span v-for="tag in c.vcp_observation_risk_tags || []" :key="tag" class="tag warn">{{ label('tag', tag) }}</span>
                <span v-if="!(c.vcp_observation_risk_tags || []).length" class="muted">--</span>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </template>
      <div v-else class="panel-empty">{{ group.emptyMessage }}</div>
    </section>

    <section v-if="vcpExitAuditRows.length" class="panel vcp-audit-panel">
      <div class="panel-header">VCP观察退出审计</div>
      <div class="table-scroll">
        <table class="lifecycle-table">
          <thead><tr><th>股票</th><th>VCP状态</th><th>评估日期</th><th>失效/退出原因</th></tr></thead>
          <tbody>
            <tr v-for="row in vcpExitAuditRows" :key="`vcp-exit-${row.code}`">
              <td><span class="code">{{ row.code }}</span> {{ row.name }}</td>
              <td>{{ label('vcpStatus', row.vcp_lifecycle_status) }}</td>
              <td>{{ row.evaluation_date || '--' }}</td>
              <td>{{ vcpExitReasonText(row) }}</td>
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

    <section v-if="selected" class="panel detail-panel">
      <div class="panel-header">候选详情 · {{ selected.code }} {{ selected.name }}</div>
      <div class="detail-grid">
        <div v-if="selected.vcp_observation_eligible"><span>VCP生命周期</span><strong>{{ label('vcpStatus', selected.vcp_lifecycle_status) }} · {{ selected.vcp_pattern_start_date || '--' }} 至 {{ selected.vcp_pattern_end_date || '--' }}</strong></div>
        <div v-if="selected.vcp_observation_eligible"><span>VCP关键位</span><strong>支点 {{ fmt(selected.vcp_pivot_price) }} · 结构低点 {{ fmt(selected.vcp_structure_low) }} · 距支点 {{ pct(selected.vcp_distance_to_pivot_pct) }}</strong></div>
        <div v-if="selected.vcp_observation_eligible"><span>VCP突破</span><strong>{{ selected.vcp_breakout_date || '--' }} · 突破后 {{ selected.vcp_days_since_breakout ?? 0 }} 个交易日</strong></div>
        <div><span>分类</span><strong>{{ candidateTypeText(selected) }} / {{ isExecutionWaiting(selected) ? '观察' : label('classification', selected.classification) }}</strong></div>
        <div data-test="detail-decision-profile"><span>决策规则</span><strong>{{ decisionProfileText(selected) }} · {{ selected.score_model_version || '--' }}</strong></div>
        <div data-test="detail-strong-trend-squeeze"><span>独立强势趋势收缩初筛</span><strong>{{ strongTrendSqueezeSummary(selected) }}</strong></div>
        <div data-test="detail-body-support"><span>实体支撑底评分</span><strong>{{ bodySupportDetail(selected) }}</strong></div>
        <div data-test="detail-latest-bar-pattern"><span>最新交易日K线形态</span><strong>{{ latestBarPatternDetail(selected) }}</strong></div>
        <div v-if="hasStrongTrendSqueezeData(selected)" data-test="detail-trend-position"><span>52周位置</span><strong>低 {{ fmt(selected.trend_low_250) }} · 现 {{ fmt(selected.trend_close) }} · 高 {{ fmt(selected.trend_high_250) }} · 高位比 {{ pct(selected.trend_close_to_high_ratio) }}</strong></div>
        <div v-if="hasStrongTrendSqueezeData(selected)" data-test="detail-trend-ema"><span>长期EMA</span><strong>EMA150 {{ fmt(selected.trend_ema150) }} · EMA200 {{ fmt(selected.trend_ema200) }}</strong></div>
        <div v-if="hasStrongTrendSqueezeData(selected)" data-test="detail-trend-bands"><span>正式收缩通道</span><strong>BB {{ priceRange(selected.trend_bb_lower, selected.trend_bb_upper) }} · Keltner {{ priceRange(selected.trend_kc_lower, selected.trend_kc_upper) }}</strong></div>
        <div data-test="detail-ttm-squeeze"><span>TTM Squeeze</span><strong>{{ ttmDetail(selected) }}</strong></div>
        <div data-test="detail-ttm-bands"><span>TTM波动通道</span><strong>{{ ttmBandsDetail(selected) }}</strong></div>
        <div data-test="detail-ttm-momentum"><span>TTM动量</span><strong>{{ ttmMomentumDetail(selected) }}</strong></div>
        <div v-if="hasTtmData(selected)"><span>TTM原因/风险</span><strong>{{ joinedLabels('tag', [...(selected.ttm_reasons || []), ...(selected.ttm_risk_tags || [])]) }}</strong></div>
        <div v-if="selected.decision_profile === 'formal_original'"><span>研究模块</span><strong>稳定箱体 / Brooks / 质量V2 未参与正式选股</strong></div>
        <div v-if="marketDowngradeText(selected)" data-test="detail-market-downgrade"><span>市场降级前等级</span><strong>{{ marketDowngradeText(selected) }}</strong></div>
        <div><span>生命周期</span><strong>{{ lifecycleText(selected) }}</strong></div>
        <div><span>强势启动</span><strong>{{ label('startType', selected.start_type) }} / {{ label('startGrade', selected.start_grade) }} / {{ pct(selected.start_day_return) }} · 启动后{{ selected.days_since_start ?? 0 }}日</strong></div>
        <div><span>近20日高位确认</span><strong>{{ highTriggerText(selected.high_trigger) }}</strong></div>
        <div><span>启动日低点</span><strong>{{ fmt(selected.start_low) }}</strong></div>
        <div><span>支撑</span><strong>{{ label('supportStatus', selected.support_status) }} · {{ selected.main_support_ma || '--' }} · 测试{{ selected.support_test_count ?? 0 }}次</strong></div>
        <div><span>战术价格</span><strong>支撑 {{ fmt(selected.key_support_price) }} · 前置支撑 {{ fmt(selected.prior_key_support_price) }} · 止损 {{ fmt(selected.stop_loss_price) }}</strong></div>
        <div data-test="detail-execution-zone"><span>{{ isExecutionWaiting(selected) ? '入场状态' : '买入区' }}</span><strong>{{ executionZoneText(selected) }}</strong></div>
        <div data-test="detail-entry-archetype"><span>入场类型</span><strong>{{ entryArchetypeText(selected) }}</strong></div>
        <div data-test="detail-entry-timing"><span>入场时机</span><strong>{{ entryTimingDetail(selected) }}</strong></div>
        <div data-test="detail-probability-rr"><span>概率修正RR</span><strong>{{ probabilityRrDetail(selected) }}</strong></div>
        <div><span>阶段</span><strong>{{ label('phaseStatus', selected.phase_status) }} · 整理 {{ selected.consolidation_start_date || '--' }} · 尾段 {{ selected.tail_start_date || '--' }} · {{ hasTailSegmentation(selected) ? label('tailSegmentationStatus', selected.tail_segmentation_status) : '--' }}</strong></div>
        <div><span>形态</span><strong>{{ label('patternType', selected.pattern_type || 'UNKNOWN') }} · {{ label('pivotSource', selected.pivot_source) }} · 收缩{{ selected.contraction_count ?? 0 }}次</strong></div>
        <div data-test="detail-consecutive-down-structure"><span>连续收跌结构</span><strong>{{ consecutiveDownStructureDetail(selected) }}</strong></div>
        <div><span>支撑簇</span><strong>战术 {{ fmt(selected.tactical_support_price) }} · {{ joinedLabels('supportSource', selected.support_cluster_sources, ' / ') }}</strong></div>
        <div><span>客观目标</span><strong>{{ fmt(selected.objective_target_1 ?? selected.target_price_1) }} / {{ fmt(selected.objective_target_2 ?? selected.target_price_2) }} · RR {{ fmt(selected.objective_rr_1 ?? selected.risk_reward_ratio_1) }} / {{ fmt(selected.objective_rr_2 ?? selected.risk_reward_ratio_2) }}</strong></div>
        <div><span>执行R目标</span><strong>1.5R {{ fmt(selected.execution_target_1_5r) }} · 2R {{ fmt(selected.execution_target_2r) }} · 2.5R {{ fmt(selected.execution_target_2_5r) }} · 3.5R {{ fmt(selected.execution_target_3_5r) }}</strong></div>
        <div><span>执行窗口</span><strong>{{ isExecutionWaiting(selected) ? '等待交易触发确认' : `${selected.valid_from_date || '--'} 至 ${selected.valid_until_date || '--'} · 限价 ${fmt(selected.suggested_limit_price)}` }}</strong></div>
        <div data-test="detail-quality-v2"><span>质量诊断</span><strong>启动质量 {{ qualityValue(selected, 'start_event_quality_score') }} · 整理质量 {{ qualityValue(selected, 'setup_quality_score') }} · 支撑反应 {{ qualityValue(selected, 'support_reaction_score') }} · 路径证据 {{ qualityValue(selected, 'path_evidence_score') }}</strong></div>
        <div><span>六维评分</span><strong>启动{{ selected.strong_start_score ?? 0 }} 形态{{ selected.pattern_score_component ?? 0 }} 支撑{{ selected.support_score ?? 0 }} 尾段{{ selected.tail_score ?? 0 }} 客观RR{{ selected.objective_rr_score ?? 0 }} RS/风险{{ selected.relative_strength_risk_score ?? 0 }}</strong></div>
        <div><span>权威三路径</span><strong>{{ label('tailPathSummary', authoritativeSummary(selected)) }} · 主路径 {{ label('tailPrimaryPath', authoritativePrimary(selected)) }} · 通过 {{ joinedLabels('tailPrimaryPath', authoritativePaths(selected), ' / ') }} · {{ selected.multi_path_confirmed ? '多路径确认' : '单路径或未通过' }}</strong></div>
        <div><span>旧尾部路径（原始/箱体）</span><strong>{{ label('tailPath', selected.tail_path || 'NONE') }} · 原路径 {{ selected.original_tail_pass ? '通过' : '未通过' }}/{{ selected.original_tail_score ?? 0 }} · {{ selected.box_tail_enabled ? `箱体 ${selected.box_tail_pass ? '通过' : '未通过'}/${selected.box_tail_score ?? 0}` : '箱体未启用' }}</strong></div>
        <template v-if="selected.box_tail_enabled">
          <div><span>稳定箱体</span><strong>{{ label('boxStatus', selected.box_status || 'NO_BOX') }} · {{ selected.box_start_date || '--' }} 至 {{ selected.box_end_date || '--' }} · {{ selected.box_days ?? 0 }}日</strong></div>
          <div><span>箱体区间</span><strong>{{ priceRange(selected.box_low, selected.box_high) }} · 宽度 {{ pct(selected.box_width) }} · 位置 {{ pct(selected.box_position) }}</strong></div>
          <div><span>箱体承接</span><strong>下沿测试{{ selected.box_low_test_count ?? 0 }}次 · 上沿测试{{ selected.box_high_test_count ?? 0 }}次 · 中枢 {{ pct(selected.box_center_shift) }} · 后/前量 {{ fmt(selected.box_volume_contraction_ratio, 3) }}</strong></div>
          <div><span>紧密排列</span><strong>{{ label('boxQualityTag', selected.box_quality_tag || 'NONE') }} · {{ selected.compact_kline_pass ? '通过' : '未通过' }} · {{ selected.compact_kline_score ?? 0 }}/10 · 箱体质量 {{ selected.box_quality_score ?? 0 }}</strong></div>
          <div><span>紧密指标</span><strong>平均实体 {{ pct(selected.avg_body_ratio_5) }} · 收盘区间 {{ pct(selected.compact_close_range_5) }} · 重叠{{ selected.kline_overlap_pair_count ?? 0 }}组 · ATR比 {{ fmt(selected.atr_contraction_ratio, 3) }}</strong></div>
        </template>
        <div v-else><span>稳定箱体</span><strong>{{ researchModuleUnavailableText(selected, '稳定箱体') }}</strong></div>
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
      <div v-if="selected.tail_regime_enabled" data-test="tail-regime-detail" class="tail-regime-evidence">
        <div class="subsection-title">尾部变点观察</div>
        <div class="tail-regime-note">影子研究，不参与正式选股、评分、过滤或候选分层</div>
        <div class="tail-regime-grid">
          <div><span>识别状态</span><strong>{{ tailRegimeStatusText(selected.tail_regime_status) }}</strong></div>
          <div><span>推导尾段</span><strong>{{ selected.tail_regime_start_date || '--' }} 起 · {{ selected.tail_regime_days ?? 0 }} 个交易日</strong></div>
          <div><span>统计证据</span><strong>BIC证据 {{ fmt(selected.tail_regime_delta_bic, 3) }} · {{ selected.tail_regime_model_version || '--' }}</strong></div>
          <div><span>收缩比值</span><strong>成交量比 {{ fmt(selected.tail_regime_volume_ratio, 3) }} · 波幅比 {{ fmt(selected.tail_regime_range_ratio, 3) }} · 实体比 {{ fmt(selected.tail_regime_body_ratio, 3) }} · 涨跌比 {{ fmt(selected.tail_regime_abs_return_ratio, 3) }}</strong></div>
          <div><span>稳定结构</span><strong>收盘离散 {{ pct(selected.tail_regime_close_dispersion) }} · 低点斜率 {{ fmt(selected.tail_regime_low_slope_atr, 3) }} ATR/日</strong></div>
        </div>
        <div class="tags">
          <span v-for="reason in selected.tail_regime_reasons || []" :key="`trr-${reason}`" class="tag info">{{ tailRegimeEvidenceText(reason) }}</span>
          <span v-for="risk in selected.tail_regime_risks || []" :key="`trk-${risk}`" class="tag risk">{{ tailRegimeEvidenceText(risk) }}</span>
        </div>
      </div>
      <div v-if="selected.vcp_observation_eligible" class="vcp-evidence">
        <div class="subsection-title">VCP收缩证据</div>
        <div data-test="vcp-quality-detail" class="vcp-quality-detail">
          <template v-if="hasVcpQuality(selected)">
            <div class="vcp-quality-summary">
              <strong>{{ selected.vcp_quality_score }}分 · {{ label('vcpQualityGrade', selected.vcp_quality_grade) }}</strong>
              <span class="muted">{{ selected.vcp_quality_model_version || '--' }}</span>
            </div>
            <div v-if="isVcpQualityV2(selected)" class="vcp-quality-components">
              <span>完整轮次 {{ selected.vcp_quality_contraction_score }}/15</span>
              <span>振幅递减 {{ selected.vcp_quality_range_score }}/20</span>
              <span>下跌量递减 {{ selected.vcp_quality_volume_score }}/20</span>
              <span>低点稳定 {{ selected.vcp_quality_low_score }}/15</span>
              <span>启动涨幅保留 {{ selected.vcp_quality_start_retention_score }}/10</span>
              <span>时间结构 {{ selected.vcp_quality_time_score }}/5</span>
              <span>支点收紧 {{ selected.vcp_quality_pivot_score }}/10</span>
              <span>突破质量 {{ selected.vcp_quality_breakout_score }}/5</span>
            </div>
            <div v-else class="vcp-quality-components">
              <span>收缩层次 {{ selected.vcp_quality_contraction_score }}/20</span>
              <span>振幅递减 {{ selected.vcp_quality_range_score }}/25</span>
              <span>成交量递减 {{ selected.vcp_quality_volume_score }}/25</span>
              <span>低点稳定 {{ selected.vcp_quality_low_score }}/15</span>
              <span>时间结构 {{ selected.vcp_quality_time_score }}/10</span>
              <span>支点清晰 {{ selected.vcp_quality_pivot_score }}/5</span>
            </div>
            <div class="tags vcp-quality-tags">
              <span v-for="reason in selected.vcp_quality_reasons || []" :key="'vqr'+reason" class="tag info">{{ label('tag', reason) }}</span>
              <span v-for="warning in selected.vcp_quality_warnings || []" :key="'vqw'+warning" class="tag warn">{{ label('tag', warning) }}</span>
            </div>
          </template>
          <span v-else class="muted">VCP形态质量：未评分</span>
        </div>
        <div v-if="!(selected.vcp_contractions || []).length" class="muted">暂无收缩明细</div>
        <div v-for="(item, index) in selected.vcp_contractions || []" :key="`${item.peak_date}-${item.low_date}-${index}`" class="vcp-contraction-row">
          {{ vcpContractionText(item, index) }}
        </div>
        <div v-if="selected.vcp_forming_round && Object.keys(selected.vcp_forming_round).length" class="vcp-contraction-row muted">
          {{ vcpFormingRoundText(selected.vcp_forming_round) }}
        </div>
        <div class="tags vcp-tags">
          <span v-for="reason in selected.vcp_observation_reasons || []" :key="'vr'+reason" class="tag info">{{ label('tag', reason) }}</span>
          <span v-for="risk in selected.vcp_observation_risk_tags || []" :key="'vk'+risk" class="tag warn">{{ label('tag', risk) }}</span>
          <span v-if="selected.vcp_invalidation_reason" class="tag risk">{{ label('tag', selected.vcp_invalidation_reason) }}</span>
        </div>
      </div>
      <div class="brooks-evidence">
        <div class="subsection-title">Brooks价格行为证据</div>
        <div v-if="!selected.brooks_tail_enabled" class="brooks-empty">{{ researchModuleUnavailableText(selected, 'Brooks') }}</div>
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
      taskPage: 1,
      taskPageSize: 10,
      taskDropdownOpen: false,
      candidates: [],
      trendSqueezeScreen: [],
      selectedTaskId: '',
      selected: null,
      marketSnapshot: null,
      lifecycleRows: [],
      loading: false,
      error: '',
    }
  },
  computed: {
    taskPageCount() {
      return Math.max(1, Math.ceil(this.tasks.length / this.taskPageSize))
    },
    pagedTasks() {
      const start = (this.taskPage - 1) * this.taskPageSize
      return this.tasks.slice(start, start + this.taskPageSize)
    },
    selectedTask() {
      return this.tasks.find(task => task.id === this.selectedTaskId) || null
    },
    sortedCandidates() {
      const typePriority = {
        READY_CANDIDATE: 0,
        KEY_CANDIDATE: 1,
        WATCH_CANDIDATE: 2,
        REJECTED: 3,
      }
      return [...this.candidates].sort((left, right) => {
        const typeDifference = (typePriority[this.effectiveCandidateType(left)] ?? 4)
          - (typePriority[this.effectiveCandidateType(right)] ?? 4)
        if (typeDifference !== 0) return typeDifference
        const rankingDifference = this.candidateRankingScore(right) - this.candidateRankingScore(left)
        if (rankingDifference !== 0) return rankingDifference
        const scoreDifference = Number(right.total_score || 0) - Number(left.total_score || 0)
        if (scoreDifference !== 0) return scoreDifference
        return String(left.code || '').localeCompare(String(right.code || ''))
      })
    },
    tradingCandidates() {
      return this.sortedCandidates.filter(c => this.effectiveCandidateType(c) !== 'REJECTED')
    },
    vcpCandidates() {
      const statusPriority = {
        VCP_NEAR_PIVOT: 0,
        VCP_BREAKOUT_CONFIRMED: 1,
        VCP_POST_BREAKOUT: 2,
        VCP_FORMING: 3,
        VCP_EXTENDED: 4,
      }
      return this.candidates.filter(c => (
        c.vcp_observation_eligible === true
        && c.vcp_history_qualified === true
        && c.vcp_lifecycle_status !== 'VCP_INVALID'
        && c.vcp_lifecycle_status !== 'VCP_NONE'
      )).sort((left, right) => {
        const leftScored = this.hasVcpQuality(left)
        const rightScored = this.hasVcpQuality(right)
        if (leftScored !== rightScored) return leftScored ? -1 : 1
        if (leftScored && left.vcp_quality_score !== right.vcp_quality_score) {
          return right.vcp_quality_score - left.vcp_quality_score
        }
        const leftStatus = statusPriority[left.vcp_lifecycle_status] ?? 99
        const rightStatus = statusPriority[right.vcp_lifecycle_status] ?? 99
        if (leftStatus !== rightStatus) return leftStatus - rightStatus
        const scoreDifference = (right.total_score ?? -1) - (left.total_score ?? -1)
        if (scoreDifference !== 0) return scoreDifference
        return String(left.code || '').localeCompare(String(right.code || ''))
      })
    },
    vcpGroups() {
      if (!this.selectedTaskId) return []
      const confirmed = this.vcpCandidates.filter(
        candidate => candidate.vcp_lifecycle_status !== 'VCP_ROUND1_CONFIRMED',
      )
      const early = this.vcpCandidates.filter(
        candidate => candidate.vcp_lifecycle_status === 'VCP_ROUND1_CONFIRMED',
      )
      return [
        {
          key: 'confirmed',
          title: 'VCP确认候选',
          rows: confirmed,
          emptyMessage: this.vcpCandidates.length ? '本任务暂无已完成两轮收缩的VCP确认候选' : this.vcpEmptyMessage,
        },
        {
          key: 'early',
          title: 'VCP早期观察',
          rows: early,
          emptyMessage: this.vcpCandidates.length ? '本任务暂无仅完成第一轮收缩的VCP早期观察' : this.vcpEmptyMessage,
        },
      ]
    },
    vcpExitAuditRows() {
      return this.sortedCandidates.filter(c => c.vcp_exit_audit === true)
    },
    taskStrategyVersion() {
      return this.sortedCandidates.find(c => c.strategy_version)?.strategy_version || ''
    },
    vcpEmptyMessage() {
      const version = this.taskStrategyVersion
      const [major = 0, minor = 0] = version.split('.').map(value => Number(value) || 0)
      if (version && (major < 4 || (major === 4 && minor < 3))) {
        return `该任务由策略6 ${version}生成，尚未计算VCP观察数据，请重新扫描策略6`
      }
      if (version && major === 4 && minor < 4) {
        return `该任务由策略6 ${version}生成，尚未计算历史正式候选资格，请重新扫描策略6`
      }
      return '本任务未发现符合条件的VCP形态候选'
    },
    vcpQualityNotice() {
      const version = this.taskStrategyVersion
      if (!version || !this.vcpCandidates.length) return ''
      const [major, minor] = version.split('.').map(Number)
      if (major === 4 && minor === 4) {
        return `该任务由策略6 ${version}生成，尚未计算VCP形态质量分，可重新扫描生成`
      }
      return ''
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
      if (!this.tradingCandidates.length) return '--'
      return Math.max(...this.tradingCandidates.map(candidate => Number(candidate.total_score || 0)))
    },
    topRr2() {
      const best = this.tradingCandidates.reduce((max, c) => Math.max(max, Number(c.objective_rr_2 ?? c.risk_reward_ratio_2 ?? 0)), 0)
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
    document.addEventListener('click', this.closeTaskDropdown)
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
      this.locateTaskPage(defaultTaskId)
      this.selectedTaskId = defaultTaskId
      await this.loadCandidates()
    }
  },
  beforeUnmount() {
    document.removeEventListener('click', this.closeTaskDropdown)
  },
  methods: {
    taskDisplayText(task) {
      return `${task.id} · ${this.label('taskStatus', task.status)} · ${task.candidates || 0} 候选`
    },
    closeTaskDropdown(event) {
      const picker = this.$refs.taskPicker
      if (this.taskDropdownOpen && (!picker || !picker.contains(event.target))) {
        this.taskDropdownOpen = false
      }
    },
    async selectTask(task) {
      this.selectedTaskId = task.id
      this.taskDropdownOpen = false
      await this.loadCandidates()
    },
    locateTaskPage(taskId) {
      const index = this.tasks.findIndex(task => task.id === taskId)
      this.taskPage = index >= 0 ? Math.floor(index / this.taskPageSize) + 1 : 1
    },
    changeTaskPage(offset) {
      this.taskPage = Math.min(this.taskPageCount, Math.max(1, this.taskPage + offset))
    },
    candidateRankingScore(candidate) {
      const rankingScore = Number(candidate?.ranking_score)
      return Number.isFinite(rankingScore) ? rankingScore : Number(candidate?.total_score || 0)
    },
    hasTtmData(candidate) {
      return Boolean(candidate?.ttm_model_version && candidate?.ttm_squeeze_status)
    },
    hasStrongTrendSqueezeData(candidate) {
      return Boolean(candidate?.strong_trend_squeeze_model_version && candidate?.strong_trend_squeeze_status)
    },
    strongTrendSqueezeSummary(candidate) {
      if (!this.hasStrongTrendSqueezeData(candidate)) return '旧任务未计算'
      const status = candidate.strong_trend_squeeze_pass ? '通过独立初筛' : '未通过独立初筛（不直接淘汰主链）'
      const reasons = this.joinedLabels('tag', candidate.strong_trend_squeeze_reasons)
      return reasons === '--' ? `${status} · ${candidate.strong_trend_squeeze_model_version}` : `${status} · ${reasons}`
    },
    highTriggerText(value) {
      if (value === 'new_120d_high') return '近20日创120日收盘新高'
      if (value === 'near_120d_high') return '近20日接近120日最高收盘价'
      return '尚未完成近20日高位确认'
    },
    bodySupportStatusText(value) {
      return { BODY_SUPPORT_STRONG: '强实体支撑', BODY_SUPPORT_CONFIRMED: '实体支撑已确认', BODY_SUPPORT_FORMING: '实体支撑形成中', BODY_SUPPORT_WEAKENED: '实体支撑转弱', BODY_SUPPORT_BROKEN: '实体支撑失效', BODY_SUPPORT_NONE: '无有效实体支撑', DISABLED: '未启用' }[value] || value || '--'
    },
    bodySupportTypeText(value) {
      return { SINGLE_BODY_PIVOT: '单实体拐点', FLAT_BODY_FLOOR: '水平实体底', RISING_BODY_FLOOR: '抬高实体底', FAILED_BREAK_BODY_FLOOR: '假跌破实体底', COMPOSITE_BODY_FLOOR: '复合实体底', NONE: '未识别' }[value] || value || '--'
    },
    bodySupportSummary(candidate) {
      if (!candidate?.body_support_model_version) return '旧任务未计算'
      return `${candidate.body_support_score ?? 0}/10 · ${this.bodySupportStatusText(candidate.body_support_status)}`
    },
    bodySupportDetail(candidate) {
      if (!candidate?.body_support_model_version) return '旧任务未计算'
      return `${this.bodySupportSummary(candidate)} · ${this.bodySupportTypeText(candidate.body_support_type)} · 支撑 ${this.fmt(candidate.body_support_floor_price)} · 区间 ${this.priceRange(candidate.body_support_zone_low, candidate.body_support_zone_high)} · 诊断分不计入总分`
    },
    latestBarPatternItems(candidate) {
      return Array.isArray(candidate?.latest_bar_patterns) ? candidate.latest_bar_patterns : []
    },
    latestPatternTypeText(value) {
      return { FAILED_BREAK_RECLAIM: '假跌破收回', BODY_FLOOR_HOLD: '守住实体支撑', POTENTIAL_BODY_PIVOT: '潜在实体拐点', HIGHER_BODY_LOW: '更高实体低点', NONE: '无' }[value] || value || '--'
    },
    latestBarPatternSummary(candidate) {
      if (!candidate?.body_support_model_version) return '旧任务未计算'
      const matched = this.latestBarPatternItems(candidate).filter(item => item.matched)
      return matched.length ? matched.map(item => item.name).join(' / ') : '未识别到配置形态'
    },
    latestBarPatternDetail(candidate) {
      const items = this.latestBarPatternItems(candidate)
      if (!items.length) return '旧任务未计算'
      const matched = items.filter(item => item.matched)
      if (!matched.length) return '未识别到配置形态'
      return matched.map(item => `${item.name} · ${this.latestPatternTypeText(item.signal_type)} · 后续确认中 · 实体 ${this.priceRange(item.body_bottom, item.body_top)} · 支撑区 ${this.priceRange(item.zone_low, item.zone_high)}`).join(' / ')
    },
    ttmSummary(candidate) {
      if (!this.hasTtmData(candidate)) return '未计算'
      const days = candidate.ttm_squeeze_on && Number(candidate.ttm_squeeze_days) > 0
        ? ` · ${candidate.ttm_squeeze_days}日`
        : ''
      return `${this.label('ttmSqueezeStatus', candidate.ttm_squeeze_status)} · 诊断分 ${candidate.ttm_squeeze_score ?? 0}${days}`
    },
    ttmDetail(candidate) {
      if (!this.hasTtmData(candidate)) return '未计算'
      return `${this.ttmSummary(candidate)} · 不参与资格与排序 · ${candidate.ttm_model_version}`
    },
    ttmBandsDetail(candidate) {
      if (!this.hasTtmData(candidate)) return '未计算'
      return `BB ${this.priceRange(candidate.ttm_bb_lower, candidate.ttm_bb_upper)} · Keltner ${this.priceRange(candidate.ttm_kc_lower, candidate.ttm_kc_upper)}`
    },
    ttmMomentumDetail(candidate) {
      if (!this.hasTtmData(candidate)) return '未计算'
      return `当前 ${this.fmt(candidate.ttm_momentum, 3)} · 前一日 ${this.fmt(candidate.ttm_previous_momentum, 3)} · ${this.label('ttmMomentumDirection', candidate.ttm_momentum_direction)}`
    },
    hasVcpQuality(candidate) {
      return typeof candidate?.vcp_quality_score === 'number'
        && Number.isFinite(candidate.vcp_quality_score)
    },
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
      if (this.isObservationRecord(candidate)) return false
      return this.isBrooksOnlyWaiting(candidate) || candidate?.entry_archetype === 'WAIT_BREAKOUT'
    },
    isObservationRecord(candidate) {
      return candidate?.candidate_type === 'REJECTED' && candidate?.classification === 'observation'
    },
    hasQualityDiagnostics(candidate) {
      if (typeof candidate?.quality_diagnostics_available === 'boolean') {
        return candidate.quality_diagnostics_available
      }
      const version = String(candidate?.score_model_version || '')
      if (!version.startsWith('S6_')) return false
      return [
        'entry_archetype',
        'start_event_quality_score',
        'setup_quality_score',
        'support_reaction_score',
        'path_evidence_score',
      ].some(field => candidate?.[field] !== null && candidate?.[field] !== undefined && candidate?.[field] !== '')
    },
    hasTailSegmentation(candidate) {
      return Boolean(candidate?.tail_segmentation_status)
    },
    researchModuleUnavailableText(candidate, moduleName) {
      const displayName = moduleName === 'Brooks' ? ' Brooks ' : moduleName
      if (candidate?.decision_profile === 'formal_original') {
        return `正式策略未启用${displayName}研究，未参与评估`
      }
      return `${moduleName}未启用或旧任务无数据（未参与评估）`
    },
    decisionProfileText(candidate) {
      const profile = candidate?.decision_profile
      if (profile === 'formal_original') return '正式原始链'
      if (profile === 'research_quality_v2') return '研究质量 V2'
      return '历史规则未标记'
    },
    qualityValue(candidate, field) {
      if (!this.hasQualityDiagnostics(candidate)) return '--'
      return candidate?.[field] ?? '--'
    },
    entryArchetypeText(candidate) {
      return this.hasQualityDiagnostics(candidate) ? this.label('entryArchetype', candidate?.entry_archetype || 'NONE') : '--'
    },
    entryTimingText(candidate) {
      return ({
        INVALID: '入场失效',
        WAITING_BREAKOUT: '等待突破',
        SUPPORT_FORMING: '支撑止跌形成中',
        SUPPORT_CONFIRMED: '支撑止跌已确认',
        BREAKOUT_CONFIRMED: '突破已确认',
        RECLAIM_CONFIRMED: '失败突破回收已确认',
        NOT_APPLICABLE: '不适用',
      })[candidate?.entry_timing_state] || '旧任务无数据'
    },
    entryTimingDetail(candidate) {
      if (!candidate?.entry_timing_version) return '旧任务无数据'
      const executable = candidate?.entry_timing_executable ? '可执行' : '等待确认'
      return `${this.entryTimingText(candidate)} · ${executable} · 证据 ${candidate?.entry_timing_evidence_count ?? 0}`
    },
    probabilityRrStatusText(candidate) {
      return ({
        RELIABLE: '可靠',
        INSUFFICIENT_SAMPLE: '样本不足',
        INVALID_TRADE_PLAN: '交易计划无效',
        NOT_EVALUATED: '未评估',
      })[candidate?.probability_rr_status] || '旧任务无数据'
    },
    probabilityRrDetail(candidate) {
      if (!candidate?.probability_rr_version) return '旧任务无数据'
      return `${this.probabilityRrStatusText(candidate)} · 期望R ${this.fmt(candidate?.probability_adjusted_r)} · 目标1 ${this.pct(candidate?.probability_rr_target_1_hit_probability)} · 目标2 ${this.pct(candidate?.probability_rr_target_2_hit_probability)} · 样本 ${candidate?.probability_rr_sample_count ?? 0}`
    },
    effectiveCandidateType(candidate) {
      if (this.isObservationRecord(candidate)) return 'REJECTED'
      return this.isExecutionWaiting(candidate) ? 'WATCH_CANDIDATE' : (candidate?.candidate_type || 'WATCH_CANDIDATE')
    },
    candidateTypeText(candidate) {
      return this.label('candidateType', this.effectiveCandidateType(candidate))
    },
    marketDowngradeText(candidate) {
      const origin = candidate?.pre_market_candidate_type
      if (origin === 'READY_CANDIDATE' || origin === 'KEY_CANDIDATE') {
        return `原${this.label('candidateType', origin)} · 因市场偏弱降级`
      }
      if ((candidate?.warn_tags || []).includes('MARKET_WEAK_DOWNGRADED')) {
        return '市场降级 · 原等级未记录'
      }
      return ''
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
        this.trendSqueezeScreen = []
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
      const [screenResult, snapshotResult, lifecycleResult] = await Promise.allSettled([
        api.getStrategy6TrendSqueezeScreen(taskId),
        api.getStrategy6MarketSnapshot(taskId),
        api.getStrategy6Lifecycle(taskId),
      ])
      if (this.selectedTaskId !== taskId) return
      if (screenResult.status === 'fulfilled') {
        this.trendSqueezeScreen = screenResult.value.stocks || []
      } else {
        this.error = '新初筛股票池加载失败，候选数据已保留'
      }
      if (snapshotResult.status === 'fulfilled') {
        this.marketSnapshot = snapshotResult.value.snapshot || null
      } else {
        this.error = '市场指数快照加载失败，候选数据已保留'
      }
      if (lifecycleResult.status === 'fulfilled') {
        this.lifecycleRows = lifecycleResult.value.lifecycle || []
      } else {
        this.error = '生命周期审计加载失败，候选数据已保留'
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
    tailRegimeStatusText(status) {
      return ({
        FORMING: '形成中',
        CONFIRMED: '已确认',
        BROKEN: '结构已破坏',
        NO_REGIME_CHANGE: '未识别到状态切换',
        INSUFFICIENT_BASELINE: '基准数据不足',
        DISABLED: '未启用',
      })[status] || '--'
    },
    tailRegimeEvidenceText(code) {
      return ({
        ROBUST_BIC_CHANGE_POINT: '鲁棒BIC识别到状态变点',
        TAIL_VOLUME_CONTRACTED: '尾段成交量收缩',
        TAIL_PRICE_ACTION_CONTRACTED: '尾段价格波动收缩',
        TAIL_LOW_STRUCTURE_STABLE: '尾段低点结构稳定',
        TAIL_REGIME_BIG_DOWN_VOLUME: '尾段出现放量大跌',
        TAIL_REGIME_LOW_DETERIORATING: '尾段低点继续恶化',
        SUPPORT_TWO_CLOSE_BREAK: '连续两日收盘跌破关键支撑',
        PREVIOUS_SUPPORT_TWO_CLOSE_BREAK: '前一交易日连续收盘跌破关键支撑',
        PREVIOUS_PHASE_INVALID: '前一交易日阶段划分无效',
        PREVIOUS_TAIL_REGIME_BIG_DOWN_VOLUME: '前一交易日尾段出现放量大跌',
        PREVIOUS_TAIL_REGIME_LOW_DETERIORATING: '前一交易日尾段低点继续恶化',
        START_NOT_FOUND: '未找到有效强势启动',
        START_TOO_RECENT: '强势启动时间过近',
        START_TOO_OLD: '强势启动时间过久',
        CONSOLIDATION_TOO_SHORT: '整理时间不足',
        CONSOLIDATION_TOO_LONG: '整理时间过长',
        PHASE_ORDER_INVALID: '启动、整理、尾段顺序无效',
        TAIL_REGIME_INVALID_KLINE: 'K线数据无效',
        TAIL_REGIME_SAMPLE_INSUFFICIENT: '尾部变点样本不足',
      })[code] || code || '--'
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
    vcpContractionText(item, index) {
      if (!item?.recovery_peak_date) {
        return `旧任务第${index + 1}段 ${item?.peak_date || '--'} 至 ${item?.low_date || '--'} · 振幅 ${this.pct(item?.amplitude)} · 均量 ${this.fmt(item?.avg_volume, 0)}`
      }
      return `第${index + 1}轮 ${item.peak_date || '--'} → ${item.low_date || '--'} → ${item.recovery_peak_date} · 振幅 ${this.pct(item.amplitude)} · 反弹 ${this.pct(item.rebound)} · 下跌均量 ${this.fmt(item.decline_avg_volume, 0)}`
    },
    vcpFormingRoundText(item) {
      return `形成中轮次 ${item?.peak_date || '--'} → ${item?.low_date || '--'} · ${this.label('vcpFormingPhase', item?.phase)}`
    },
    hasConsecutiveDownDiagnostic(candidate) {
      return candidate?.consecutive_down_structure_version === 'CONSECUTIVE_DOWN_INTERVAL_5D_V2'
        && candidate?.consecutive_down_days !== null
        && candidate?.consecutive_down_days !== undefined
        && candidate?.consecutive_down_structure_pass !== null
        && candidate?.consecutive_down_structure_pass !== undefined
    },
    consecutiveDownStructureText(candidate) {
      if (!this.hasConsecutiveDownDiagnostic(candidate)) return '未计算'
      const days = Number(candidate.consecutive_down_days) || 0
      if (days < 3) return `${days}日 · 未满足`
      if (candidate.consecutive_down_no_new_streak_low === null
        || candidate.consecutive_down_no_new_streak_low === undefined) return '未计算'
      if (candidate.consecutive_down_structure_pass) {
        return `${days}日 · 守5日参考低 · 未创5日高`
      }
      const failures = []
      if (candidate.consecutive_down_no_new_streak_low === false) failures.push('跌破5日参考低')
      if (Number(candidate.consecutive_down_max_high_break_pct) > 0) failures.push('已创5日高')
      return `${days}日 · ${failures.join(' · ') || '未满足'}`
    },
    consecutiveDownStructureDetail(candidate) {
      if (!this.hasConsecutiveDownDiagnostic(candidate)) return '未计算'
      const summary = this.consecutiveDownStructureText(candidate)
      if (summary === '未计算') return summary
      return `${summary} · 连跌低点 ${this.fmt(candidate.consecutive_down_low)} · 相对5日参考低余量 ${this.pct(candidate.consecutive_down_min_low_margin_pct)} · 高点突破 ${this.pct(candidate.consecutive_down_max_high_break_pct)}`
    },
    isVcpQualityV2(candidate) {
      return ['VCP_QUALITY_V2', 'VCP_QUALITY_V3'].includes(candidate?.vcp_quality_model_version)
    },
    vcpExitReasonText(row) {
      const reasons = [
        row.vcp_invalidation_reason,
        ...(row.vcp_observation_risk_tags || []),
      ].filter(Boolean)
      return this.joinedLabels('tag', [...new Set(reasons)], ' / ')
    },
    trendScreenOutcomeText(stock) {
      if (stock?.downstream_candidate_type && stock.downstream_candidate_type !== 'REJECTED') {
        return `进入${this.label('candidateType', stock.downstream_candidate_type)}`
      }
      return '通过初筛，后续未入选'
    },
    exportTrendSqueezeScreen() {
      downloadCsv({
        filename: `strategy6-trend-squeeze-screen-${this.selectedTaskId || 'latest'}.csv`,
        columns: [
          { header: '代码', value: row => row.code },
          { header: '名称', value: row => row.name },
          { header: '评价日', value: row => row.evaluation_date || '' },
          { header: '现价', value: row => row.trend_close ?? '' },
          { header: 'EMA150', value: row => row.trend_ema150 ?? '' },
          { header: 'EMA200', value: row => row.trend_ema200 ?? '' },
          { header: '52周最低价', value: row => row.trend_low_250 ?? '' },
          { header: '52周最高价', value: row => row.trend_high_250 ?? '' },
          { header: '现价相对52周低', value: row => row.trend_close_to_low_ratio ?? '' },
          { header: '现价相对52周高', value: row => row.trend_close_to_high_ratio ?? '' },
          { header: 'BB下轨', value: row => row.trend_bb_lower ?? '' },
          { header: 'BB上轨', value: row => row.trend_bb_upper ?? '' },
          { header: 'KC下轨', value: row => row.trend_kc_lower ?? '' },
          { header: 'KC上轨', value: row => row.trend_kc_upper ?? '' },
          { header: '后续主链结果', value: row => this.trendScreenOutcomeText(row) },
          { header: '后续拦截原因', value: row => (row.downstream_reject_reasons || []).join('|') },
          { header: '模型版本', value: row => row.strong_trend_squeeze_model_version || '' },
        ],
        rows: this.trendSqueezeScreen,
      })
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
          { header: '决策规则', value: c => this.decisionProfileText(c) },
          { header: '评分模型版本', value: c => c.score_model_version || '' },
          { header: '入场类型', value: c => this.entryArchetypeText(c) === '--' ? '' : this.entryArchetypeText(c) },
          { header: '入场类型原始值', value: c => this.hasQualityDiagnostics(c) ? (c.entry_archetype || 'NONE') : '' },
          { header: '启动事件质量分', value: c => this.hasQualityDiagnostics(c) ? (c.start_event_quality_score ?? '') : '' },
          { header: '整理质量分', value: c => this.hasQualityDiagnostics(c) ? (c.setup_quality_score ?? '') : '' },
          { header: '支撑反应分', value: c => this.hasQualityDiagnostics(c) ? (c.support_reaction_score ?? '') : '' },
          { header: '路径证据分', value: c => this.hasQualityDiagnostics(c) ? (c.path_evidence_score ?? '') : '' },
          { header: '实体支撑底评分', value: c => c.body_support_model_version ? (c.body_support_score ?? 0) : '' },
          { header: '实体支撑底状态', value: c => c.body_support_model_version ? this.bodySupportStatusText(c.body_support_status) : '' },
          { header: '实体支撑底类型', value: c => c.body_support_model_version ? this.bodySupportTypeText(c.body_support_type) : '' },
          { header: '实体支撑价格', value: c => c.body_support_floor_price ?? '' },
          { header: '实体支撑区下沿', value: c => c.body_support_zone_low ?? '' },
          { header: '实体支撑区上沿', value: c => c.body_support_zone_high ?? '' },
          { header: '最新交易日K线形态', value: c => this.latestBarPatternSummary(c) },
          { header: '最新K线形态明细', value: c => this.latestBarPatternItems(c).map(item => `${item.name}:${this.latestPatternTypeText(item.signal_type)}:${item.status}`).join('|') },
          { header: '实体支撑模型版本', value: c => c.body_support_model_version || '' },
          { header: '入场时机', value: c => c.entry_timing_version ? this.entryTimingText(c) : '' },
          { header: '入场时机原始值', value: c => c.entry_timing_state || '' },
          { header: '当前可执行', value: c => c.entry_timing_version ? (c.entry_timing_executable ? '是' : '否') : '' },
          { header: '入场证据数', value: c => c.entry_timing_version ? (c.entry_timing_evidence_count ?? 0) : '' },
          { header: '概率RR状态', value: c => c.probability_rr_version ? this.probabilityRrStatusText(c) : '' },
          { header: '概率RR状态原始值', value: c => c.probability_rr_status || '' },
          { header: '概率RR样本', value: c => c.probability_rr_version ? (c.probability_rr_sample_count ?? 0) : '' },
          { header: '目标1命中率', value: c => c.probability_rr_version ? this.pct(c.probability_rr_target_1_hit_probability) : '' },
          { header: '目标2命中率', value: c => c.probability_rr_version ? this.pct(c.probability_rr_target_2_hit_probability) : '' },
          { header: '概率修正期望R', value: c => c.probability_rr_version ? this.fmt(c.probability_adjusted_r) : '' },
          { header: '尾段划分', value: c => this.hasTailSegmentation(c) ? this.label('tailSegmentationStatus', c.tail_segmentation_status) : '' },
          { header: '尾段划分原始值', value: c => this.hasTailSegmentation(c) ? c.tail_segmentation_status : '' },
          { header: '尾段划分分数', value: c => this.hasTailSegmentation(c) ? (c.tail_segmentation_score ?? '') : '' },
          { header: '连续收跌天数', value: c => this.hasConsecutiveDownDiagnostic(c) ? c.consecutive_down_days : '' },
          { header: '连续收跌最低价', value: c => this.hasConsecutiveDownDiagnostic(c) ? this.fmt(c.consecutive_down_low) : '' },
          { header: '连续收跌结构', value: c => this.hasConsecutiveDownDiagnostic(c) ? this.consecutiveDownStructureText(c) : '' },
          { header: '守住5日参考低', value: c => this.hasConsecutiveDownDiagnostic(c) ? (c.consecutive_down_no_new_streak_low ? '是' : '否') : '' },
          { header: '相对5日参考低余量', value: c => this.hasConsecutiveDownDiagnostic(c) ? this.pct(c.consecutive_down_min_low_margin_pct) : '' },
          { header: '5日高最大突破', value: c => this.hasConsecutiveDownDiagnostic(c) ? this.pct(c.consecutive_down_max_high_break_pct) : '' },
          { header: '阶段状态', value: c => this.label('phaseStatus', c.phase_status) },
          { header: '阶段状态原始值', value: c => c.phase_status || '' },
          { header: '形态类型', value: c => this.label('patternType', c.pattern_type) },
          { header: '形态类型原始值', value: c => c.pattern_type || '' },
          { header: 'VCP观察资格', value: c => c.vcp_observation_eligible ? '是' : '否' },
          { header: 'VCP状态', value: c => this.label('vcpStatus', c.vcp_lifecycle_status || 'VCP_NONE') },
          { header: 'VCP状态原始值', value: c => c.vcp_lifecycle_status || 'VCP_NONE' },
          { header: 'VCP起点', value: c => c.vcp_origin_start_date || '' },
          { header: 'VCP形态开始', value: c => c.vcp_pattern_start_date || '' },
          { header: 'VCP形态结束', value: c => c.vcp_pattern_end_date || '' },
          { header: 'VCP收缩次数', value: c => c.vcp_contraction_count ?? 0 },
          { header: 'VCP支点', value: c => this.fmt(c.vcp_pivot_price) },
          { header: 'VCP结构低点', value: c => this.fmt(c.vcp_structure_low) },
          { header: '距VCP支点', value: c => this.pct(c.vcp_distance_to_pivot_pct) },
          { header: 'VCP突破日期', value: c => c.vcp_breakout_date || '' },
          { header: 'VCP突破后天数', value: c => c.vcp_days_since_breakout ?? 0 },
          { header: 'VCP观察原因', value: c => strategy6Labels('tag', c.vcp_observation_reasons).join('|') },
          { header: 'VCP观察风险', value: c => strategy6Labels('tag', c.vcp_observation_risk_tags).join('|') },
          { header: 'VCP失效原因', value: c => c.vcp_invalidation_reason ? this.label('tag', c.vcp_invalidation_reason) : '' },
          { header: 'VCP形态分', value: c => this.hasVcpQuality(c) ? c.vcp_quality_score : '' },
          { header: 'VCP等级', value: c => this.hasVcpQuality(c) ? this.label('vcpQualityGrade', c.vcp_quality_grade) : '' },
          { header: 'VCP完整轮次分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_contraction_score ?? '') : '' },
          { header: 'VCP振幅递减分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_range_score ?? '') : '' },
          { header: 'VCP下跌量递减分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_volume_score ?? '') : '' },
          { header: 'VCP低点稳定分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_low_score ?? '') : '' },
          { header: 'VCP启动涨幅保留分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_start_retention_score ?? '') : '' },
          { header: 'VCP时间结构分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_time_score ?? '') : '' },
          { header: 'VCP支点收紧分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_pivot_score ?? '') : '' },
          { header: 'VCP突破质量分', value: c => this.hasVcpQuality(c) ? (c.vcp_quality_breakout_score ?? '') : '' },
          { header: 'VCP评分原因', value: c => strategy6Labels('tag', c.vcp_quality_reasons).join('|') },
          { header: 'VCP评分警告', value: c => strategy6Labels('tag', c.vcp_quality_warnings).join('|') },
          { header: 'VCP评分模型版本', value: c => c.vcp_quality_model_version || '' },
          { header: 'VCP历史正式候选资格', value: c => c.vcp_history_qualified ? '是' : '否' },
          { header: 'VCP历史候选日期', value: c => c.vcp_history_candidate_date || '' },
          { header: 'VCP历史候选类型', value: c => c.vcp_history_candidate_type || '' },
          { header: 'VCP历史候选分数', value: c => c.vcp_history_candidate_score ?? '' },
          { header: 'VCP历史资格来源', value: c => c.vcp_history_source || '' },
          { header: 'VCP历史资格起点', value: c => c.vcp_history_origin_start_date || '' },
          { header: '总分', value: c => c.total_score ?? '' },
          { header: 'TTM状态', value: c => this.hasTtmData(c) ? this.label('ttmSqueezeStatus', c.ttm_squeeze_status) : '' },
          { header: 'TTM状态原始值', value: c => this.hasTtmData(c) ? c.ttm_squeeze_status : '' },
          { header: 'TTM诊断分', value: c => this.hasTtmData(c) ? (c.ttm_squeeze_score ?? 0) : '' },
          { header: '排序分', value: c => this.hasTtmData(c) ? this.candidateRankingScore(c) : (c.total_score ?? '') },
          { header: '连续挤压天数', value: c => this.hasTtmData(c) ? (c.ttm_squeeze_days ?? 0) : '' },
          { header: '当前挤压', value: c => this.hasTtmData(c) ? (c.ttm_squeeze_on ? '是' : '否') : '' },
          { header: '挤压刚解除', value: c => this.hasTtmData(c) ? (c.ttm_fired ? '是' : '否') : '' },
          { header: 'TTM动量', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_momentum, 3) : '' },
          { header: '前一日TTM动量', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_previous_momentum, 3) : '' },
          { header: 'TTM动量方向', value: c => this.hasTtmData(c) ? this.label('ttmMomentumDirection', c.ttm_momentum_direction) : '' },
          { header: '布林带下轨', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_bb_lower) : '' },
          { header: '布林带上轨', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_bb_upper) : '' },
          { header: 'Keltner下轨', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_kc_lower) : '' },
          { header: 'Keltner上轨', value: c => this.hasTtmData(c) ? this.fmt(c.ttm_kc_upper) : '' },
          { header: 'TTM原因', value: c => this.hasTtmData(c) ? strategy6Labels('tag', c.ttm_reasons).join('|') : '' },
          { header: 'TTM风险', value: c => this.hasTtmData(c) ? strategy6Labels('tag', c.ttm_risk_tags).join('|') : '' },
          { header: 'TTM模型版本', value: c => c.ttm_model_version || '' },
          { header: '独立强势趋势收缩初筛', value: c => this.hasStrongTrendSqueezeData(c) ? (c.strong_trend_squeeze_pass ? '通过' : '未通过') : '' },
          { header: 'EMA150', value: c => c.trend_ema150 ?? '' },
          { header: 'EMA200', value: c => c.trend_ema200 ?? '' },
          { header: '52周最低价', value: c => c.trend_low_250 ?? '' },
          { header: '52周最高价', value: c => c.trend_high_250 ?? '' },
          { header: '现价/52周最低价', value: c => c.trend_close_to_low_ratio ?? '' },
          { header: '现价/52周最高价', value: c => c.trend_close_to_high_ratio ?? '' },
          { header: '最新日BB/KC收缩状态', value: c => this.hasStrongTrendSqueezeData(c) ? (c.trend_squeeze_on ? '是' : '否') : '' },
          { header: '强势趋势收缩失败原因', value: c => strategy6Labels('tag', c.strong_trend_squeeze_reasons).join('|') },
          { header: '强势趋势收缩模型', value: c => c.strong_trend_squeeze_model_version || '' },
          { header: '市场过滤', value: c => c.enable_market_filter ? '开启' : '关闭' },
          { header: '市场过滤模式', value: c => this.label('marketFilterMode', c.market_filter_mode) },
          { header: '市场过滤模式原始值', value: c => c.market_filter_mode || '' },
          { header: '市场状态', value: c => this.label('marketStatus', c.market_status) },
          { header: '市场状态原始值', value: c => c.market_status || '' },
          { header: '市场降级前等级', value: c => c.pre_market_candidate_type ? `原${this.label('candidateType', c.pre_market_candidate_type)}` : '' },
          { header: '市场降级前等级原始值', value: c => c.pre_market_candidate_type || '' },
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
          { header: '近20日高位确认', value: c => this.highTriggerText(c.high_trigger) },
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
.strategy6-results { padding: 22px 24px 40px; color: var(--text-primary); }
.page-header { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; margin-bottom: 12px; padding-bottom: 14px; border-bottom: 1px solid var(--border); }
.page-title-block { min-width: 320px; }
.terminal-kicker { display: block; margin-bottom: 7px; color: var(--gold); font: 10px/1 var(--font-mono); letter-spacing: 0.16em; }
h1 { margin: 0 0 5px; font-size: 23px; line-height: 1.2; }
p { margin: 0; color: var(--text-muted); font-size: 12px; }
.header-controls { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex: 1; }
.task-picker { position: relative; min-width: 350px; }
.task-select-trigger { width: 100%; height: 34px; display: flex; align-items: center; justify-content: space-between; gap: 12px; background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 10px; cursor: pointer; text-align: left; font: 11px/1 var(--font-mono); }
.task-select-trigger:hover, .task-select-trigger[aria-expanded="true"] { border-color: var(--accent); }
.task-select-arrow { color: var(--text-secondary); font-size: 10px; }
.task-dropdown { position: absolute; z-index: 40; top: calc(100% + 5px); left: 0; right: 0; overflow: hidden; background: var(--bg-elevated); border: 1px solid var(--border-light); border-radius: var(--radius-sm); box-shadow: 0 12px 32px rgba(0, 0, 0, 0.42); }
.task-options { display: flex; flex-direction: column; padding: 5px; }
.task-option { width: 100%; background: transparent; color: var(--text-primary); border: 0; border-radius: 2px; padding: 8px 10px; cursor: pointer; text-align: left; font: 11px/1.3 var(--font-mono); }
.task-option:hover { background: var(--bg-hover); }
.task-option.selected { background: var(--accent-glow); color: var(--accent-strong); }
.task-option-empty { padding: 12px; color: var(--text-secondary); text-align: center; }
.task-pagination { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 8px; border-top: 1px solid var(--border); color: var(--text-secondary); font-size: 12px; }
.task-pagination button { background: transparent; color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 4px 9px; cursor: pointer; }
.task-pagination button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.task-pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.export-btn { height: 34px; background: transparent; color: var(--text-secondary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 7px 11px; cursor: pointer; font-size: 11px; white-space: nowrap; }
.export-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
.export-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.summary-bar { display: flex; gap: 18px; align-items: center; margin: 10px 0 14px; padding: 8px 12px; border: 1px solid var(--border); background: rgba(11,17,27,0.72); color: var(--text-secondary); flex-wrap: wrap; font: 11px/1.3 var(--font-mono); }
.summary-bar strong { color: var(--text-primary); }
.market-summary { padding: 9px 14px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; color: var(--text-secondary); border-bottom: 1px solid var(--border); font-size: 11px; }
.chip, .type-badge, .tag { border-radius: 2px; padding: 2px 7px; font-size: 11px; display: inline-block; margin: 1px 3px 1px 0; border: 1px solid transparent; }
.chip.ready, .type-badge.ready { background: rgba(59, 130, 246, 0.18); color: #93c5fd; }
.chip.key, .type-badge.key { background: rgba(168, 85, 247, 0.18); color: #d8b4fe; }
.chip.watch, .type-badge.watch { background: rgba(234, 179, 8, 0.15); color: #fde68a; }
.downgrade-note { margin-top: 5px; color: #fdba74; font-size: 12px; font-weight: 600; white-space: nowrap; }
.chip.vcp { background: rgba(20, 184, 166, 0.16); color: #99f6e4; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-sm); margin: 12px 0; overflow: hidden; box-shadow: var(--shadow-panel); }
.panel-header { min-height: 39px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 11px; font-weight: 700; letter-spacing: 0.05em; color: var(--text-secondary); }
.panel-header-actions { display: flex; align-items: center; gap: 10px; }
.panel-count { min-width: 24px; padding: 2px 6px; border: 1px solid var(--border-light); color: var(--text-primary); font: 10px/1.2 var(--font-mono); text-align: center; }
.market-state { color: var(--gold); font-size: 11px; }
.market-index-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; padding: 12px 14px; }
.market-index-card { min-width: 0; padding: 11px 12px; border: 1px solid var(--border); background: linear-gradient(180deg, var(--bg-card), rgba(16,24,36,0.6)); }
.index-card-head { display: flex; justify-content: space-between; gap: 8px; align-items: flex-start; }
.index-card-head div { display: flex; flex-direction: column; min-width: 0; }
.index-card-head strong { color: var(--text-primary); font-size: 12px; }
.index-card-head div span { color: var(--text-muted); font: 9px/1.4 var(--font-mono); }
.data-state { color: var(--text-muted); font-size: 10px; }
.data-state.fresh { color: var(--success); }
.index-price { margin-top: 10px; color: var(--text-primary); font: 700 20px/1 var(--font-mono); }
.index-return { margin-top: 5px; font: 600 11px/1.2 var(--font-mono); }
.index-return.up { color: var(--up-red); }
.index-return.down { color: var(--down-green); }
.index-meta { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 10px; color: var(--text-muted); font: 9px/1.3 var(--font-mono); }
.market-raw-data { border-top: 1px solid var(--border); }
.market-raw-data summary { padding: 9px 14px; cursor: pointer; color: var(--text-muted); font-size: 11px; user-select: none; }
.market-raw-data summary:hover { color: var(--accent); background: var(--bg-hover); }
.vcp-panel { border-color: rgba(20, 184, 166, 0.35); }
.vcp-audit-panel { border-color: rgba(239, 68, 68, 0.28); }
.panel-note { padding: 9px 14px; color: var(--text-secondary); font-size: 12px; border-bottom: 1px solid var(--border); }
.panel-empty { padding: 18px 14px; color: var(--text-secondary); }
.vcp-table { min-width: 1120px; }
.table-scroll { overflow-x: auto; }
.candidate-table { width: 100%; min-width: 1520px; border-collapse: collapse; font-size: 13px; }
.trend-screen-table { width: 100%; min-width: 1180px; border-collapse: collapse; font-size: 12px; }
.trend-screen-table th, .trend-screen-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; white-space: nowrap; }
.trend-screen-table th { color: var(--text-muted); font-size: 11px; font-weight: 600; background: #0d1520; }
.market-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 13px; }
.lifecycle-table { width: 100%; min-width: 980px; border-collapse: collapse; font-size: 13px; }
th, td { border-bottom: 1px solid var(--border); padding: 8px 10px; text-align: left; }
th { position: sticky; top: 0; z-index: 2; background: #0d1520; color: var(--text-secondary); font-size: 11px; font-weight: 600; white-space: nowrap; }
td { vertical-align: top; }
.clickable { cursor: pointer; }
.clickable:hover { background: var(--bg-hover); }
.candidate-table th:first-child, .candidate-table td:first-child,
.vcp-table th:first-child, .vcp-table td:first-child { position: sticky; left: 0; z-index: 3; background: var(--bg-panel); box-shadow: 1px 0 0 var(--border); }
.candidate-table th:first-child, .vcp-table th:first-child { z-index: 4; background: #0d1520; }
.candidate-table .clickable:hover td:first-child, .vcp-table .clickable:hover td:first-child { background: var(--bg-hover); }
.code { color: var(--accent); font-family: var(--font-mono); }
.score, .rr { color: var(--gold); font-weight: 700; }
.tag.risk { background: rgba(239, 68, 68, 0.16); color: #fca5a5; }
.tag.warn { background: rgba(249, 115, 22, 0.16); color: #fdba74; }
.tag.info { background: rgba(79,125,255,0.15); color: #93c5fd; }
.detail-panel { padding-bottom: 12px; }
.detail-grid { padding: 12px 14px 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1px; background: var(--border); }
.detail-grid div { display: flex; flex-direction: column; gap: 4px; min-height: 58px; padding: 10px 11px; background: var(--bg-panel); }
.detail-grid span { color: var(--text-secondary); font-size: 12px; }
.detail-grid strong { color: var(--text-primary); }
.tail-regime-evidence { margin: 0 14px 14px; padding: 12px; border: 1px solid rgba(74, 144, 226, 0.35); border-radius: var(--radius-sm); background: rgba(74, 144, 226, 0.06); }
.tail-regime-note { margin: 6px 0 10px; color: var(--text-secondary); font-size: 12px; }
.tail-regime-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.tail-regime-grid div { display: flex; flex-direction: column; gap: 3px; }
.tail-regime-grid span { color: var(--text-secondary); font-size: 12px; }
.brooks-evidence { margin: 0 14px 14px; padding: 14px; border: 1px solid rgba(77, 163, 255, 0.25); border-radius: var(--radius-sm); background: rgba(77, 163, 255, 0.04); }
.vcp-evidence { margin: 0 14px 14px; padding: 14px; border: 1px solid rgba(20, 184, 166, 0.3); border-radius: var(--radius-sm); background: rgba(20, 184, 166, 0.04); }
.vcp-contraction-row { padding: 5px 0; color: var(--text-primary); font-family: var(--font-mono); font-size: 13px; }
.vcp-tags { padding: 8px 0 0; }
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
@media (max-width: 1180px) {
  .page-header { align-items: flex-start; flex-direction: column; }
  .header-controls { width: 100%; justify-content: flex-start; flex-wrap: wrap; }
  .market-index-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .strategy6-results { padding: 16px 12px 30px; }
  .task-picker { min-width: 100%; width: 100%; }
  .market-index-grid { grid-template-columns: 1fr; }
}
</style>
