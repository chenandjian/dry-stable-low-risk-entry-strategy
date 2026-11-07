<template>
  <main class="observation-page">
    <header>
      <h1>美股候选与 VCP 持续观察</h1>
      <p>只读已完成的美股研究任务。未启用指数过滤，结果不是正式候选或交易信号。</p>
      <a href="/us/strategy6/research">返回美股研究</a>
    </header>
    <section class="panel">
      <nav class="controls" aria-label="美股观察视图">
        <button :aria-pressed="view === 'candidates'" @click="selectView('candidates')">研究候选</button>
        <button data-test="us-pool-vcp" :aria-pressed="view === 'vcp'" @click="selectView('vcp')">VCP 持续观察</button>
      </nav>
      <form class="controls" @submit.prevent="submit">
        <label>评估日 <input v-model="asOf" type="date"></label>
        <label>股票代码 <input v-model.trim="symbol" placeholder="AAPL / BRK.B"></label>
        <button :disabled="loading">查询</button>
      </form>
      <p>评估日留空时使用最近已有评估证据的日期，不表示数据覆盖当前交易日。</p>
      <p v-if="error" role="alert" class="error">{{ error }}</p>
      <p v-if="loading" role="status">读取本地观察记录…</p>
      <template v-if="result">
        <p>查看日期 {{ result.as_of || '—' }} · 库内最近评估日 {{ result.latest_evaluation_date || '—' }}</p>
        <p v-if="!result.latest_evaluation_date">暂无观察证据。请先完成一轮新版美股研究扫描；旧任务不会自动补入。</p>
        <p v-else-if="!result.rows.length">所选日期或代码暂无{{ view === 'vcp' ? '已确认 VCP 观察记录' : '研究候选' }}。</p>
        <div v-else class="table-scroll">
          <table>
            <thead><tr>
              <th>股票</th><th>状态</th><th>首次入池</th><th>最近确认</th><th>确认交易日数</th>
              <th v-if="view === 'vcp'">突破 / 退出</th><th>分数</th><th>证据</th>
            </tr></thead>
            <tbody><tr v-for="item in result.rows" :key="item.symbol">
              <td>{{ item.symbol }}</td>
              <td>{{ labels[item.status] || item.status }}
                <small v-if="view === 'vcp' && !item.updated_on_date">评估日未更新 · 上次评估 {{ item.last_evaluation_date }}</small>
              </td>
              <td>{{ item.first_seen_date || '—' }}</td>
              <td>{{ item.last_seen_date || '—' }}</td>
              <td>{{ item.confirmed_days ?? '—' }}</td>
              <td v-if="view === 'vcp'">
                {{ item.breakout_date ? '突破 ' + item.breakout_date : '未记录突破' }}
                <small v-if="item.exit_date">退出 {{ item.exit_date }} · {{ item.exit_reason }}</small>
              </td>
              <td>{{ view === 'vcp' ? (item.vcp_quality_score ?? '—') : (item.total_score ?? '—') }}</td>
              <td><details>
                <summary>查看证据</summary>
                <a v-if="item.task_id" :href="taskLink(item.task_id)">来源研究任务</a>
                <a v-if="item.exit_task_id" :href="taskLink(item.exit_task_id)">退出证据任务</a>
                <template v-if="view === 'vcp'">
                  <p>启动 {{ item.vcp_origin_start_date || '—' }} · 历史候选日 {{ item.vcp_history_candidate_date || '—' }}</p>
                  <p>收缩 {{ item.vcp_contraction_count ?? '—' }} 轮 · 枢轴 {{ item.vcp_pivot_price ?? '—' }} USD · 结构低点 {{ item.vcp_structure_low ?? '—' }} USD</p>
                  <p v-for="(round, index) in item.vcp_contractions || []" :key="index">
                    第 {{ index + 1 }} 轮：{{ round.peak_date }} → {{ round.low_date }} → {{ round.recovery_peak_date }}
                  </p>
                </template>
                <p v-else>候选类型 {{ types[item.candidate_type] || item.candidate_type }} · 尾部分 {{ item.tail_score ?? '—' }}</p>
              </details></td>
            </tr></tbody>
          </table>
        </div>
        <div class="controls">
          <span>共 {{ result.total }} 条 · 第 {{ result.page }} / {{ pages }} 页</span>
          <button :disabled="loading || result.page <= 1" @click="load(result.page - 1)">上一页</button>
          <button :disabled="loading || result.page >= pages" @click="load(result.page + 1)">下一页</button>
        </div>
      </template>
    </section>
  </main>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const view = ref('candidates')
const asOf = ref('')
const symbol = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref('')
const pages = computed(() => Math.max(1, Math.ceil((result.value?.total || 0) / 50)))
const labels = {
  NEW: '新入池', CONTINUING: '持续观察', VCP_ROUND1_CONFIRMED: '首轮确认',
  VCP_CONFIRMED: '形态确认', VCP_NEAR_PIVOT: '接近枢轴', VCP_BREAKOUT_CONFIRMED: '突破确认',
  VCP_POST_BREAKOUT: '突破后观察', VCP_EXTENDED: '已远离枢轴', VCP_INVALID: '已失效',
  VCP_EXPIRED: '观察到期', VCP_NOT_RECONFIRMED: '未重新确认',
}
const types = { READY_CANDIDATE: '研究就绪', KEY_CANDIDATE: '研究重点', WATCH_CANDIDATE: '研究观察' }
const taskLink = id => `/us/strategy6/research?task=${encodeURIComponent(id)}`
let generation = 0
let submitted = {}

async function load(page = 1) {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const query = new URLSearchParams({ ...submitted, view: view.value, page, page_size: 50 })
    const response = await fetch(`/api/us/strategy6/observations?${query}`)
    const data = await response.json()
    if (!response.ok) throw new Error(data.message || '查询失败')
    if (token === generation) result.value = data
  } catch (err) {
    if (token === generation) error.value = err.message
  } finally {
    if (token === generation) loading.value = false
  }
}

function submit() {
  submitted = { ...(asOf.value ? { as_of: asOf.value } : {}), ...(symbol.value ? { symbol: symbol.value } : {}) }
  result.value = null
  load()
}

function selectView(next) {
  if (next === view.value) return
  view.value = next
  result.value = null
  load()
}

onMounted(() => load())
onUnmounted(() => { generation++ })
</script>

<style scoped>
.observation-page { max-width: 1500px; margin: 28px auto; padding: 0 24px; color: var(--text-primary); }
.panel { background: var(--bg-panel); border: 1px solid var(--border); margin-top: 16px; padding: 18px; }
.controls { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; }
button, input { color: inherit; background: #111d2b; border: 1px solid var(--border); padding: 7px 10px; }
button[aria-pressed="true"], a { color: var(--gold); }
button:disabled { opacity: .45; }
.error { color: #f37676; }
.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; text-align: left; }
th, td { border-bottom: 1px solid var(--border); padding: 10px; vertical-align: top; }
th { white-space: nowrap; }
small, details a { display: block; margin-top: 4px; }
summary { cursor: pointer; white-space: nowrap; }
</style>
