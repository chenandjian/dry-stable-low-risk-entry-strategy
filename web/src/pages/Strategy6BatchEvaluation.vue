<template>
  <main class="batch-page">
    <header class="page-header">
      <div>
        <p class="eyebrow">STRATEGY 6 · LOCAL EVALUATION</p>
        <h1>强势股批量评分</h1>
        <p>复用策略6当前正式评价体系，只读本地前复权日线；结果按尾部评分优先、总分次优排列。</p>
      </div>
      <div class="tail-priority">
        <span>排序规则</span>
        <strong>尾部评分优先</strong>
        <small>量稳价干 20分 · 总分 100分</small>
      </div>
    </header>

    <section class="input-panel terminal-panel">
      <div class="panel-title">
        <div><span>01</span><strong>输入股票池</strong></div>
        <small>每行、空格或逗号分隔；自动去重，最多200只；自动记住上次输入</small>
      </div>
      <textarea
        v-model="rawCodes"
        data-test="batch-codes"
        rows="8"
        spellcheck="false"
        placeholder="601857&#10;601899&#10;002371"
      />
      <div class="input-actions">
        <span>已识别 <strong>{{ parsedCodes.length }}</strong> 只</span>
        <div class="input-buttons">
          <button
            data-test="import-trend-squeeze-screen"
            class="secondary-button"
            :disabled="importLoading || loading"
            @click="importTrendSqueezeScreen"
          >{{ importLoading ? (loading ? '正在评分…' : '正在导入…') : '一键导入并评分' }}</button>
          <button data-test="batch-submit" :disabled="loading" @click="runEvaluation">
            {{ loading ? '正在评分…' : '开始批量评分' }}
          </button>
        </div>
      </div>
      <p v-if="importMessage" data-test="trend-squeeze-import-message" class="import-message">{{ importMessage }}</p>
      <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>
    </section>

    <section v-if="response" class="summary-strip">
      <div><span>请求</span><strong>{{ response.requestedCount || 0 }}</strong></div>
      <div><span>完成</span><strong>{{ response.evaluatedCount || 0 }}</strong></div>
      <div><span>尾部通过</span><strong>{{ tailPassedCount }}</strong></div>
      <div><span>数据异常</span><strong>{{ response.errorCount || 0 }}</strong></div>
      <div><span>数据模式</span><strong>仅本地</strong></div>
    </section>

    <section v-if="allResults.length" class="terminal-panel result-panel">
      <div class="panel-title">
        <div><span>02</span><strong>评分结果</strong></div>
        <div class="filter-summary">
          <small>显示 {{ results.length }} / {{ allResults.length }} · 尾部得分相同时按策略总分排序</small>
          <button
            data-test="clear-table-filters"
            class="clear-filter-button"
            :disabled="!hasActiveFilters"
            @click="clearTableFilters"
          >清除筛选</button>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th><th>股票</th><th>评价日</th><th>尾部质量</th><th>尾部结论</th><th>量比</th>
              <th>量能趋势</th><th>5日成交额最低</th><th>收盘低于MA5</th><th>5日收盘波动</th><th>最新交易日K线形态</th><th>K线集合形态</th><th>策略总分</th>
            </tr>
            <tr class="filter-row">
              <th></th>
              <th><input v-model.trim="tableFilters.stock" data-test="filter-stock" placeholder="代码/名称" /></th>
              <th>
                <select v-model="tableFilters.evaluationDate" data-test="filter-evaluation-date">
                  <option value="">全部日期</option>
                  <option v-for="date in evaluationDates" :key="date" :value="date">{{ date }}</option>
                </select>
              </th>
              <th><div class="range-filter"><input v-model="tableFilters.tailQualityMin" data-test="filter-tail-score-min" type="number" min="0" max="20" placeholder="最低" /><input v-model="tableFilters.tailQualityMax" type="number" min="0" max="20" placeholder="最高" /></div></th>
              <th><select v-model="tableFilters.tailPass" data-test="filter-tail-pass"><option value="">全部</option><option value="pass">通过</option><option value="fail">未通过</option></select></th>
              <th><div class="range-filter"><input v-model="tableFilters.volumeRatioMin" type="number" step="0.01" placeholder="最低" /><input v-model="tableFilters.volumeRatioMax" type="number" step="0.01" placeholder="最高" /></div></th>
              <th><select v-model="tableFilters.volumeTrend"><option value="">全部</option><option value="shrinking">缩量</option><option value="not_shrinking">未缩量</option></select></th>
              <th><div class="stacked-filter"><select v-model="tableFilters.turnoverMin" data-test="filter-turnover-min"><option value="">5日最低：全部</option><option value="yes">5日最低：是</option><option value="no">5日最低：否</option><option value="unknown">5日最低：数据不足</option></select><select v-model="tableFilters.turnoverExtreme" data-test="filter-turnover-extreme"><option value="">极致缩量：全部</option><option value="yes">极致缩量：是</option><option value="no">极致缩量：否</option><option value="unknown">极致缩量：数据不足</option></select></div></th>
              <th><select v-model="tableFilters.belowMa5"><option value="">全部</option><option value="yes">是</option><option value="no">否</option><option value="unknown">数据不足</option></select></th>
              <th><div class="range-filter percent-filter"><input v-model="tableFilters.closeRangeMin" type="number" step="0.1" placeholder="最低%" /><input v-model="tableFilters.closeRangeMax" type="number" step="0.1" placeholder="最高%" /></div></th>
              <th><select v-model="tableFilters.latestPattern"><option value="">全部</option><option value="matched">已识别</option><option value="unmatched">未识别</option><option value="INVERTED_HAMMER">倒锤形/射击之星</option></select></th>
              <th>
                <div class="collection-filter">
                  <select v-model="tableFilters.collectionPatternCode"><option value="">全部形态</option><option value="SLOW_ROUNDED_BASE">缓跌圆底</option></select>
                  <select v-model="tableFilters.collectionPatternStatus" data-test="filter-collection-pattern-status"><option value="">全部状态</option><option value="strong">强匹配</option><option value="matched">已匹配</option><option value="forming">形成中</option><option value="not_matched">未匹配</option><option value="data_insufficient">数据不足</option></select>
                  <select v-model="tableFilters.collectionPatternGrade" data-test="filter-collection-pattern-grade"><option value="">全部等级</option><option value="S">S</option><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="UNQUALIFIED">未达标</option></select>
                  <div class="range-filter"><input v-model="tableFilters.collectionPatternScoreMin" data-test="filter-collection-pattern-score-min" type="number" min="0" max="100" placeholder="最低分" /><input v-model="tableFilters.collectionPatternScoreMax" type="number" min="0" max="100" placeholder="最高分" /></div>
                </div>
              </th>
              <th><div class="range-filter"><input v-model="tableFilters.totalScoreMin" type="number" min="0" max="100" placeholder="最低" /><input v-model="tableFilters.totalScoreMax" type="number" min="0" max="100" placeholder="最高" /></div></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(item, index) in results" :key="item.code">
              <tr class="score-row" @click="toggle(item.code)">
                <td class="rank">{{ index + 1 }}</td>
                <td>
                  <button
                    class="code-copy"
                    :data-test="`copy-code-${item.code}`"
                    :title="`复制股票代码 ${item.code}`"
                    @click.stop="copyCode(item.code)"
                  >
                    <strong>{{ item.code }}</strong>
                    <span v-if="copiedCode === item.code">已复制</span>
                  </button>
                  <small>{{ item.name || '名称未收录' }}</small>
                </td>
                <td>{{ item.evaluationDate || '--' }}</td>
                <td><strong class="tail-score" :class="scoreClass(item.tailQualityScore)">{{ item.tailQualityScore }} / 20</strong><small>计入 {{ item.tailScore }} / 20</small></td>
                <td><span class="status" :class="item.tailPass ? 'pass' : 'fail'">{{ item.tailPass ? '量稳价干通过' : '尾部未通过' }}</span></td>
                <td>{{ ratio(item.tailVolumeRatio) }}</td>
                <td :class="item.volumeSlope10 < 0 ? 'positive' : 'negative'">{{ item.volumeSlope10 < 0 ? '缩量' : '未缩量' }}</td>
                <td :data-test="`turnover-min-${item.code}`" :class="{ 'requirement-hit': item.latestTurnover5Min === true }">
                  <strong>5日最低 {{ flagText(item.latestTurnover5Min) }}</strong>
                  <small>{{ amountText(item.latestTurnover) }}</small>
                  <small :data-test="`turnover-extreme-${item.code}`" :class="{ 'requirement-hit': item.latestTurnoverBelowPrevious5Avg60 === true }">今日/前5日均 {{ turnoverRatioText(item.latestToPrevious5TurnoverRatio) }} · 极致缩量 {{ flagText(item.latestTurnoverBelowPrevious5Avg60) }}</small>
                </td>
                <td :data-test="`below-ma5-${item.code}`" :class="{ 'requirement-hit': item.closeBelowMa5 === true }"><strong>{{ flagText(item.closeBelowMa5) }}</strong><small>{{ ma5Text(item) }}</small></td>
                <td>{{ pct(item.closeRange5) }}</td>
                <td :data-test="`latest-pattern-${item.code}`" :class="{ 'requirement-hit': hasMatchedLatestBarPattern(item) }">{{ latestBarPatternSummary(item) }}</td>
                <td :data-test="`collection-pattern-${item.code}`" :class="{ 'requirement-hit': hasMatchedCollectionPattern(item) }">
                  {{ collectionPatternSummary(item) }}
                  <small>{{ collectionPatternRange(item) }}</small>
                </td>
                <td><strong>{{ item.totalScore }} / 100</strong></td>
              </tr>
              <tr v-if="expanded.has(item.code)" class="detail-row">
                <td colspan="13">
                  <div class="detail-grid">
                    <div>
                      <h3>强势趋势收缩初筛</h3>
                      <p :class="item.strongTrendSqueezePass ? 'evidence' : 'risk'">
                        {{ item.strongTrendSqueezePass ? '全部条件通过' : '未通过' }}
                      </p>
                      <p>现价 {{ price(item.trendClose) }} · EMA150 {{ price(item.trendEma150) }} · EMA200 {{ price(item.trendEma200) }}</p>
                      <p>52周低/高 {{ price(item.trendLow250) }} / {{ price(item.trendHigh250) }} · 高位比 {{ pct(item.trendCloseToHighRatio) }}</p>
                      <p>BB {{ priceRange(item.trendBbLower, item.trendBbUpper) }} · KC {{ priceRange(item.trendKcLower, item.trendKcUpper) }}</p>
                      <p v-for="reason in item.strongTrendSqueezeReasons || []" :key="reason" class="risk">{{ trendReasonText(reason) }}</p>
                    </div>
                    <div>
                      <h3>最新交易日K线形态</h3>
                      <template v-for="pattern in latestBarPatternItems(item)" :key="pattern.code">
                        <p :class="pattern.matched ? 'evidence' : 'muted'">{{ pattern.name }} · {{ pattern.matched ? '命中' : '未命中' }} · {{ latestPatternStatusText(pattern.status) }}</p>
                        <template v-if="pattern.code === 'HAMMER' || pattern.code === 'INVERTED_HAMMER'">
                          <p>实体占比 {{ metricPct(pattern, 'body_ratio') }} · 下影/实体 {{ metricRatio(pattern, 'lower_shadow_to_body') }} · 上影/实体 {{ metricRatio(pattern, 'upper_shadow_to_body') }}</p>
                          <p>振幅/前收 {{ metricPct(pattern, 'range_to_previous_close') }} · 振幅/ATR14 {{ metricRatio(pattern, 'range_to_atr14') }}</p>
                          <p v-if="pattern.code === 'INVERTED_HAMMER'">此前5日趋势 {{ metricSignedPct(pattern, 'context_return_5') }} · 此前5日均价 {{ metricPrice(pattern, 'context_ma5') }}</p>
                        </template>
                        <template v-else>
                          <p>路径 {{ latestPatternTypeText(pattern.signal_type) }} · 实体 {{ priceRange(pattern.body_bottom, pattern.body_top) }}</p>
                          <p>支撑区 {{ priceRange(pattern.zone_low, pattern.zone_high) }} · 距支撑 {{ nullablePct(pattern.distance_to_floor_pct) }}</p>
                        </template>
                        <p v-for="reason in pattern.reasons || []" :key="reason" :class="pattern.matched ? 'evidence' : 'muted'">{{ bodyEvidenceText(reason) }}</p>
                        <p v-for="risk in pattern.risks || []" :key="risk" class="risk">{{ latestPatternRiskText(risk) }}</p>
                      </template>
                    </div>
                    <div>
                      <h3>K线集合形态</h3>
                      <template v-for="pattern in collectionPatternItems(item)" :key="pattern.code">
                        <p :class="pattern.matched ? 'evidence' : 'muted'">{{ pattern.name }} {{ patternGradeText(pattern.grade) }} · {{ collectionPatternStatusText(pattern.status) }} · {{ numberText(pattern.score) }}分</p>
                        <p>识别区间 {{ pattern.startDate || '--' }} 至 {{ pattern.endDate || '--' }} · {{ pattern.windowDays || 0 }}个交易日</p>
                        <p>回撤 {{ featurePct(pattern, 'pullbackDepth') }} · 收跌中位数 {{ featurePct(pattern, 'medianDownPct') }}</p>
                        <p>前/中/后斜率 {{ featureSignedPct(pattern, 'earlySlope') }} / {{ featureSignedPct(pattern, 'middleSlope') }} / {{ featureSignedPct(pattern, 'lateSlope') }}</p>
                        <p>底部停留 {{ featureNumber(pattern, 'bottomDays', 0) }}日 / {{ featurePct(pattern, 'bottomDwellRatio') }} · 低点后 {{ featureNumber(pattern, 'barsAfterLow', 0) }}日</p>
                        <p>前/后波动 {{ featurePct(pattern, 'earlyRange') }} / {{ featurePct(pattern, 'lateRange') }} · 收缩比 {{ featureRatio(pattern, 'rangeContractionRatio') }}</p>
                        <p>缓跌 {{ componentScore(pattern, 'slowPullback', 15) }} · 减速 {{ componentScore(pattern, 'deceleration', 25) }} · 底部宽度 {{ componentScore(pattern, 'bottomWidth', 20) }} · 低点后整理 {{ componentScore(pattern, 'afterLow', 10) }}</p>
                        <p>波动收缩 {{ componentScore(pattern, 'volatilityContraction', 12) }} · 收盘聚集 {{ componentScore(pattern, 'closeClustering', 8) }} · K线重叠 {{ componentScore(pattern, 'overlapImprovement', 5) }} · 非V型 {{ componentScore(pattern, 'noVReversal', 5) }}</p>
                        <p v-for="reason in pattern.reasons || []" :key="reason" class="evidence">{{ collectionPatternReasonText(reason) }}</p>
                        <p v-for="warning in pattern.warnings || []" :key="warning" class="risk">{{ collectionPatternWarningText(warning) }}</p>
                      </template>
                      <p v-if="!collectionPatternItems(item).length" class="muted">暂无集合形态诊断</p>
                    </div>
                    <div>
                      <h3>尾部依据</h3>
                      <p v-for="reason in item.tailReasons" :key="reason" class="evidence">{{ tailReasonText(reason) }}</p>
                      <p v-if="!item.tailReasons?.length" class="muted">暂无加分依据</p>
                    </div>
                    <div>
                      <h3>尾部拦截</h3>
                      <p v-for="reason in item.tailRejects" :key="reason" class="risk">{{ tailRejectText(reason) }}</p>
                      <p v-if="!item.tailRejects?.length" class="muted">无尾部硬拦截</p>
                    </div>
                    <div>
                      <h3>总分构成</h3>
                      <p>{{ breakdownText(item.scoreBreakdown) }}</p>
                      <p class="muted">阶段 {{ phaseText(item.phaseStatus) }} · 尾段 {{ item.tailDays || 0 }} 日 · {{ item.scoreModelVersion || '--' }}</p>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!results.length" class="empty-filter-row">
              <td colspan="13">没有符合当前筛选条件的股票，请调整条件或清除筛选。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="errors.length" class="terminal-panel error-panel">
      <div class="panel-title"><div><span>!</span><strong>未完成评分</strong></div></div>
      <div v-for="item in errors" :key="item.code" class="error-item">
        <strong>{{ item.code }}</strong><span>{{ item.name }}</span><em>{{ item.message }}</em>
      </div>
    </section>
  </main>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const api = useApi()
const STOCK_POOL_STORAGE_KEY = 'strategy6.batchEvaluation.stockPool.v1'
const DEFAULT_STOCK_POOL = '601857\n601899\n002371\n688072\n601898\n300604\n601872\n002353\n002493\n688120\n688361\n000977\n000938\n603296\n002648\n688702\n601958'
const rawCodes = ref(loadSavedStockPool())
const loading = ref(false)
const importLoading = ref(false)
const importMessage = ref('')
const errorMessage = ref('')
const copiedCode = ref('')
const response = ref(null)
const expanded = reactive(new Set())
const tableFilters = reactive(createEmptyTableFilters())

const parsedCodes = computed(() => [...new Set(
  rawCodes.value.split(/[\s,，;；]+/).map(code => code.trim()).filter(Boolean),
)])
const allResults = computed(() => response.value?.results || [])
const results = computed(() => allResults.value.filter(matchesTableFilters))
const errors = computed(() => response.value?.errors || [])
const tailPassedCount = computed(() => allResults.value.filter(item => item.tailPass).length)
const evaluationDates = computed(() => [...new Set(allResults.value.map(item => item.evaluationDate).filter(Boolean))].sort().reverse())
const hasActiveFilters = computed(() => Object.values(tableFilters).some(value => value !== ''))

watch(rawCodes, value => {
  try {
    localStorage.setItem(STOCK_POOL_STORAGE_KEY, value)
  } catch (_) {
    // Storage can be unavailable in privacy modes; evaluation still works.
  }
})

function loadSavedStockPool() {
  try {
    const saved = localStorage.getItem(STOCK_POOL_STORAGE_KEY)
    return saved === null ? DEFAULT_STOCK_POOL : saved
  } catch (_) {
    return DEFAULT_STOCK_POOL
  }
}

async function runEvaluation() {
  errorMessage.value = ''
  copiedCode.value = ''
  response.value = null
  clearTableFilters()
  const invalid = parsedCodes.value.filter(code => !/^\d{6}$/.test(code))
  if (!parsedCodes.value.length) {
    errorMessage.value = '请至少输入一个股票代码'
    return false
  }
  if (invalid.length) {
    errorMessage.value = `股票代码必须为6位数字：${invalid.join('、')}`
    return false
  }
  if (parsedCodes.value.length > 200) {
    errorMessage.value = '单次最多评估200只股票'
    return false
  }
  loading.value = true
  try {
    const data = await api.evaluateStrategy6Batch(parsedCodes.value)
    if (!data.ok) throw new Error(data.message || '批量评分失败')
    response.value = data
    return true
  } catch (error) {
    errorMessage.value = error?.message || '批量评分失败'
    return false
  } finally {
    loading.value = false
  }
}

function createEmptyTableFilters() {
  return {
    stock: '', evaluationDate: '', tailQualityMin: '', tailQualityMax: '', tailPass: '',
    volumeRatioMin: '', volumeRatioMax: '', volumeTrend: '', turnoverMin: '', turnoverExtreme: '', belowMa5: '',
    closeRangeMin: '', closeRangeMax: '', latestPattern: '',
    collectionPatternCode: '', collectionPatternStatus: '', collectionPatternGrade: '',
    collectionPatternScoreMin: '', collectionPatternScoreMax: '', totalScoreMin: '', totalScoreMax: '',
  }
}

function matchesNumberRange(value, minimum, maximum, multiplier = 1) {
  if (value == null || value === '') return minimum === '' && maximum === ''
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return minimum === '' && maximum === ''
  const comparable = numeric * multiplier
  if (minimum !== '' && comparable < Number(minimum)) return false
  if (maximum !== '' && comparable > Number(maximum)) return false
  return true
}

function matchesBooleanFilter(value, filter) {
  if (!filter) return true
  if (filter === 'unknown') return value == null
  return filter === 'yes' ? value === true : value === false
}

function matchesTableFilters(item) {
  const stockQuery = tableFilters.stock.toLowerCase()
  if (stockQuery && !`${item.code || ''} ${item.name || ''}`.toLowerCase().includes(stockQuery)) return false
  if (tableFilters.evaluationDate && item.evaluationDate !== tableFilters.evaluationDate) return false
  if (!matchesNumberRange(item.tailQualityScore, tableFilters.tailQualityMin, tableFilters.tailQualityMax)) return false
  if (tableFilters.tailPass === 'pass' && item.tailPass !== true) return false
  if (tableFilters.tailPass === 'fail' && item.tailPass === true) return false
  if (!matchesNumberRange(item.tailVolumeRatio, tableFilters.volumeRatioMin, tableFilters.volumeRatioMax)) return false
  if (tableFilters.volumeTrend === 'shrinking' && !(Number(item.volumeSlope10) < 0)) return false
  if (tableFilters.volumeTrend === 'not_shrinking' && Number(item.volumeSlope10) < 0) return false
  if (!matchesBooleanFilter(item.latestTurnover5Min, tableFilters.turnoverMin)) return false
  if (!matchesBooleanFilter(item.latestTurnoverBelowPrevious5Avg60, tableFilters.turnoverExtreme)) return false
  if (!matchesBooleanFilter(item.closeBelowMa5, tableFilters.belowMa5)) return false
  if (!matchesNumberRange(item.closeRange5, tableFilters.closeRangeMin, tableFilters.closeRangeMax, 100)) return false
  if (tableFilters.latestPattern === 'matched' && !hasMatchedLatestBarPattern(item)) return false
  if (tableFilters.latestPattern === 'unmatched' && hasMatchedLatestBarPattern(item)) return false
  if (tableFilters.latestPattern === 'INVERTED_HAMMER' && !latestBarPatternItems(item).some(pattern => pattern.code === 'INVERTED_HAMMER' && pattern.matched)) return false
  const collectionPatterns = collectionPatternItems(item)
  const selectedPatterns = tableFilters.collectionPatternCode
    ? collectionPatterns.filter(pattern => pattern.code === tableFilters.collectionPatternCode)
    : collectionPatterns
  if (tableFilters.collectionPatternCode && !selectedPatterns.length) return false
  if (tableFilters.collectionPatternStatus === 'strong' && !selectedPatterns.some(pattern => pattern.strongMatched)) return false
  if (tableFilters.collectionPatternStatus === 'matched' && !selectedPatterns.some(pattern => pattern.matched)) return false
  if (tableFilters.collectionPatternStatus === 'forming' && !selectedPatterns.some(pattern => pattern.status === 'FORMING')) return false
  if (tableFilters.collectionPatternStatus === 'not_matched' && !selectedPatterns.some(pattern => pattern.status === 'NOT_MATCHED')) return false
  if (tableFilters.collectionPatternStatus === 'data_insufficient' && !selectedPatterns.some(pattern => pattern.status === 'DATA_INSUFFICIENT')) return false
  if (tableFilters.collectionPatternGrade && !selectedPatterns.some(pattern => pattern.grade === tableFilters.collectionPatternGrade)) return false
  if ((tableFilters.collectionPatternScoreMin !== '' || tableFilters.collectionPatternScoreMax !== '') && !selectedPatterns.some(pattern => matchesNumberRange(pattern.score, tableFilters.collectionPatternScoreMin, tableFilters.collectionPatternScoreMax))) return false
  return matchesNumberRange(item.totalScore, tableFilters.totalScoreMin, tableFilters.totalScoreMax)
}

function clearTableFilters() {
  Object.assign(tableFilters, createEmptyTableFilters())
}

async function importTrendSqueezeScreen() {
  errorMessage.value = ''
  importMessage.value = ''
  importLoading.value = true
  try {
    const data = await api.getLatestStrategy6TrendSqueezeScreen()
    const stocks = Array.isArray(data.stocks) ? data.stocks : []
    if (!data.taskId || !stocks.length) {
      throw new Error('暂无已完成任务的新初筛股票，请先重新扫描策略6')
    }
    rawCodes.value = stocks.map(item => item.code).filter(Boolean).join('\n')
    importMessage.value = `来源任务 ${data.taskId} · 已导入 ${stocks.length} 只，正在评分`
    const succeeded = await runEvaluation()
    importMessage.value = succeeded
      ? `来源任务 ${data.taskId} · 已导入并完成评分 ${stocks.length} 只`
      : `来源任务 ${data.taskId} · 已导入 ${stocks.length} 只，但评分失败`
  } catch (error) {
    errorMessage.value = error?.message || '新初筛股票导入失败'
  } finally {
    importLoading.value = false
  }
}

function toggle(code) {
  expanded.has(code) ? expanded.delete(code) : expanded.add(code)
}
async function copyCode(code) {
  try {
    errorMessage.value = ''
    if (!navigator.clipboard?.writeText) throw new Error('当前浏览器不支持剪贴板')
    await navigator.clipboard.writeText(code)
    copiedCode.value = code
  } catch (error) {
    errorMessage.value = `复制失败：${error?.message || '无法访问剪贴板'}`
  }
}
function pct(value) { return `${(Number(value || 0) * 100).toFixed(2)}%` }
function signedPct(value) { const n = Number(value || 0) * 100; return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%` }
function ratio(value) { return Number(value || 0).toFixed(2) }
function price(value) { return value == null || value === '' ? '--' : Number(value).toFixed(2) }
function priceRange(low, high) { return `${price(low)} - ${price(high)}` }
function nullablePct(value) { return value == null ? '--' : signedPct(value) }
function scoreClass(value) { return value >= 18 ? 'excellent' : value >= 14 ? 'good' : 'weak' }
function flagText(value) { return value == null ? '数据不足' : value ? '是' : '否' }
function amountText(value) { return value == null ? '--' : `${(Number(value) / 100000000).toFixed(2)}亿` }
function turnoverRatioText(value) { return value == null ? '--' : `${(Number(value) * 100).toFixed(1)}%` }
function ma5Text(item) { return item.ma5 == null ? '--' : `${price(item.latestClose)} / ${price(item.ma5)}` }
function phaseText(value) {
  return {
    PHASE_VALID: '阶段有效', START_NOT_FOUND: '未识别强势启动', START_TOO_RECENT: '启动时间过近',
    START_TOO_OLD: '启动时间过久', CONSOLIDATION_TOO_SHORT: '整理期过短',
    CONSOLIDATION_TOO_LONG: '整理期过长', TAIL_VOLUME_BASE_INSUFFICIENT: '尾部量能基准不足',
  }[value] || value || '--'
}
function tailReasonText(value) {
  return {
    'volume:non_overlap_tail_dry': '量能明显萎缩',
    'volume:non_overlap_tail_strong_dry': '量能达到强萎缩',
    'volume:slope_down': '近10日量能趋势向下',
    'price:no_new_low': '尾部未创新低',
    'price:close_range_stable': '5日收盘区间稳定',
    'price:return_5_stable': '5日收益保持稳定',
    'risk:no_big_down_volume': '没有放量大跌',
  }[value] || value
}
function tailRejectText(value) {
  return {
    BIG_DOWN_VOLUME: '存在放量大跌', TAIL_NEW_LOW: '尾部收盘创新低',
    TAIL_LOW_DECLINING: '尾部低点继续下移', TAIL_CLOSE_RANGE_GT_8PCT: '5日收盘波动过大',
    TAIL_VOLUME_NOT_DRY: '尾部量能未充分萎缩', TAIL_RETURN_5_TOO_WEAK: '5日走势过弱',
    TAIL_SINGLE_DROP_TOO_WEAK: '尾部存在过大的单日下跌', TAIL_VOLUME_BASE_INSUFFICIENT: '尾部量能基准不足',
  }[value] || value
}
function trendReasonText(value) {
  return {
    TREND_SQUEEZE_HISTORY_LT_250: '有效历史不足250个交易日',
    TREND_SQUEEZE_DATA_INSUFFICIENT: '初筛指标无法计算',
    CLOSE_LE_10: '股价不高于10元', CLOSE_LT_52W_LOW_1_30: '未高于52周最低价30%',
    CLOSE_LT_52W_HIGH_0_70: '低于52周最高价70%', CLOSE_GT_52W_HIGH: '收盘价异常高于52周最高价',
    EMA150_LE_EMA200: 'EMA150不高于EMA200', CLOSE_LE_EMA150: '收盘价不高于EMA150',
    CLOSE_LE_EMA200: '收盘价不高于EMA200', BB_NOT_INSIDE_KC: '布林带未完全进入肯特纳通道',
  }[value] || value
}
function breakdownText(score = {}) {
  return `启动 ${score.strongStart || 0} + 形态 ${score.pattern || 0} + 支撑 ${score.support || 0} + 尾部 ${score.tail || 0} + 盈亏比 ${score.objectiveRiskReward || 0} + 强弱风险 ${score.relativeStrengthRisk || 0}`
}
function latestBarPatternItems(item) { return Array.isArray(item.latestBarPatterns) ? item.latestBarPatterns : [] }
function hasMatchedLatestBarPattern(item) { return latestBarPatternItems(item).some(pattern => pattern.matched) }
function latestBarPatternSummary(item) {
  const matched = latestBarPatternItems(item).filter(pattern => pattern.matched)
  return matched.length ? matched.map(pattern => pattern.name).join(' / ') : '未识别到配置形态'
}
function latestPatternStatusText(value) { return { DETECTED: '当日识别', CONFIRMING: '后续确认中', CONFIRMED: '已确认', NOT_MATCHED: '未命中' }[value] || value || '--' }
function latestPatternTypeText(value) {
  return { FAILED_BREAK_RECLAIM: '假跌破收回', BODY_FLOOR_HOLD: '守住实体支撑', POTENTIAL_BODY_PIVOT: '潜在实体拐点', HIGHER_BODY_LOW: '更高实体低点', BULLISH_HAMMER: '阳线锤子', BEARISH_HAMMER: '阴线锤子', BULLISH_INVERTED_HAMMER: '阳线倒锤子', BEARISH_INVERTED_HAMMER: '阴线倒锤子', SHOOTING_STAR: '射击之星', UPPER_SHADOW_HAMMER_UNCLEAR: '上影锤形位置不明确', NONE: '无' }[value] || value || '--'
}
function bodyEvidenceText(value) {
  return { LATEST_LOW_BREAK_RECLAIMED_BY_BODY: '盘中跌破后实体收回', LATEST_BODY_HELD_SUPPORT_ZONE: '实体守住支撑区', LATEST_BODY_POTENTIAL_PIVOT: '最新实体形成潜在低点', LATEST_BAR_NO_VALID_BODY_LOW: '最新K线未形成有效实体低点', LATEST_BAR_EFFECTIVE_HAMMER: '最新交易日形成有效锤子线', LATEST_BAR_EFFECTIVE_INVERTED_HAMMER: '回调背景下形成有效倒锤子线' }[value] || value
}
function latestPatternRiskText(value) {
  return {
    HAMMER_ATR14_DATA_INSUFFICIENT: '不足15根K线，无法计算ATR14', HAMMER_OHLC_INVALID: 'OHLC数据非法',
    HAMMER_ZERO_RANGE_OR_BODY: '零振幅、零实体或ATR14无效', HAMMER_BODY_RATIO_LT_10PCT: '实体占比低于10%',
    HAMMER_BODY_RATIO_GT_25PCT: '实体占比超过25%', HAMMER_LOWER_SHADOW_LT_BODY_2: '下影线不足实体2倍',
    HAMMER_UPPER_SHADOW_GT_BODY_0_1: '上影线超过实体10%', HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT: '总振幅不足前收盘0.8%',
    HAMMER_RANGE_LT_ATR14_0_5: '总振幅不足ATR14的50%', BEARISH_HAMMER_REQUIRES_CONFIRMATION: '阴线锤子反转力度较弱，仍需确认',
    INVERTED_HAMMER_ATR14_DATA_INSUFFICIENT: '不足15根K线，无法计算倒锤子线', INVERTED_HAMMER_OHLC_INVALID: '倒锤子线OHLC数据非法',
    INVERTED_HAMMER_ZERO_RANGE_OR_BODY: '倒锤子线零振幅、零实体或ATR14无效', INVERTED_HAMMER_CONTEXT_DATA_INSUFFICIENT: '倒锤子线位置判断数据不足',
    INVERTED_HAMMER_BODY_RATIO_LT_10PCT: '倒锤子线实体占比低于10%', INVERTED_HAMMER_BODY_RATIO_GT_25PCT: '倒锤子线实体占比超过25%',
    INVERTED_HAMMER_UPPER_SHADOW_LT_BODY_2: '倒锤子线上影线不足实体2倍', INVERTED_HAMMER_LOWER_SHADOW_GT_BODY_0_1: '倒锤子线下影线超过实体10%',
    INVERTED_HAMMER_RANGE_LT_PREVIOUS_CLOSE_0_8PCT: '倒锤子线总振幅不足前收盘0.8%', INVERTED_HAMMER_RANGE_LT_ATR14_0_5: '倒锤子线总振幅不足ATR14的50%',
    INVERTED_HAMMER_REQUIRES_CONFIRMATION: '倒锤子线仍需后续交易日确认', SHOOTING_STAR_AFTER_RISE: '上涨背景下属于射击之星风险',
    INVERTED_HAMMER_CONTEXT_UNCLEAR: '上影锤形K线位置不明确，不作为有效倒锤子线',
    REQUIRES_TWO_COMPLETED_BARS_TO_CONFIRM_PIVOT: '需要后续两根完整K线确认实体拐点',
  }[value] || value
}
function metricPct(pattern, key) { const value = pattern.metrics?.[key]; return value == null ? '--' : pct(value) }
function metricRatio(pattern, key) { const value = pattern.metrics?.[key]; return value == null ? '--' : `${Number(value).toFixed(2)}倍` }
function metricSignedPct(pattern, key) { const value = pattern.metrics?.[key]; return value == null ? '--' : signedPct(value) }
function metricPrice(pattern, key) { return price(pattern.metrics?.[key]) }
function collectionPatternItems(item) { return Array.isArray(item.klineCollectionPatterns) ? item.klineCollectionPatterns : [] }
function hasMatchedCollectionPattern(item) { return collectionPatternItems(item).some(pattern => pattern.matched) }
function primaryCollectionPattern(item) { return collectionPatternItems(item)[0] || null }
function collectionPatternSummary(item) {
  const pattern = primaryCollectionPattern(item)
  if (!pattern) return '未识别集合形态'
  return pattern.matched
    ? `${pattern.name} ${patternGradeText(pattern.grade)} · ${numberText(pattern.score)}`
    : `未识别 · 最高${numberText(pattern.score)}`
}
function collectionPatternRange(item) {
  const pattern = primaryCollectionPattern(item)
  return pattern?.startDate && pattern?.endDate ? `${pattern.startDate} 至 ${pattern.endDate}` : '--'
}
function collectionPatternStatusText(value) { return { STRONG_MATCHED: '强匹配', MATCHED: '已匹配', FORMING: '形成中', NOT_MATCHED: '未匹配', DATA_INSUFFICIENT: '数据不足', DATA_INVALID: '最新K线非法', EVALUATION_FAILED: '诊断失败' }[value] || value || '--' }
function patternGradeText(value) { return value === 'UNQUALIFIED' ? '未达标' : value || '--' }
function numberText(value) { return value == null ? '--' : Number(value).toFixed(Number(value) % 1 ? 1 : 0) }
function featureNumber(pattern, key, digits = 2) { const value = pattern.features?.[key]; return value == null ? '--' : Number(value).toFixed(digits) }
function featurePct(pattern, key) { const value = pattern.features?.[key]; return value == null ? '--' : `${(Number(value) * 100).toFixed(2)}%` }
function featureSignedPct(pattern, key) { const value = pattern.features?.[key]; return value == null ? '--' : signedPct(value) }
function featureRatio(pattern, key) { const value = pattern.features?.[key]; return value == null ? '--' : Number(value).toFixed(2) }
function componentScore(pattern, key, maximum) { const value = pattern.componentScores?.[key]; return `${numberText(value)} / ${maximum}` }
function collectionPatternReasonText(value) {
  return {
    PULLBACK_PACE_GENTLE: '回调节奏温和', DECLINE_DECELERATING: '下跌速度总体减慢',
    BOTTOM_AREA_HAS_TIME_WIDTH: '低位形成时间宽度', LATE_PATH_STABILIZING: '后半段价格逐渐稳定',
    NO_V_REVERSAL: '未出现急跌V反',
  }[value] || value
}
function collectionPatternWarningText(value) {
  return {
    PATTERN_DATA_INSUFFICIENT: '有效K线不足10个交易日', LATEST_BAR_INVALID: '最新交易日K线数据非法，未回退旧日期', PATTERN_EVALUATION_FAILED: '集合形态诊断执行失败', PRIOR_PULLBACK_MISSING: '窗口前段缺少有效回调',
    DECLINE_NOT_DECELERATING: '下跌速度尚未改善', BOTTOM_AREA_TOO_NARROW: '底部停留时间不足',
    LATE_PATH_NOT_STABLE: '后半段尚未稳定', V_REVERSAL_OR_ALREADY_EXTENDED: '疑似V型反转或已明显离开底部',
  }[value] || value
}
</script>

<style scoped>
.batch-page { padding: 24px; color: var(--text-primary); }
.page-header { display: flex; justify-content: space-between; gap: 24px; margin-bottom: 18px; }
.eyebrow { color: var(--gold); font: 11px/1 var(--font-mono); letter-spacing: .18em; }
h1 { margin: 8px 0; font-size: 26px; } .page-header p { color: var(--text-secondary); margin: 0; }
.tail-priority { min-width: 230px; padding: 14px 18px; border: 1px solid rgba(214,168,74,.45); background: rgba(214,168,74,.06); display: flex; flex-direction: column; }
.tail-priority span,.tail-priority small { color: var(--text-muted); font-size: 11px; }.tail-priority strong { color: var(--gold); margin: 5px 0; font-size: 18px; }
.terminal-panel { background: rgba(12,20,31,.92); border: 1px solid var(--border); }
.input-panel,.result-panel,.error-panel { padding: 16px; margin-bottom: 16px; }
.panel-title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; color: var(--text-muted); }
.panel-title div { display: flex; gap: 10px; align-items: center; }.panel-title div span { color: var(--gold); font: 12px var(--font-mono); }.panel-title strong { color: var(--text-primary); }
.panel-title .filter-summary { justify-content: flex-end; }.clear-filter-button { padding: 5px 10px; color: var(--gold); background: transparent; border: 1px solid rgba(214,168,74,.45); font-size: 11px; }
textarea { width: 100%; box-sizing: border-box; resize: vertical; padding: 13px; color: #dce7f4; background: #080f18; border: 1px solid #273648; font: 13px/1.7 var(--font-mono); }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; color: var(--text-muted); }.input-actions strong { color: var(--gold); }
.input-buttons { display: flex; gap: 10px; align-items: center; }.secondary-button { color: var(--gold); background: transparent; border: 1px solid rgba(214,168,74,.6); }.import-message { color: var(--gold); margin: 10px 0 0; font: 12px var(--font-mono); }
button { padding: 9px 22px; color: #111; background: var(--gold); border: 0; border-radius: 3px; font-weight: 700; cursor: pointer; }button:disabled { opacity: .55; }
.form-error { color: var(--danger); margin: 10px 0 0; }
.summary-strip { display: grid; grid-template-columns: repeat(5,1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); margin-bottom: 16px; }.summary-strip div { background: #0c1420; padding: 12px 16px; display: flex; flex-direction: column; }.summary-strip span { color: var(--text-muted); font-size: 11px; }.summary-strip strong { margin-top: 4px; font: 18px var(--font-mono); }
.table-wrap { overflow-x: auto; }table { width: 100%; border-collapse: collapse; font-size: 12px; }th { padding: 10px 9px; text-align: left; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }td { padding: 11px 9px; border-bottom: 1px solid rgba(54,70,90,.55); white-space: nowrap; }td small { display: block; color: var(--text-muted); margin-top: 3px; }.score-row { cursor: pointer; }.score-row:hover { background: rgba(255,255,255,.025); }.rank { color: var(--gold); font-family: var(--font-mono); }
.filter-row th { padding: 6px 5px 9px; background: #09111b; }.filter-row input,.filter-row select { width: 100%; min-width: 82px; box-sizing: border-box; padding: 6px 7px; color: var(--text-secondary); background: #080f18; border: 1px solid #273648; border-radius: 2px; font: 11px var(--font-mono); }.filter-row input:focus,.filter-row select:focus { outline: none; border-color: rgba(214,168,74,.75); }.range-filter { display: grid; grid-template-columns: repeat(2, minmax(58px, 1fr)); gap: 4px; min-width: 126px; }.stacked-filter,.collection-filter { display: grid; gap: 4px; min-width: 145px; }.collection-filter { min-width: 170px; }.percent-filter { min-width: 146px; }.empty-filter-row td { padding: 24px; color: var(--text-muted); text-align: center; }
.code-copy { display: inline-flex; align-items: center; gap: 6px; padding: 0; color: #dce7f4; background: transparent; border: 0; font: 12px var(--font-mono); cursor: copy; }.code-copy:hover strong { color: var(--gold); text-decoration: underline; }.code-copy span { color: var(--gold); font: 10px var(--font-mono); }
.tail-score { font: 700 15px var(--font-mono); }.tail-score.excellent { color: #f2c66d; }.tail-score.good,.positive { color: var(--up-red); }.tail-score.weak,.negative { color: var(--down-green); }
.requirement-hit { color: var(--up-red); font-weight: 700; }
.status { padding: 3px 7px; border: 1px solid; }.status.pass { color: var(--up-red); border-color: rgba(223,72,72,.45); }.status.fail { color: var(--text-muted); border-color: var(--border); }
.detail-row td { padding: 0; background: #09111b; }.detail-grid { padding: 14px 18px; display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; white-space: normal; }.detail-grid h3 { color: var(--text-secondary); font-size: 12px; margin: 0 0 8px; }.detail-grid p { margin: 5px 0; }.evidence { color: #d8b35f; }.risk { color: #e57575; }.muted { color: var(--text-muted); }
.error-item { display: grid; grid-template-columns: 100px 150px 1fr; padding: 9px 0; border-top: 1px solid var(--border); }.error-item em { color: var(--danger); font-style: normal; }
@media (max-width: 900px) { .page-header { flex-direction: column; }.summary-strip { grid-template-columns: repeat(2,1fr); }.detail-grid { grid-template-columns: 1fr; }.batch-page { padding: 14px; } }
</style>
