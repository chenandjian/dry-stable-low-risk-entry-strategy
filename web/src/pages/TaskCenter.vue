<template>
  <div class="page-content">
    <h2 class="page-title">扫描任务</h2>
    <p class="page-sub">历史扫描记录</p>

    <div class="panel">
      <div class="task-header">
        <span style="width:20px"></span>
        <span>任务ID</span>
        <span>扫描日期</span>
        <span>状态</span>
        <span>耗时</span>
        <span>候选</span>
        <span>失败</span>
        <span>来源</span>
        <span>最新日</span>
        <span>操作</span>
      </div>
      <div v-if="tasks.length === 0" class="empty-state">
        暂无扫描记录
      </div>
      <div v-for="t in tasks" :key="t.id" class="task-row" :class="{ 're-evaluating': isReEvaluating(t) }">
        <span class="task-dot" :class="dotClass(t)"></span>
        <span class="task-id">{{ t.id }}</span>
        <span class="task-date">{{ t.date }}</span>
        <span :class="statusClass(t)">{{ statusLabel(t) }}</span>
        <span class="muted">{{ t.duration || '--' }}</span>
        <span class="blue">{{ t.candidates || 0 }}<span v-if="candidateDelta(t)" class="delta">{{ candidateDelta(t) }}</span></span>
        <span class="red">{{ t.failed || 0 }}</span>
        <span class="muted">{{ t.stock_pool_source || '--' }}</span>
        <span class="muted">{{ t.latest_trade_date || '--' }}</span>
        <span class="actions">
          <button class="action-btn" @click="viewResults(t.id)" v-if="!isReEvaluating(t) && !t.running">查看结果</button>
          <button class="action-btn primary" @click="handleReEvaluate(t.id)" :disabled="isReEvaluating(t)" v-if="!t.running">
            {{ isReEvaluating(t) ? '重新评估中...' : '重新扫描策略' }}
          </button>
          <button class="action-btn" @click="viewFailures(t.id)" v-if="!isReEvaluating(t) && !t.running && t.failed">失败列表</button>
          <button class="action-btn" @click="exportResults(t.id)" v-if="!isReEvaluating(t) && !t.running">导出</button>
          <span v-if="t.running" class="st-running">实时查看 →</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'

const router = useRouter()
const { getScanTasks, reEvaluateTask } = useApi()
const tasks = ref([])
const reEvaluating = ref(new Set())
const preCounts = ref({})   // taskId → previous candidate count
let pollTimer = null

function isReEvaluating(t) { return reEvaluating.value.has(t.id) || t.status === 're_evaluating' }
function dotClass(t) {
  if (t.running || isReEvaluating(t)) return 'running'
  return 'done'
}
function statusClass(t) {
  if (t.running) return 'st-running'
  if (isReEvaluating(t)) return 'st-running'
  return 'st-done'
}
function statusLabel(t) {
  if (t.running) return '扫描中'
  if (isReEvaluating(t)) return '重新评估中...'
  if (t.status === 'failed') return '失败'
  if (t.status === 'cancelled') return '已停止'
  return '已完成'
}
function candidateDelta(t) {
  const prev = preCounts.value[t.id]
  if (prev != null && t.candidates !== prev && !isReEvaluating(t)) {
    const d = t.candidates - prev
    return d > 0 ? ` +${d}` : ` ${d}`
  }
  return ''
}
function viewResults(id) { router.push(`/results?task_id=${id}`) }
function viewFailures(id) { router.push(`/?task=${id}&status=failed`) }
function exportResults(id) { window.open('/api/candidates', '_blank') }
async function handleReEvaluate(taskId) {
  preCounts.value[taskId] = tasks.value.find(t => t.id === taskId)?.candidates || 0
  reEvaluating.value.add(taskId)
  const res = await reEvaluateTask(taskId)
  if (res.ok) {
    // Poll until status returns to 'completed'
    let tries = 0
    while (tries < 60) {
      await new Promise(r => setTimeout(r, 1000))
      await loadTasks()
      const task = tasks.value.find(t => t.id === taskId)
      if (task && task.status !== 're_evaluating') {
        // Done — keep delta visible briefly
        setTimeout(() => { delete preCounts.value[taskId] }, 5000)
        break
      }
      tries++
    }
  }
  reEvaluating.value.delete(taskId)
  await loadTasks()
}

async function loadTasks() {
  try {
    const data = await getScanTasks()
    tasks.value = (data.tasks || [])
    // Sync re-evaluating state from server status
    for (const t of tasks.value) {
      if (t.status === 're_evaluating') reEvaluating.value.add(t.id)
    }
  } catch (e) {
    console.error('Failed to load tasks:', e)
  }
}

onMounted(() => {
  loadTasks()
  pollTimer = setInterval(loadTasks, 2000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 1200px; margin: 0 auto; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.page-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 20px; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.task-header {
  display: grid; grid-template-columns: 20px 140px 150px 80px 70px 60px 60px 80px 90px 180px;
  align-items: center; padding: 10px 16px; border-bottom: 2px solid var(--border-light);
  font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;
}
.task-row {
  display: grid; grid-template-columns: 20px 140px 150px 80px 70px 60px 60px 80px 90px 180px;
  align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px;
}
.task-row:hover { background: rgba(79,125,255,0.03); }
.task-id { font-family: var(--font-mono); font-size: 12px; color: var(--accent); }
.task-dot { width: 8px; height: 8px; border-radius: 50%; }
.task-dot.running { background: var(--warn-orange); box-shadow: 0 0 6px rgba(249,115,22,0.3); }
.task-dot.done { background: var(--down-green); }
.st-running { color: var(--warn-orange); }
.st-done { color: var(--down-green); }
.muted { color: var(--text-muted); }
.blue { color: var(--accent); }
.gold { color: var(--gold); font-weight: 600; }
.red { color: var(--up-red); font-weight: 600; }
.actions { display: flex; gap: 6px; }
.action-btn {
  font-size: 11px; padding: 4px 10px; border-radius: 3px;
  border: 1px solid var(--border); background: transparent; color: var(--text-secondary); cursor: pointer;
}
.action-btn:hover { border-color: var(--accent); color: var(--accent); }
.action-btn.primary { border-color: var(--accent); color: var(--accent); }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.delta { font-size: 10px; margin-left: 2px; color: var(--down-green); }
.task-row.re-evaluating { background: rgba(249,115,22,0.04); }
.empty-state { padding: 40px; text-align: center; color: var(--text-muted); }
</style>
