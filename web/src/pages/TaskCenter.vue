<template>
  <div class="page-content">
    <h2 class="page-title">策略6扫描任务</h2>
    <p class="page-sub">仅展示策略6的手动与定时扫描记录</p>

    <div class="panel scheduler-panel">
      <div class="panel-header scheduler-header">
        <span>定时任务日志</span>
        <span class="scheduler-status" :class="{ enabled: schedulerConfig.enabled }">
          {{ schedulerConfig.enabled ? '配置已启用' : '配置未启用' }}
        </span>
      </div>
      <div class="scheduler-meta">
        <span :class="schedulerRuntime.running ? 'runtime-running' : 'runtime-stopped'">
          实际{{ schedulerRuntime.running ? '运行中' : '未运行' }}
        </span>
        <span>策略6定时扫描：{{ schedulerConfig.enabled ? '开启' : '关闭' }}</span>
        <span>Cron {{ strategy6Schedule.cron || schedulerConfig.cron || '--' }}</span>
        <span>下次 {{ nextSchedulerRun || '--' }}</span>
      </div>
      <div v-if="schedulerEvents.length === 0" class="scheduler-empty">暂无定时任务日志</div>
      <div v-else class="scheduler-log-lines">
        <div v-for="event in schedulerEvents" :key="event.time + event.stage + event.message" class="scheduler-log-line">
          <span class="log-time">{{ event.time }}</span>
          <span class="log-level" :class="event.level">{{ event.level }}</span>
          <span class="log-stage">{{ event.stage }}</span>
          <span class="log-task">{{ event.task_id || '--' }}</span>
          <span class="log-message">{{ event.message }}</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="task-header">
        <span></span><span>任务ID</span><span>扫描日期</span><span>状态</span>
        <span>耗时</span><span>候选</span><span>失败</span><span>来源</span><span>最新日</span><span>操作</span>
      </div>
      <div v-if="tasks.length === 0" class="empty-state">暂无策略6扫描记录</div>
      <div v-for="task in tasks" :key="task.id" class="task-row">
        <span class="task-dot" :class="task.running ? 'running' : 'done'"></span>
        <span class="task-id">{{ task.id }}</span>
        <span>{{ task.date || task.started_at || '--' }}</span>
        <span :class="task.running ? 'st-running' : statusClass(task)">{{ statusLabel(task) }}</span>
        <span class="muted">{{ task.duration || '--' }}</span>
        <span class="blue">{{ task.candidates || task.candidates_count || 0 }}</span>
        <span class="red">{{ task.failed || 0 }}</span>
        <span class="muted">{{ task.stock_pool_source || '--' }}</span>
        <span class="muted">{{ task.latest_trade_date || '--' }}</span>
        <span class="actions">
          <button v-if="!task.running" class="action-btn" @click="viewResults(task.id)">查看结果</button>
          <span v-else class="st-running">扫描中</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'

const router = useRouter()
const { getStrategy6Tasks, getSchedulerLogs } = useApi()
const tasks = ref([])
const schedulerConfig = ref({ enabled: false, serial_dual_scan: {} })
const schedulerRuntime = ref({ running: false, jobs: [] })
const schedulerEvents = ref([])
let pollTimer = null

const strategy6Schedule = computed(() => schedulerConfig.value.serial_dual_scan || {})
const nextSchedulerRun = computed(() => {
  const jobs = schedulerRuntime.value.jobs || []
  return (jobs.find(job => job.id === 'strategy6_scan') || jobs[0])?.next_run_time || ''
})

function statusLabel(task) {
  if (task.running || task.status === 'running') return '扫描中'
  if (task.status === 'failed') return '失败'
  if (task.status === 'cancelled') return '已停止'
  return '已完成'
}

function statusClass(task) {
  return task.status === 'failed' ? 'st-failed' : 'st-done'
}

function viewResults(taskId) {
  router.push(`/strategy6/results?task=${taskId}`)
}

async function loadTasks() {
  try {
    const data = await getStrategy6Tasks()
    tasks.value = [...(data.tasks || [])].sort((left, right) => {
      if (left.running && !right.running) return -1
      if (!left.running && right.running) return 1
      return String(right.date || right.started_at || '').localeCompare(String(left.date || left.started_at || ''))
    })
  } catch (error) {
    console.error('Failed to load Strategy6 tasks:', error)
  }
}

async function loadSchedulerLogs() {
  try {
    const data = await getSchedulerLogs(100)
    schedulerConfig.value = data.scheduler || { enabled: false, serial_dual_scan: {} }
    schedulerRuntime.value = data.runtime || { running: false, jobs: [] }
    schedulerEvents.value = data.events || []
  } catch (error) {
    console.error('Failed to load Strategy6 scheduler logs:', error)
  }
}

onMounted(() => {
  loadTasks()
  loadSchedulerLogs()
  pollTimer = setInterval(() => {
    loadTasks()
    loadSchedulerLogs()
  }, 2000)
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 1200px; margin: 0 auto; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.page-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 20px; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.scheduler-panel { margin-bottom: 16px; }
.panel-header { display: flex; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.scheduler-status { font-size: 11px; color: var(--text-muted); }
.scheduler-status.enabled, .runtime-running, .st-done { color: var(--down-green); }
.runtime-stopped, .st-failed, .red { color: var(--up-red); }
.scheduler-meta { display: flex; gap: 16px; padding: 10px 16px; border-bottom: 1px solid var(--border); font-size: 12px; color: var(--text-muted); }
.scheduler-empty, .empty-state { padding: 32px 16px; text-align: center; color: var(--text-muted); }
.scheduler-log-lines { max-height: 180px; overflow-y: auto; padding: 6px 0; }
.scheduler-log-line { display: grid; grid-template-columns: 150px 60px 150px 180px 1fr; gap: 8px; padding: 4px 16px; font-family: var(--font-mono); font-size: 11px; }
.log-level.info { color: var(--accent); }
.log-level.warning { color: var(--warn-orange); }
.log-level.error { color: var(--up-red); }
.log-stage { color: var(--gold); }
.task-header, .task-row { display: grid; grid-template-columns: 20px 160px 150px 70px 70px 60px 60px 90px 90px 100px; align-items: center; padding: 11px 16px; gap: 4px; }
.task-header { border-bottom: 2px solid var(--border-light); font-size: 11px; color: var(--text-muted); }
.task-row { border-bottom: 1px solid var(--border); font-size: 12px; }
.task-dot { width: 8px; height: 8px; border-radius: 50%; }
.task-dot.running { background: var(--warn-orange); }
.task-dot.done { background: var(--down-green); }
.task-id { color: var(--accent); font-family: var(--font-mono); }
.st-running { color: var(--warn-orange); }
.muted { color: var(--text-muted); }
.blue { color: var(--accent); }
.actions { display: flex; gap: 6px; }
.action-btn { font-size: 11px; padding: 4px 10px; border: 1px solid var(--border); background: transparent; color: var(--text-secondary); cursor: pointer; border-radius: 3px; }
.action-btn:hover { border-color: var(--accent); color: var(--accent); }
</style>
