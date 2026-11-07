<template>
  <main class="us-research">
    <header><small>STRATEGY 6 · US RESEARCH</small><h1>美股策略6研究</h1>
      <p>TickFlow免费端 · forward前复权 · 原始volume · 独立美股数据库</p></header>
    <aside class="warning"><strong>研究模式：未启用市场过滤，不是正式候选或买入建议。</strong>
      <p>成交量拆股口径尚未独立核验。估算成交额＝前复权收盘价 × 供应商成交量，不等于真实成交额；参数未完成美股收益调优。</p>
      <p>免费日线可能延迟发布。缺少目标交易日时明确失败，不冒充停牌或用旧数据生成当天结果。</p></aside>
    <section class="inputs">
      <label>股票代码（最多200只）<textarea v-model="symbolsText" rows="4" placeholder="AAPL&#10;MSFT&#10;BRK.B" /></label>
      <div class="controls">
        <label>请求日线根数<input v-model.number="count" type="number" min="500" max="3000"></label>
        <label>评估日期（留空＝最近完整交易日）<input v-model="asOf" type="date"></label>
        <label><input v-model="localOnly" type="checkbox">仅使用本地数据，不请求网络</label>
        <label><input v-model="force" type="checkbox" :disabled="localOnly">强制重新拉取</label>
        <button data-test="start" :disabled="starting || running || !symbolsText.trim()" @click="start()">{{ starting ? '提交中…' : '开始美股研究扫描' }}</button>
      </div>
    </section>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <section class="task-bar">
      <label>最近20个美股研究任务<select v-model="selectedId"><option value="">请选择</option>
        <option v-for="item in tasks" :key="item.task_id" :value="item.task_id">{{ item.started_at }} · {{ statusLabel(item.status) }} · {{ item.task_id.slice(-8) }}</option>
        <option v-if="selectedId && !tasks.some(item => item.task_id === selectedId)" :value="selectedId">{{ selectedId }}</option>
      </select></label><button @click="refresh">刷新任务</button>
    </section>
    <section v-if="task" class="results">
      <div class="summary"><strong>{{ statusLabel(task.status) }}</strong><span>{{ task.progress?.phase }}：{{ task.progress?.processed || 0 }}/{{ task.progress?.total || 0 }}</span>
        <span>当前：{{ task.progress?.symbols?.join(', ') || '—' }}</span></div>
      <p>评估日 {{ task.context?.target_trade_date || '—' }} · 最近完整交易日 {{ task.context?.live_target_trade_date || task.context?.target_trade_date || '—' }}
        <strong v-if="task.context?.historical_evaluation"> · 历史日期研究，非当前信号</strong></p>
      <p v-if="task.error" class="error">{{ task.error }}</p>
      <div class="task-bar"><label><input v-model="onlyPassed" type="checkbox">只显示研究命中</label>
        <span>命中 {{ task.candidates || 0 }} · 失败 {{ failedCount }}</span>
        <button :disabled="running || starting || !failedCount" @click="start(task.task_id)">仅重试失败股票</button></div>
      <div class="table-scroll"><table><thead><tr><th>代码（点击复制）</th><th>评估日</th><th>收盘 USD</th><th>评分</th><th>原始尾部分</th><th>尾段量比</th><th>研究分层</th><th>排除 / 失败原因</th></tr></thead>
        <tbody><tr v-for="stock in visibleStocks" :key="stock.symbol">
          <td><button class="code" @click="copy(stock.symbol)">{{ stock.symbol }}</button></td>
          <td>{{ stock.evaluation_date || '—' }}</td><td>{{ format(stock.candidate?.current_price) }}</td>
          <td>{{ stock.candidate?.total_score ?? '—' }}</td><td>{{ stock.candidate?.tail_score ?? '—' }}</td>
          <td>{{ format(stock.candidate?.tail_volume_ratio) }}</td>
          <td>{{ tierLabel(stock) }}</td><td class="reason">{{ stock.error || stock.candidate?.reject_reasons?.join(' / ') || '未触发硬性排除；仍仅为研究结果' }}</td>
        </tr><tr v-if="!visibleStocks.length"><td colspan="8">{{ running ? '等待逐批入库及评估结果…' : '没有符合显示条件的记录' }}</td></tr></tbody></table></div>
      <p v-if="copied">已复制 {{ copied }}</p>
      <details><summary>估算成交额与数据口径</summary>
        <p v-for="stock in task.stocks?.filter(item => item.candidate)" :key="stock.symbol">{{ stock.symbol }}：
          估算 {{ format(stock.candidate.latest_turnover_estimated_usd) }} USD · 成交量 {{ stock.candidate.latest_volume }} ·
          实际成交额 {{ stock.candidate.latest_turnover_actual ?? '缺失' }} · 获取 {{ stock.metadata?.fetched_at }} · {{ stock.metadata?.volume_basis }}</p>
      </details>
    </section>
  </main>
</template>

<script setup>
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route = useRoute(), router = useRouter()
const symbolsText = ref(localStorage.getItem('strategy6-us-research-symbols') || '')
const count = ref(1100), asOf = ref(''), localOnly = ref(false), force = ref(false)
const tasks = ref([]), selectedId = ref(String(route.query.task || '')), task = ref(null)
const starting = ref(false), error = ref(''), copied = ref(''), onlyPassed = ref(false)
const running = computed(() => task.value?.status === 'RUNNING')
const failedCount = computed(() => (task.value?.stocks || []).filter(stock => stock.status === 'FAILED').length)
const passed = stock => ['READY_CANDIDATE', 'KEY_CANDIDATE', 'WATCH_CANDIDATE'].includes(stock.candidate?.candidate_type)
const visibleStocks = computed(() => (task.value?.stocks || []).filter(stock => !onlyPassed.value || passed(stock)))
let timer = null, generation = 0, stopped = false

async function request(url, options) {
  const response = await fetch(url, options)
  const data = await response.json()
  if (!response.ok) throw new Error(data.message || data.error || `HTTP ${response.status}`)
  return data
}
async function loadTasks() {
  try {
    const data = await request('/api/us/strategy6/tasks')
    if (stopped) return
    tasks.value = data.tasks || []
    if (!selectedId.value && tasks.value.length) selectedId.value = tasks.value[0].task_id
  } catch (e) { if (!stopped) error.value = e.message }
}
async function loadTask(id, token) {
  try {
    const data = await request(`/api/us/strategy6/tasks/${encodeURIComponent(id)}`)
    if (stopped || token !== generation || id !== selectedId.value) return
    task.value = data.task
    error.value = ''
    if (task.value?.status === 'RUNNING') timer = setTimeout(() => loadTask(id, token), 2000)
  } catch (e) {
    if (!stopped && token === generation) {
      error.value = `任务刷新失败：${e.message}`
      if (task.value?.status === 'RUNNING') timer = setTimeout(() => loadTask(id, token), 4000)
    }
  }
}
async function refresh() {
  clearTimeout(timer)
  await loadTasks()
  if (selectedId.value) await loadTask(selectedId.value, ++generation)
}
watch(selectedId, id => {
  clearTimeout(timer)
  task.value = null
  error.value = ''
  const token = ++generation
  router.replace({ query: { ...route.query, task: id || undefined } })
  if (id) loadTask(id, token)
})
watch(() => route.query.task, id => { if (String(id || '') !== selectedId.value) selectedId.value = String(id || '') })
async function start(retryOf) {
  if (starting.value) return
  starting.value = true
  error.value = ''
  localStorage.setItem('strategy6-us-research-symbols', symbolsText.value)
  try {
    const symbols = [...new Set(symbolsText.value.split(/[\s,，;；]+/).filter(Boolean))]
    const data = await request('/api/us/strategy6/research', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols, count: count.value, as_of: asOf.value || null,
        local_only: localOnly.value, force: force.value, retry_of: retryOf || null }),
    })
    if (stopped) return
    selectedId.value = data.task_id
    await loadTasks()
  } catch (e) { if (!stopped) error.value = e.message }
  finally { starting.value = false }
}
async function copy(symbol) {
  try { await navigator.clipboard.writeText(symbol.replace(/\.US$/, '')); copied.value = symbol }
  catch { error.value = '复制失败，请检查浏览器剪贴板权限' }
}
const format = value => typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : '—'
const statusLabel = status => ({ RUNNING: '运行中', COMPLETED: '完成', COMPLETED_WITH_ERRORS: '完成（有失败）', FAILED: '失败', INTERRUPTED: '已中断' }[status] || status)
const tierLabel = stock => stock.status === 'FAILED' ? '数据失败' : ({ READY_CANDIDATE: '研究就绪', KEY_CANDIDATE: '研究重点', WATCH_CANDIDATE: '研究观察', REJECTED: '未通过' }[stock.candidate?.candidate_type] || '—')
onMounted(() => { loadTasks(); if (selectedId.value) loadTask(selectedId.value, generation) })
onUnmounted(() => { stopped = true; generation++; clearTimeout(timer) })
</script>

<style scoped>
.us-research { max-width: 1500px; margin: 28px auto; padding: 0 24px; color: var(--text-primary, #ddd); }
small { color: var(--gold, #d6a84a); letter-spacing: .1em; }
h1 { margin: 8px 0; font-size: 24px; }
p { line-height: 1.7; font-size: 13px; }
section, aside { border: 1px solid var(--border, #283444); background: var(--bg-panel, #0d1520); padding: 18px; margin-top: 18px; }
.warning { border-left: 3px solid #d6a84a; color: #e8c77f; }
.inputs, .controls, .task-bar, .summary { display: flex; gap: 18px; flex-wrap: wrap; align-items: center; }
.inputs > label { flex: 1; min-width: 240px; }
label { font-size: 12px; display: flex; gap: 8px; align-items: center; }
.inputs > label, .controls > label:has(input[type=number]), .controls > label:has(input[type=date]) { flex-direction: column; align-items: stretch; }
.controls { flex: 2; }
textarea, input, select, button { color: inherit; background: #111d2b; border: 1px solid #304258; padding: 8px; border-radius: 2px; }
textarea { width: 100%; box-sizing: border-box; font-family: monospace; }
button { cursor: pointer; color: #e7c572; }
button:disabled { opacity: .4; cursor: default; }
.error { color: #f37676; }
.table-scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th, td { padding: 12px 9px; text-align: left; border-bottom: 1px solid #273443; }
th { white-space: nowrap; color: #91a7c2; }
.reason { max-width: 480px; overflow-wrap: anywhere; }
.code { border: 0; padding: 0; background: none; font-family: monospace; }
</style>
