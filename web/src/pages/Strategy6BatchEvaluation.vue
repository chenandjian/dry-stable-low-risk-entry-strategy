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

    <section v-if="results.length" class="terminal-panel result-panel">
      <div class="panel-title">
        <div><span>02</span><strong>评分结果</strong></div>
        <small>尾部得分相同时按策略总分排序</small>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th><th>股票</th><th>评价日</th><th>尾部质量</th><th>尾部结论</th><th>量比</th>
              <th>量能趋势</th><th>5日收盘波动</th><th>5日涨跌</th><th>实体支撑底评分</th><th>最新交易日K线形态</th><th>策略总分</th><th>当前分类</th>
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
                <td>{{ pct(item.closeRange5) }}</td>
                <td :class="numberClass(item.return5)">{{ signedPct(item.return5) }}</td>
                <td><strong>{{ item.bodySupportScore ?? 0 }} / 10</strong><small>{{ bodySupportStatusText(item.bodySupportStatus) }}</small></td>
                <td>{{ latestBarPatternSummary(item) }}</td>
                <td><strong>{{ item.totalScore }} / 100</strong></td>
                <td>{{ candidateText(item.candidateType) }}</td>
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
                      <h3>实体支撑底评分</h3>
                      <p><strong>{{ item.bodySupportScore ?? 0 }} / 10</strong> · {{ bodySupportStatusText(item.bodySupportStatus) }} · {{ bodySupportTypeText(item.bodySupportType) }}</p>
                      <p>支撑 {{ price(item.bodySupportFloorPrice) }} · 区间 {{ priceRange(item.bodySupportZoneLow, item.bodySupportZoneHigh) }}</p>
                      <p>有效拐点 {{ item.bodySupportPivotCount ?? 0 }} · 独立测试 {{ item.bodySupportIndependentTouchCount ?? 0 }}</p>
                      <p>恢复 {{ item.bodySupportRecoveryPass ? '通过' : '未通过' }} · {{ ratio(item.bodySupportRecoveryAtr) }} ATR · 低价拒绝率 {{ nullablePct(item.bodySupportRejectionRatio) }}</p>
                      <p class="muted">独立诊断分，不计入策略6总分</p>
                    </div>
                    <div>
                      <h3>最新交易日K线形态</h3>
                      <template v-for="pattern in latestBarPatternItems(item)" :key="pattern.code">
                        <p :class="pattern.matched ? 'evidence' : 'muted'">{{ pattern.name }} · {{ pattern.matched ? '命中' : '未命中' }} · {{ latestPatternStatusText(pattern.status) }}</p>
                        <p>路径 {{ latestPatternTypeText(pattern.signal_type) }} · 实体 {{ priceRange(pattern.body_bottom, pattern.body_top) }}</p>
                        <p>支撑区 {{ priceRange(pattern.zone_low, pattern.zone_high) }} · 距支撑 {{ nullablePct(pattern.distance_to_floor_pct) }}</p>
                        <p v-for="reason in pattern.reasons || []" :key="reason" :class="pattern.matched ? 'evidence' : 'muted'">{{ bodyEvidenceText(reason) }}</p>
                      </template>
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

const parsedCodes = computed(() => [...new Set(
  rawCodes.value.split(/[\s,，;；]+/).map(code => code.trim()).filter(Boolean),
)])
const results = computed(() => response.value?.results || [])
const errors = computed(() => response.value?.errors || [])
const tailPassedCount = computed(() => results.value.filter(item => item.tailPass).length)

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
function numberClass(value) { return Number(value) >= 0 ? 'positive' : 'negative' }
function scoreClass(value) { return value >= 18 ? 'excellent' : value >= 14 ? 'good' : 'weak' }
function candidateText(value) {
  return { KEY_CANDIDATE: '重点候选', READY_CANDIDATE: '准备候选', WATCH_CANDIDATE: '观察候选', REJECTED: '未入选' }[value] || value
}
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
function latestBarPatternSummary(item) {
  const matched = latestBarPatternItems(item).filter(pattern => pattern.matched)
  return matched.length ? matched.map(pattern => pattern.name).join(' / ') : '未识别到配置形态'
}
function bodySupportStatusText(value) {
  return { BODY_SUPPORT_STRONG: '强实体支撑', BODY_SUPPORT_CONFIRMED: '实体支撑已确认', BODY_SUPPORT_FORMING: '实体支撑形成中', BODY_SUPPORT_WEAKENED: '实体支撑转弱', BODY_SUPPORT_BROKEN: '实体支撑失效', BODY_SUPPORT_NONE: '无有效实体支撑', DISABLED: '未启用' }[value] || value || '--'
}
function bodySupportTypeText(value) {
  return { SINGLE_BODY_PIVOT: '单实体拐点', FLAT_BODY_FLOOR: '水平实体底', RISING_BODY_FLOOR: '抬高实体底', FAILED_BREAK_BODY_FLOOR: '假跌破实体底', COMPOSITE_BODY_FLOOR: '复合实体底', NONE: '未识别' }[value] || value || '--'
}
function latestPatternStatusText(value) { return { CONFIRMING: '后续确认中', CONFIRMED: '已确认', NOT_MATCHED: '未命中' }[value] || value || '--' }
function latestPatternTypeText(value) {
  return { FAILED_BREAK_RECLAIM: '假跌破收回', BODY_FLOOR_HOLD: '守住实体支撑', POTENTIAL_BODY_PIVOT: '潜在实体拐点', HIGHER_BODY_LOW: '更高实体低点', NONE: '无' }[value] || value || '--'
}
function bodyEvidenceText(value) {
  return { LATEST_LOW_BREAK_RECLAIMED_BY_BODY: '盘中跌破后实体收回', LATEST_BODY_HELD_SUPPORT_ZONE: '实体守住支撑区', LATEST_BODY_POTENTIAL_PIVOT: '最新实体形成潜在低点', LATEST_BAR_NO_VALID_BODY_LOW: '最新K线未形成有效实体低点' }[value] || value
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
textarea { width: 100%; box-sizing: border-box; resize: vertical; padding: 13px; color: #dce7f4; background: #080f18; border: 1px solid #273648; font: 13px/1.7 var(--font-mono); }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; color: var(--text-muted); }.input-actions strong { color: var(--gold); }
.input-buttons { display: flex; gap: 10px; align-items: center; }.secondary-button { color: var(--gold); background: transparent; border: 1px solid rgba(214,168,74,.6); }.import-message { color: var(--gold); margin: 10px 0 0; font: 12px var(--font-mono); }
button { padding: 9px 22px; color: #111; background: var(--gold); border: 0; border-radius: 3px; font-weight: 700; cursor: pointer; }button:disabled { opacity: .55; }
.form-error { color: var(--danger); margin: 10px 0 0; }
.summary-strip { display: grid; grid-template-columns: repeat(5,1fr); gap: 1px; background: var(--border); border: 1px solid var(--border); margin-bottom: 16px; }.summary-strip div { background: #0c1420; padding: 12px 16px; display: flex; flex-direction: column; }.summary-strip span { color: var(--text-muted); font-size: 11px; }.summary-strip strong { margin-top: 4px; font: 18px var(--font-mono); }
.table-wrap { overflow-x: auto; }table { width: 100%; border-collapse: collapse; font-size: 12px; }th { padding: 10px 9px; text-align: left; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }td { padding: 11px 9px; border-bottom: 1px solid rgba(54,70,90,.55); white-space: nowrap; }td small { display: block; color: var(--text-muted); margin-top: 3px; }.score-row { cursor: pointer; }.score-row:hover { background: rgba(255,255,255,.025); }.rank { color: var(--gold); font-family: var(--font-mono); }
.code-copy { display: inline-flex; align-items: center; gap: 6px; padding: 0; color: #dce7f4; background: transparent; border: 0; font: 12px var(--font-mono); cursor: copy; }.code-copy:hover strong { color: var(--gold); text-decoration: underline; }.code-copy span { color: var(--gold); font: 10px var(--font-mono); }
.tail-score { font: 700 15px var(--font-mono); }.tail-score.excellent { color: #f2c66d; }.tail-score.good,.positive { color: var(--up-red); }.tail-score.weak,.negative { color: var(--down-green); }
.status { padding: 3px 7px; border: 1px solid; }.status.pass { color: var(--up-red); border-color: rgba(223,72,72,.45); }.status.fail { color: var(--text-muted); border-color: var(--border); }
.detail-row td { padding: 0; background: #09111b; }.detail-grid { padding: 14px 18px; display: grid; grid-template-columns: repeat(3,1fr); gap: 24px; white-space: normal; }.detail-grid h3 { color: var(--text-secondary); font-size: 12px; margin: 0 0 8px; }.detail-grid p { margin: 5px 0; }.evidence { color: #d8b35f; }.risk { color: #e57575; }.muted { color: var(--text-muted); }
.error-item { display: grid; grid-template-columns: 100px 150px 1fr; padding: 9px 0; border-top: 1px solid var(--border); }.error-item em { color: var(--danger); font-style: normal; }
@media (max-width: 900px) { .page-header { flex-direction: column; }.summary-strip { grid-template-columns: repeat(2,1fr); }.detail-grid { grid-template-columns: 1fr; }.batch-page { padding: 14px; } }
</style>
