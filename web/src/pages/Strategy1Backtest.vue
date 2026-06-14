<template>
  <div class="strategy1-backtest">
    <section class="panel">
      <div class="panel-head">
        <div>
          <h1>策略1回测实验</h1>
          <p>本地 daily_ohlc 回放，统一调用 CupHandleStrategyEngine。</p>
        </div>
        <span v-if="runningStatus.running" class="badge running">RUNNING</span>
      </div>

      <div class="form-grid">
        <label>开始日期 <input v-model="form.startDate" placeholder="2025-01-01" /></label>
        <label>结束日期 <input v-model="form.endDate" placeholder="2025-03-31" /></label>
        <label>股票代码 <input v-model="codesText" placeholder="600000,000001" /></label>
        <label>基线任务 <input v-model="baselineTaskId" placeholder="s1bt-..." /></label>
      </div>

      <label class="check">
        <input type="checkbox" v-model="experimentEnabled" />
        实验模式，不影响正式扫描
      </label>

      <div v-if="experimentEnabled" class="experiment-box">
        <span class="badge">EXPERIMENTAL</span>
        <label>候选最低分 <input type="number" v-model.number="experimentForm.minimumTotalScore" /></label>
        <label>量干最低分 <input type="number" v-model.number="experimentForm.minVolumeDryScore" /></label>
        <label>价稳最低分 <input type="number" v-model.number="experimentForm.minPriceStableScore" /></label>
        <label>时间退出
          <select v-model.number="experimentForm.timeExitDays">
            <option :value="null">不启用</option>
            <option :value="3">3日</option>
            <option :value="5">5日</option>
            <option :value="10">10日</option>
          </select>
        </label>
      </div>

      <div class="actions">
        <button @click="previewExperiment">预览实验</button>
        <button class="primary" @click="startBacktest">启动回测</button>
      </div>
      <p v-if="message" class="message">{{ message }}</p>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>任务列表</h2>
        <button @click="loadTasks">刷新</button>
      </div>
      <div v-for="task in tasks" :key="task.id" class="task-row" @click="loadTask(task.id)">
        <span>{{ task.id }}</span>
        <span>{{ task.status }}</span>
        <span class="badge">{{ task.credibility_status || '--' }}</span>
      </div>
      <p v-if="!tasks.length" class="empty">暂无任务</p>
    </section>

    <section v-if="currentTask" class="panel">
      <div class="panel-head">
        <div>
          <h2>{{ currentTask.id }}</h2>
          <p>{{ currentTask.status }} · {{ currentTask.credibility_status }}</p>
        </div>
        <span v-if="currentTask.credibility_status === 'EXPERIMENTAL'" class="badge">EXPERIMENTAL</span>
      </div>

      <div class="metrics">
        <span>机会 {{ summary?.total_opportunities ?? '--' }}</span>
        <span>入场 {{ summary?.entered_count ?? '--' }}</span>
        <span>原始信号 {{ summary?.raw_signals_count ?? '--' }}</span>
      </div>

      <div v-if="qualityGroups.length" class="quality-groups">
        <span v-for="group in qualityGroups" :key="group.tag" class="quality-chip">
          {{ group.tag }} {{ group.count }}
        </span>
      </div>

      <pre v-if="experimentSnapshotText" class="snapshot">{{ experimentSnapshotText }}</pre>

      <div v-if="comparison" class="comparison">
        <strong>{{ comparison.comparable ? '对比可用' : '对比不可用' }}</strong>
        <span v-if="comparison.delta">机会差值 {{ comparison.delta.opportunities ?? 0 }}</span>
        <span v-if="comparison.reasons?.length">原因 {{ comparison.reasons.join(', ') }}</span>
      </div>

      <h3>机会</h3>
      <div v-for="opp in opportunities" :key="`${opp.code}-${opp.first_detected_date}`" class="task-row">
        <span>{{ opp.code }}</span>
        <span>{{ opp.first_detected_date }}</span>
        <span>{{ opp.exit_reason || '--' }}</span>
        <span class="quality-tags">
          <em v-for="tag in normalizeTags(opp.quality_tags)" :key="tag">{{ tag }}</em>
        </span>
        <span>价稳 {{ opp.price_stable_score ?? '--' }}</span>
        <span>量干 {{ opp.volume_dry_score ?? '--' }}</span>
        <span>{{ opp.verdict_key || '--' }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useApi } from '../composables/useApi.js'

const api = useApi()
const form = reactive({ startDate: '', endDate: '' })
const codesText = ref('')
const baselineTaskId = ref('')
const experimentEnabled = ref(false)
const experimentForm = reactive({
  minimumTotalScore: null,
  minVolumeDryScore: null,
  minPriceStableScore: null,
  timeExitDays: null,
})
const tasks = ref([])
const currentTask = ref(null)
const summary = ref(null)
const opportunities = ref([])
const comparison = ref(null)
const runningStatus = ref({ running: false, stats: {} })
const message = ref('')

const experimentSnapshotText = computed(() => {
  const raw = currentTask.value?.experiment_snapshot
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
})

const qualityGroups = computed(() => {
  const groups = summary.value?.by_quality_tag || {}
  return Object.entries(groups).map(([tag, stats]) => ({
    tag,
    count: stats?.count ?? 0,
  }))
})

function normalizeTags(tags) {
  if (Array.isArray(tags)) return tags
  if (!tags) return []
  if (typeof tags === 'string') {
    try {
      const parsed = JSON.parse(tags)
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  }
  return []
}

function buildExperimentPayload() {
  return {
    enabled: experimentEnabled.value,
    minimumTotalScore: experimentForm.minimumTotalScore || null,
    decision: {
      minVolumeDryScore: experimentForm.minVolumeDryScore || null,
      minPriceStableScore: experimentForm.minPriceStableScore || null,
    },
    timeExitDays: experimentForm.timeExitDays || null,
  }
}

function buildPayload() {
  return {
    startDate: form.startDate,
    endDate: form.endDate,
    codes: codesText.value.split(',').map(code => code.trim()).filter(Boolean),
    baselineTaskId: baselineTaskId.value || undefined,
    experiment: buildExperimentPayload(),
  }
}

async function previewExperiment() {
  const result = await api.previewStrategy1BacktestExperiment(buildExperimentPayload())
  message.value = result.valid ? result.credibilityStatus : (result.error || '实验配置无效')
  return result
}

async function startBacktest() {
  const result = await api.startStrategy1Backtest(buildPayload())
  message.value = result.ok ? `已启动 ${result.task_id || result.taskId}` : (result.message || result.error || '启动失败')
  await loadTasks()
  return result
}

async function loadTasks() {
  const result = await api.getStrategy1BacktestTasks()
  tasks.value = result.tasks || []
}

async function loadTask(taskId) {
  const detail = await api.getStrategy1BacktestTask(taskId)
  currentTask.value = detail?.task || null
  summary.value = detail?.summary || null
  const oppResult = await api.getStrategy1BacktestOpportunities(taskId)
  opportunities.value = oppResult.opportunities || []
  await api.getStrategy1BacktestSignals(taskId)
  await api.getStrategy1BacktestStocks(taskId)
  comparison.value = null
  if (currentTask.value?.baseline_task_id) {
    comparison.value = await api.getStrategy1BacktestComparison(taskId, currentTask.value.baseline_task_id)
  }
}

onMounted(async () => {
  runningStatus.value = await api.getStrategy1BacktestStatus()
  await loadTasks()
  if (runningStatus.value.running && runningStatus.value.taskId) {
    await loadTask(runningStatus.value.taskId)
  }
})

defineExpose({
  experimentEnabled,
  experimentForm,
  baselineTaskId,
  startBacktest,
  loadTask,
  previewExperiment,
  normalizeTags,
})
</script>

<style scoped>
.strategy1-backtest { padding: 20px; display: grid; gap: 16px; color: var(--text-primary); }
.panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 12px; }
h1, h2, h3, p { margin: 0; }
p { color: var(--text-secondary); font-size: 13px; }
.form-grid, .experiment-box, .metrics { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
label { display: grid; gap: 4px; font-size: 12px; color: var(--text-secondary); }
input, select { background: var(--bg-main); color: var(--text-primary); border: 1px solid var(--border); border-radius: 4px; padding: 6px 8px; }
.check { display: flex; grid-template-columns: auto 1fr; margin: 12px 0; align-items: center; }
.experiment-box { border: 1px dashed var(--accent); padding: 12px; border-radius: 6px; margin-bottom: 12px; }
.actions { display: flex; gap: 10px; }
button { border: 1px solid var(--border); background: var(--bg-main); color: var(--text-primary); padding: 7px 12px; border-radius: 4px; cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.badge { display: inline-flex; align-items: center; padding: 3px 8px; border-radius: 999px; background: rgba(212, 175, 55, 0.16); color: var(--accent); font-size: 12px; }
.badge.running { color: var(--up-red); }
.task-row { display: grid; grid-template-columns: 1fr auto auto auto auto auto auto; gap: 12px; padding: 8px 0; border-top: 1px solid var(--border); cursor: pointer; align-items: center; }
.snapshot { background: var(--bg-main); padding: 10px; border-radius: 6px; overflow: auto; }
.comparison, .message { margin-top: 10px; display: flex; gap: 12px; color: var(--text-secondary); }
.empty { padding: 10px 0; }
.quality-groups { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.quality-chip { display: inline-flex; padding: 3px 8px; border-radius: 999px; background: rgba(64, 156, 255, 0.15); color: #7db7ff; font-size: 12px; }
.quality-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.quality-tags em { font-style: normal; padding: 2px 6px; border-radius: 999px; background: rgba(212, 175, 55, 0.14); color: var(--accent); font-size: 11px; }
</style>
