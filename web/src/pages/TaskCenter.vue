<template>
  <div class="page-content">
    <h2 class="page-title">扫描任务</h2>
    <p class="page-sub">历史扫描记录</p>

    <div class="panel">
      <div class="task-header">
        <span style="width:20px"></span>
        <span>扫描日期</span>
        <span>范围</span>
        <span>状态</span>
        <span>耗时</span>
        <span>候选</span>
        <span>最高</span>
        <span>平均</span>
        <span>A级</span>
        <span>突破</span>
        <span>操作</span>
      </div>
      <div v-if="tasks.length === 0" class="empty-state">
        暂无扫描记录
      </div>
      <div v-for="t in tasks" :key="t.id" class="task-row">
        <span class="task-dot" :class="t.running ? 'running' : 'done'"></span>
        <span class="task-date">{{ t.date }}</span>
        <span>{{ t.scope || '全市场' }}</span>
        <span :class="t.running ? 'st-running' : 'st-done'">{{ t.running ? '扫描中' : '已完成' }}</span>
        <span class="muted">{{ t.duration || '--' }}</span>
        <span class="blue">{{ t.candidates || 0 }}</span>
        <span class="gold">{{ t.topScore || '--' }}</span>
        <span class="muted">{{ t.avgScore || '--' }}</span>
        <span class="gold">{{ t.aGrade || 0 }}</span>
        <span class="red">{{ t.breakout || 0 }}</span>
        <span class="actions">
          <button class="action-btn" @click="viewResults(t.id)" v-if="!t.running">查看结果</button>
          <button class="action-btn" @click="exportResults(t.id)" v-if="!t.running">导出</button>
          <span v-if="t.running" class="st-running">实时查看 →</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useApi } from '../composables/useApi.js'

const router = useRouter()
const { getScanTasks } = useApi()
const tasks = ref([])

function viewResults(id) { router.push('/results') }
function exportResults(id) { window.open(`/api/candidates?format=csv`) }

onMounted(async () => {
  const data = await getScanTasks()
  tasks.value = (data.tasks || []).map(t => ({ ...t, running: false }))
  // Add demo tasks if empty
  if (!tasks.value.length) {
    tasks.value = [
      { id: 'task-1', date: '2026-06-03 14:30', scope: '全市场 · 5,128只', running: false, duration: '8m 42s', candidates: 12, topScore: 87, avgScore: 73.5, aGrade: 3, breakout: 2 },
      { id: 'task-2', date: '2026-06-02 09:45', scope: '全市场 · 5,126只', running: false, duration: '9m 15s', candidates: 9, topScore: 84, avgScore: 72.1, aGrade: 2, breakout: 3 },
    ]
  }
})
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 1200px; margin: 0 auto; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.page-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 20px; }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.task-header {
  display: grid; grid-template-columns: 20px 180px 140px 80px 80px 60px 60px 60px 50px 50px 140px;
  align-items: center; padding: 10px 16px; border-bottom: 2px solid var(--border-light);
  font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;
}
.task-row {
  display: grid; grid-template-columns: 20px 180px 140px 80px 80px 60px 60px 60px 50px 50px 140px;
  align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px;
}
.task-row:hover { background: rgba(79,125,255,0.03); }
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
.empty-state { padding: 40px; text-align: center; color: var(--text-muted); }
</style>
