<template>
  <div class="page-content">
    <div class="page-header">
      <div>
        <h1>策略4 · 热点龙头二波</h1>
        <p>先看热点题材，再看核心龙头，最后判断健康回踩后的二波机会。</p>
      </div>
      <select v-model="selectedTaskId" @change="loadTask">
        <option value="">选择历史任务</option>
        <option v-for="task in tasks" :key="task.id" :value="task.id">
          {{ task.id }} · {{ task.status }}
        </option>
      </select>
    </div>

    <div v-if="error" class="error-banner">{{ error }}</div>

    <section class="panel">
      <div class="panel-header">热点题材榜</div>
      <div v-if="topics.length === 0" class="empty">暂无热点题材快照</div>
      <table v-else>
        <thead><tr><th>题材</th><th>状态</th><th>热度</th><th>信号数</th><th>领涨股</th><th>来源</th></tr></thead>
        <tbody>
          <tr v-for="t in topics" :key="t.topic_id">
            <td>{{ t.topic_name }}</td>
            <td>{{ t.status }}</td>
            <td>{{ fmt(t.hot_topic_score) }}</td>
            <td>{{ t.signal_count || 0 }}</td>
            <td>{{ t.leading_stock_code || '--' }} {{ t.leading_stock_name || '' }}</td>
            <td>{{ t.source || '--' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <div class="panel-header">龙头股票榜</div>
      <div v-if="leaders.length === 0" class="empty">暂无龙头快照</div>
      <table v-else>
        <thead><tr><th>股票</th><th>题材</th><th>类型</th><th>龙头强度</th><th>可交易性</th><th>涨停制度</th><th>形态</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="l in leaders" :key="`${l.topic_id}-${l.code}`">
            <td>{{ l.code }} {{ l.name }}</td>
            <td>{{ l.topic_name }}</td>
            <td>{{ l.leader_type }}</td>
            <td>{{ fmt(l.leader_strength_score) }}</td>
            <td>{{ fmt(l.tradability_score) }}</td>
            <td>{{ l.price_limit_rule || '--' }}</td>
            <td>{{ l.limit_shape || '--' }}</td>
            <td>{{ l.status }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <div class="panel-header">二波候选榜</div>
      <div v-if="buyableCandidates.length === 0" class="empty">暂无可交易二波候选，但热点和龙头仍可继续观察</div>
      <table v-else>
        <thead><tr><th>股票</th><th>题材</th><th>总分</th><th>第一波</th><th>回踩</th><th>风险</th><th>RR</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="c in buyableCandidates" :key="`${c.topic_id}-${c.code}`" class="clickable" @click="openCandidate(c)">
            <td>{{ c.code }} {{ c.name }}</td>
            <td>{{ c.topic_name }}</td>
            <td>{{ fmt(c.strategy4_score) }}</td>
            <td>{{ pct(c.first_wave_return) }}</td>
            <td>{{ pct(c.pullback_pct) }} / {{ c.pullback_days || 0 }}天</td>
            <td>{{ pct(c.risk_ratio) }}</td>
            <td>{{ fmt(c.reward_risk_ratio) }}</td>
            <td>{{ c.entry_note || '--' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="selectedCandidate" class="panel">
      <div class="panel-header">候选详情</div>
      <div class="detail-grid">
        <div><span>股票</span><strong>{{ selectedCandidate.code }} {{ selectedCandidate.name }}</strong></div>
        <div><span>题材</span><strong>{{ selectedCandidate.topic_name || '--' }}</strong></div>
        <div><span>状态</span><strong>{{ selectedCandidate.status || '--' }}</strong></div>
        <div><span>支撑 / 止损 / 目标</span><strong>{{ fmt(selectedCandidate.support_price) }} / {{ fmt(selectedCandidate.stop_loss) }} / {{ fmt(selectedCandidate.target_price) }}</strong></div>
        <div><span>风险比</span><strong>{{ pct(selectedCandidate.risk_ratio) }}</strong></div>
        <div><span>收益风险比</span><strong>{{ fmt(selectedCandidate.reward_risk_ratio) }}</strong></div>
        <div><span>涨停制度 / 形态</span><strong>{{ selectedCandidate.price_limit_rule || '--' }} / {{ selectedCandidate.limit_shape || '--' }}</strong></div>
        <div><span>说明</span><strong>{{ selectedCandidate.entry_note || '--' }}</strong></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-header">锁仓观察榜</div>
      <div v-if="lockedLeaders.length === 0" class="empty">暂无锁仓观察龙头</div>
      <table v-else>
        <thead><tr><th>股票</th><th>题材</th><th>强度</th><th>涨停形态</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="l in lockedLeaders" :key="`${l.topic_id}-${l.code}`">
            <td>{{ l.code }} {{ l.name }}</td>
            <td>{{ l.topic_name }}</td>
            <td>{{ fmt(l.leader_strength_score) }}</td>
            <td>{{ l.limit_shape || '--' }}</td>
            <td>锁仓关注，不因当日成交额偏低直接排除</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'

const route = useRoute()
const router = useRouter()
const {
  getStrategy4Tasks,
  getStrategy4Topics,
  getStrategy4Leaders,
  getStrategy4Candidates,
  getStrategy4Candidate,
} = useApi()

const tasks = ref([])
const selectedTaskId = ref('')
const topics = ref([])
const leaders = ref([])
const candidates = ref([])
const selectedCandidate = ref(null)
const error = ref('')
let loadSeq = 0

const buyableCandidates = computed(() => candidates.value.filter(c => c.status === 'BUYABLE_SECOND_WAVE'))
const lockedLeaders = computed(() => leaders.value.filter(l => l.status === 'LOCKED_LEADER_WATCH'))

function fmt(v) {
  const n = Number(v || 0)
  return Number.isFinite(n) ? n.toFixed(1) : '--'
}
function pct(v) {
  const n = Number(v || 0)
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : '--'
}

async function loadTasks() {
  const res = await getStrategy4Tasks()
  tasks.value = res.tasks || []
  if (!selectedTaskId.value && tasks.value.length) {
    selectedTaskId.value = tasks.value[0].id
  }
}

async function loadTask() {
  const seq = ++loadSeq
  error.value = ''
  selectedCandidate.value = null
  const taskId = selectedTaskId.value
  if (!taskId) return
  try {
    router.replace({ path: '/strategy4/results', query: { task: taskId } })
    const [topicRes, leaderRes, candidateRes] = await Promise.all([
      getStrategy4Topics(taskId),
      getStrategy4Leaders(taskId),
      getStrategy4Candidates(taskId),
    ])
    if (seq !== loadSeq || taskId !== selectedTaskId.value) return
    if (topicRes.error || leaderRes.error || candidateRes.error) {
      error.value = topicRes.message || leaderRes.message || candidateRes.message || topicRes.error || leaderRes.error || candidateRes.error
    }
    topics.value = topicRes.topics || []
    leaders.value = leaderRes.leaders || []
    candidates.value = candidateRes.candidates || []
  } catch (e) {
    error.value = '策略4结果加载失败'
    console.error(e)
  }
}

async function openCandidate(candidate) {
  const seq = loadSeq
  const taskId = selectedTaskId.value
  selectedCandidate.value = candidate
  try {
    const res = await getStrategy4Candidate(taskId, candidate.code)
    if (seq !== loadSeq || taskId !== selectedTaskId.value) return
    selectedCandidate.value = res?.candidate || candidate
  } catch (e) {
    if (seq === loadSeq) {
      selectedCandidate.value = candidate
    }
  }
}

onMounted(async () => {
  selectedTaskId.value = String(route.query.task || '')
  await loadTasks()
  await loadTask()
})

watch(() => route.query.task, async task => {
  const id = String(task || '')
  if (id && id !== selectedTaskId.value) {
    selectedTaskId.value = id
    await loadTask()
  }
})
</script>

<style scoped>
.page-content { padding: 20px; color: var(--text-primary); }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; gap: 16px; }
h1 { margin: 0 0 6px; font-size: 22px; }
p { margin: 0; color: var(--text-secondary); font-size: 13px; }
select { background: var(--bg-panel); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 8px 10px; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 16px; overflow: hidden; }
.panel-header { padding: 12px 16px; border-bottom: 1px solid var(--border); color: var(--accent); font-weight: 700; }
.empty { padding: 20px; color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
th { color: var(--text-secondary); font-weight: 600; }
.error-banner { margin-bottom: 12px; padding: 10px 12px; border: 1px solid rgba(239,68,68,0.4); color: var(--up-red); border-radius: 4px; }
.clickable { cursor: pointer; }
.clickable:hover { background: rgba(249, 115, 22, 0.08); }
.detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; padding: 16px; font-size: 12px; }
.detail-grid span { display: block; color: var(--text-secondary); margin-bottom: 4px; }
.detail-grid strong { color: var(--text-primary); font-weight: 600; }
</style>
