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

    <div class="tabbar">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        {{ tab.label }}
      </button>
    </div>

    <section v-if="activeTab === 'topics'" class="panel">
      <div class="panel-header">热点题材榜</div>
      <div v-if="topics.length === 0" class="empty">暂无热点题材快照</div>
      <table v-else>
        <thead><tr><th>题材</th><th>状态</th><th>热度</th><th>来源确认</th><th>成员口径</th><th>板块K线</th><th>阶段</th><th>信号数</th><th>领涨股</th></tr></thead>
        <tbody>
          <tr v-for="t in topics" :key="t.topic_id">
            <td>{{ t.topic_name }}</td>
            <td>{{ t.status }}</td>
            <td>{{ fmt(t.hot_topic_score) }}</td>
            <td>
              <span :class="sourceClass(t)">{{ sourceLabel(t) }}</span>
              <small v-if="warningLabel(t)"> · {{ warningLabel(t) }}</small>
            </td>
            <td><span :class="membershipClass(t)">{{ membershipLabel(t) }}</span></td>
            <td>
              <span :class="topicIndexClass(t)">{{ topicIndexLabel(t) }}</span>
              <small v-if="t.topic_index_latest_date"> · {{ t.topic_index_latest_date }}</small>
            </td>
            <td>{{ t.topic_index_phase || '--' }}</td>
            <td>{{ t.signal_count || 0 }}</td>
            <td>{{ t.leading_stock_code || '--' }} {{ t.leading_stock_name || '' }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-if="activeTab === 'leaders'" class="panel">
      <div class="panel-header">龙头股票榜</div>
      <div v-if="leaders.length === 0" class="empty">暂无龙头快照</div>
      <table v-else>
        <thead><tr><th>股票</th><th>题材</th><th>来源</th><th>成员口径</th><th>类型</th><th>龙头强度</th><th>可交易性</th><th>涨停制度</th><th>形态</th><th>状态</th></tr></thead>
        <tbody>
          <tr v-for="l in leaders" :key="`${l.topic_id}-${l.code}`">
            <td>{{ l.code }} {{ l.name }}</td>
            <td>{{ l.topic_name }}</td>
            <td><span :class="sourceClass(l)">{{ sourceLabel(l) }}</span></td>
            <td><span :class="membershipClass(l)">{{ membershipLabel(l) }}</span></td>
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

    <section v-if="activeTab === 'candidates'" class="panel">
      <div class="panel-header">二波候选榜</div>
      <div v-if="buyableCandidates.length === 0" class="empty">暂无可交易二波候选，但热点和龙头仍可继续观察</div>
      <table v-else>
        <thead><tr><th>股票</th><th>题材</th><th>来源</th><th>跟踪状态</th><th>总分</th><th>第一波</th><th>回踩</th><th>风险</th><th>RR</th><th>说明</th></tr></thead>
        <tbody>
          <tr v-for="c in buyableCandidates" :key="`${c.topic_id}-${c.code}`" class="clickable" @click="openCandidate(c)">
            <td>{{ c.code }} {{ c.name }}</td>
            <td>{{ c.topic_name }}</td>
            <td><span :class="sourceClass(c)">{{ sourceLabel(c) }}</span></td>
            <td>{{ trackingCandidateLabel(c) }}</td>
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
        <div><span>来源确认</span><strong>{{ sourceLabel(selectedCandidate) }}</strong></div>
        <div><span>跟踪状态</span><strong>{{ trackingCandidateLabel(selectedCandidate) }}</strong></div>
        <div><span>首次热点 / 最近确认</span><strong>{{ selectedCandidate.topic_first_detected_date || '--' }} / {{ selectedCandidate.topic_last_confirmed_date || '--' }}</strong></div>
        <div><span>跟踪天数 / 阶段</span><strong>{{ selectedCandidate.tracking_age_days || 0 }} / {{ trackingPhaseLabel(selectedCandidate.tracking_phase) }}</strong></div>
        <div><span>成员口径</span><strong>{{ membershipLabel(selectedCandidate) }}</strong></div>
        <div><span>融合提示</span><strong>{{ warningLabel(selectedCandidate) || '--' }}</strong></div>
        <div><span>板块阶段</span><strong>{{ selectedCandidate.evaluation_snapshot?.topic_index_phase || '--' }}</strong></div>
        <div><span>板块最新K线</span><strong>{{ selectedCandidate.evaluation_snapshot?.topic_index_latest_date || '--' }}</strong></div>
        <div><span>说明</span><strong>{{ selectedCandidate.entry_note || '--' }}</strong></div>
      </div>
    </section>

    <section v-if="activeTab === 'locked'" class="panel">
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

    <section v-if="activeTab === 'tracking'" class="panel">
      <div class="panel-header">跟踪池</div>
      <div v-if="trackedTopics.length === 0 && trackedLeaders.length === 0" class="empty">暂无跟踪池记录</div>
      <div v-else class="tracking-grid">
        <div>
          <h3>题材生命周期</h3>
          <table>
            <thead><tr><th>题材</th><th>状态</th><th>阶段</th><th>跟踪天数</th><th>最近确认</th><th>板块阶段</th></tr></thead>
            <tbody>
              <tr v-for="t in trackedTopics" :key="t.topic_id">
                <td>{{ t.topic_name }}</td>
                <td>{{ t.tracking_status }}</td>
                <td>{{ trackingPhaseLabel(t.tracking_phase) }}</td>
                <td>{{ t.age_calendar_days || 0 }}</td>
                <td>{{ t.last_confirmed_date || '--' }}</td>
                <td>{{ t.topic_index_phase || '--' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h3>龙头生命周期</h3>
          <table>
            <thead><tr><th>股票</th><th>题材</th><th>状态</th><th>阶段</th><th>RR</th><th>风险</th></tr></thead>
            <tbody>
              <tr v-for="l in trackedLeaders" :key="`${l.topic_id}-${l.code}`">
                <td>{{ l.code }} {{ l.name }}</td>
                <td>{{ l.topic_name }}</td>
                <td>{{ l.tracking_status }}</td>
                <td>{{ trackingPhaseLabel(l.tracking_phase) }}</td>
                <td>{{ fmt(l.reward_risk_ratio) }}</td>
                <td>{{ pct(l.risk_ratio) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
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
  getStrategy4TrackedTopics,
  getStrategy4TrackedLeaders,
  getStrategy4TrackingEvents,
} = useApi()

const tabs = [
  { key: 'candidates', label: '二波候选' },
  { key: 'topics', label: '热点题材' },
  { key: 'leaders', label: '龙头股票' },
  { key: 'tracking', label: '跟踪池' },
  { key: 'locked', label: '锁仓观察' },
]
const activeTab = ref('candidates')
const tasks = ref([])
const selectedTaskId = ref('')
const topics = ref([])
const leaders = ref([])
const candidates = ref([])
const trackedTopics = ref([])
const trackedLeaders = ref([])
const trackingEvents = ref([])
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
function topicIndexLabel(topic) {
  if (topic.topic_index_observed) return '已观察'
  if (topic.topic_index_status === 'source_failed') return '拉取失败'
  if (topic.topic_index_status) return '不可观察'
  return '未观察'
}
function topicIndexClass(topic) {
  return topic.topic_index_observed ? 'topic-index-ok' : 'topic-index-warn'
}
function sourceModes(item) {
  const modes = item?.source_modes || item?.evaluation_snapshot?.source_modes || []
  return Array.isArray(modes) ? modes : []
}
function sourceLabel(item) {
  if (item?.candidate_origin === 'tracking_pool') return '跟踪池二波'
  if (item?.candidate_origin === 'merged_current_and_tracking') return '当前热点 + 跟踪池'
  if (item?.candidate_origin === 'current_hot') return '当前热点'
  const modes = sourceModes(item)
  if (modes.includes('live_external') && modes.includes('historical_kline_derived')) return '双源确认'
  if (modes.includes('historical_kline_derived')) return 'K线反推'
  if (modes.includes('live_external')) return '外部热点'
  if (item?.snapshot_source === 'historical_kline_derived') return 'K线反推'
  if (item?.snapshot_source === 'merged') return '双源确认'
  return item?.source || '--'
}
function sourceClass(item) {
  if (item?.candidate_origin === 'tracking_pool') return 'source-tracking'
  if (item?.candidate_origin === 'merged_current_and_tracking') return 'source-merged'
  const label = sourceLabel(item)
  if (label === '双源确认') return 'source-merged'
  if (label === 'K线反推') return 'source-derived'
  return 'source-live'
}
function membershipLabel(item) {
  const mode = item?.membership_mode || item?.evaluation_snapshot?.membership_mode || ''
  if (mode === 'current_members_proxy') return '成员代理'
  if (mode === 'historical_members_snapshot') return '历史成员'
  if (mode === 'unobserved_members') return '成员不可观察'
  return '--'
}
function membershipClass(item) {
  const mode = item?.membership_mode || item?.evaluation_snapshot?.membership_mode || ''
  if (mode === 'current_members_proxy') return 'membership-warn'
  if (mode === 'historical_members_snapshot') return 'membership-ok'
  return 'membership-muted'
}
function warningLabel(item) {
  const warnings = item?.merge_warnings || item?.evaluation_snapshot?.merge_warnings || []
  if (!Array.isArray(warnings) || warnings.length === 0) return ''
  if (warnings.includes('derived_weak_noise')) return 'K线反推偏弱'
  if (warnings.includes('derived_high_risk_climax')) return '板块高潮风险'
  if (warnings.includes('current_members_proxy')) return '成员代理'
  return warnings.join('、')
}
function trackingPhaseLabel(phase) {
  if (phase === 'strong_attention') return '强关注期'
  if (phase === 'golden_second_wave') return '黄金二波期'
  if (phase === 'extension') return '延长期'
  if (phase === 'expired') return '已过期'
  return phase || '--'
}
function trackingCandidateLabel(item) {
  if (!item?.candidate_origin || item.candidate_origin === 'current_hot') return '--'
  const parts = [
    item.tracking_topic_status,
    item.tracking_leader_status,
    item.tracking_age_days ? `${item.tracking_age_days}天` : '',
  ].filter(Boolean)
  return parts.join(' / ') || '--'
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
    const [topicRes, leaderRes, candidateRes, trackedTopicRes, trackedLeaderRes, eventRes] = await Promise.all([
      getStrategy4Topics(taskId),
      getStrategy4Leaders(taskId),
      getStrategy4Candidates(taskId),
      getStrategy4TrackedTopics({ include_expired: false, page_size: 200 }),
      getStrategy4TrackedLeaders({ include_expired: false, page_size: 200 }),
      getStrategy4TrackingEvents({ task_id: taskId, page_size: 100 }),
    ])
    if (seq !== loadSeq || taskId !== selectedTaskId.value) return
    if (topicRes.error || leaderRes.error || candidateRes.error) {
      error.value = topicRes.message || leaderRes.message || candidateRes.message || topicRes.error || leaderRes.error || candidateRes.error
    }
    topics.value = topicRes.topics || []
    leaders.value = leaderRes.leaders || []
    candidates.value = candidateRes.candidates || []
    trackedTopics.value = trackedTopicRes.topics || []
    trackedLeaders.value = trackedLeaderRes.leaders || []
    trackingEvents.value = eventRes.events || []
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
.tabbar { display: flex; gap: 8px; flex-wrap: wrap; margin: 0 0 14px; }
.tabbar button { background: rgba(15,23,42,0.7); color: var(--text-secondary); border: 1px solid var(--border); border-radius: 999px; padding: 7px 12px; cursor: pointer; }
.tabbar button.active { color: #fb923c; border-color: rgba(249,115,22,0.65); background: rgba(249,115,22,0.12); }
.empty { padding: 20px; color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
th { color: var(--text-secondary); font-weight: 600; }
small { color: var(--text-muted); }
.topic-index-ok { color: var(--down-green); font-weight: 700; }
.topic-index-warn { color: var(--up-red); font-weight: 700; }
.source-merged { color: var(--accent); font-weight: 700; }
.source-derived { color: #60a5fa; font-weight: 700; }
.source-live { color: var(--text-secondary); font-weight: 700; }
.source-tracking { color: #c084fc; font-weight: 700; }
.membership-ok { color: var(--down-green); font-weight: 700; }
.membership-warn { color: #f59e0b; font-weight: 700; }
.membership-muted { color: var(--text-muted); }
.error-banner { margin-bottom: 12px; padding: 10px 12px; border: 1px solid rgba(239,68,68,0.4); color: var(--up-red); border-radius: 4px; }
.clickable { cursor: pointer; }
.clickable:hover { background: rgba(249, 115, 22, 0.08); }
.detail-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; padding: 16px; font-size: 12px; }
.detail-grid span { display: block; color: var(--text-secondary); margin-bottom: 4px; }
.detail-grid strong { color: var(--text-primary); font-weight: 600; }
.tracking-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; padding: 14px; }
.tracking-grid h3 { margin: 0 0 10px; color: var(--text-secondary); font-size: 13px; }
</style>
