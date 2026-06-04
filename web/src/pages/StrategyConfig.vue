<template>
  <div class="page-content">
    <h2 class="page-title">策略配置</h2>
    <p class="page-sub">修改扫描参数，保存后下次扫描生效</p>

    <!-- 市场范围 -->
    <section class="section">
      <h3 class="section-title">市场范围</h3>
      <div class="toggle-grid">
        <label v-for="m in markets" :key="m.key" class="toggle-item">
          <span class="toggle-label" :title="m.tip">{{ m.label }}</span>
          <button class="toggle" :class="{ active: config.market?.[m.key] }"
            @click="toggle('market', m.key)">{{ config.market?.[m.key] ? '开' : '关' }}</button>
        </label>
      </div>
    </section>

    <!-- 基础参数 -->
    <section class="section">
      <h3 class="section-title">基础参数</h3>
      <div class="param-grid">
        <div class="param">
          <label title="近20日平均成交额低于此值的股票将被过滤（单位：元）">平均成交额阈值 <span class="unit">万元</span></label>
          <input type="number" v-model.number="config.liquidity.min_avg_turnover"
            @input="markDirty" step="1000000" />
          <span class="default">默认 1亿</span>
        </div>
        <div class="param">
          <label title="股价低于此值的股票将被过滤（单位：元）">最低股价 <span class="unit">元</span></label>
          <input type="number" v-model.number="config.liquidity.min_stock_price"
            @input="markDirty" step="1" min="0" />
          <span class="default">默认 10元</span>
        </div>
        <div class="param">
          <label title="上市交易日少于此天数的股票将被过滤">新股最短上市天数 <span class="unit">交易日</span></label>
          <input type="number" v-model.number="config.liquidity.min_listing_days"
            @input="markDirty" step="10" min="30" />
          <span class="default">默认 250天</span>
        </div>
      </div>
    </section>

    <!-- 高级参数 -->
    <section class="section">
      <h3 class="section-title" style="cursor:pointer" @click="showAdvanced = !showAdvanced">
        {{ showAdvanced ? '▾' : '▸' }} 高级参数
      </h3>
      <div v-if="showAdvanced">
        <h4 class="sub-group-title">流动性</h4>
        <div class="param-grid">
          <div class="param">
            <label title="近20日平均成交量低于此值的股票将被过滤（单位：股）">平均成交量阈值 <span class="unit">股</span></label>
            <input type="number" v-model.number="config.liquidity.min_avg_volume"
              @input="markDirty" step="100000" />
            <span class="default">默认 500万</span>
          </div>
          <div class="param">
            <label title="最近交易日成交额低于此值的股票将被过滤（单位：元）">最新成交额阈值 <span class="unit">万元</span></label>
            <input type="number" v-model.number="config.liquidity.min_latest_turnover"
              @input="markDirty" step="1000000" />
            <span class="default">默认 8000万</span>
          </div>
        </div>

        <h4 class="sub-group-title">杯体结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="60" v-model.number="config.cup.min_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.min_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体从杯口到杯底再到杯口的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="100" max="250" v-model.number="config.cup.max_duration" @input="markDirty" />
            <div class="range-val">{{ config.cup.max_duration }} 天</div>
          </div>
          <div class="param">
            <label title="杯体回调的最小幅度，低于此幅度不算杯体">最小深度 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupMinDepth" @input="markDirty" />
            <div class="range-val">{{ cupMinDepth }}%</div>
          </div>
          <div class="param">
            <label title="杯体回调的最大幅度，超过此幅度杯体太深">最大深度 <span class="unit">%</span></label>
            <input type="range" min="30" max="55" step="1" v-model.number="cupMaxDepth" @input="markDirty" />
            <div class="range-val">{{ cupMaxDepth }}%</div>
          </div>
          <div class="param">
            <label title="左右杯口价格的最大偏差比例">杯口最大偏差 <span class="unit">%</span></label>
            <input type="range" min="5" max="20" step="1" v-model.number="cupLipDeviation" @input="markDirty" />
            <div class="range-val">{{ cupLipDeviation }}%</div>
          </div>
          <div class="param">
            <label title="杯底附近价格在杯底8%范围内的比例阈值">杯底圆滑度 <span class="unit">%</span></label>
            <input type="range" min="5" max="30" step="1" v-model.number="cupRoundness" @input="markDirty" />
            <div class="range-val">{{ cupRoundness }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">柄部结构</h4>
        <div class="param-grid">
          <div class="param">
            <label title="柄部回调的最短交易日数">最短周期 <span class="unit">交易日</span></label>
            <input type="range" min="3" max="10" v-model.number="handleMinDur" @input="markDirty" />
            <div class="range-val">{{ handleMinDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部回调的最长交易日数">最长周期 <span class="unit">交易日</span></label>
            <input type="range" min="20" max="40" v-model.number="handleMaxDur" @input="markDirty" />
            <div class="range-val">{{ handleMaxDur }} 天</div>
          </div>
          <div class="param">
            <label title="柄部从右杯口向下的最大回撤幅度">最大回撤 <span class="unit">%</span></label>
            <input type="range" min="8" max="25" step="1" v-model.number="handleMaxDepth" @input="markDirty" />
            <div class="range-val">{{ handleMaxDepth }}%</div>
          </div>
        </div>

        <h4 class="sub-group-title">突破判断</h4>
        <div class="param-grid">
          <div class="param">
            <label title="突破确认的价格缓冲比例，超过杯口此比例算突破">缓冲比例 <span class="unit">%</span></label>
            <input type="range" min="0" max="5" step="0.5" v-model.number="breakoutBuffer" @input="markDirty" />
            <div class="range-val">{{ breakoutBuffer }}%</div>
          </div>
          <div class="param">
            <label title="突破当天成交量相对均量的倍数阈值">放量倍数</label>
            <input type="range" min="1.0" max="2.5" step="0.1" v-model.number="config.breakout.volume_multiplier" @input="markDirty" />
            <div class="range-val">{{ config.breakout.volume_multiplier }}×</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Actions -->
    <div class="actions-bar">
      <div v-if="saved" class="saved-msg">✓ 配置已保存</div>
      <div v-if="error" class="error-msg">{{ error }}</div>
      <div class="actions-right">
        <button class="btn-reset" @click="resetAll">恢复默认</button>
        <button class="btn-save" :class="{ dirty }" @click="saveConfig" :disabled="saving">
          {{ saving ? '保存中...' : '保存配置' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useApi } from '../composables/useApi.js'

const { getConfig, updateConfig } = useApi()

const config = reactive({
  market: {},
  liquidity: {},
  cup: {},
  handle: {},
  breakout: {},
})

const dirty = ref(false)
const saved = ref(false)
const saving = ref(false)
const error = ref('')
const showAdvanced = ref(false)

// Computed: convert cup depth from 0-1 to percentage for slider display
const cupMinDepth = computed({
  get: () => Math.round((config.cup.min_depth || 0.12) * 100),
  set: (v) => { config.cup.min_depth = v / 100 },
})
const cupMaxDepth = computed({
  get: () => Math.round((config.cup.max_depth || 0.45) * 100),
  set: (v) => { config.cup.max_depth = v / 100 },
})
const cupRoundness = computed({
  get: () => Math.round((config.cup.min_bottom_roundness || 0.15) * 100),
  set: (v) => { config.cup.min_bottom_roundness = v / 100 },
})
const cupLipDeviation = computed({
  get: () => Math.round((config.cup.max_lip_deviation || 0.12) * 100),
  set: (v) => { config.cup.max_lip_deviation = v / 100 },
})
const handleMinDur = computed({
  get: () => config.handle?.min_duration || 5,
  set: (v) => { config.handle.min_duration = v },
})
const handleMaxDur = computed({
  get: () => config.handle?.max_duration || 30,
  set: (v) => { config.handle.max_duration = v },
})
const handleMaxDepth = computed({
  get: () => Math.round((config.handle?.max_depth || 0.18) * 100),
  set: (v) => { config.handle.max_depth = v / 100 },
})
const breakoutBuffer = computed({
  get: () => Math.round((config.breakout?.buffer_pct || 0.02) * 100),
  set: (v) => { config.breakout.buffer_pct = v / 100 },
})

const markets = [
  { key: 'include_sh', label: '沪市主板', tip: '上证主板股票，代码 60xxxx' },
  { key: 'include_sz', label: '深市主板', tip: '深证主板股票，代码 00xxxx/002xxx/003xxx' },
  { key: 'include_cyb', label: '创业板', tip: '创业板股票，代码 300xxx/301xxx' },
  { key: 'include_kcb', label: '科创板', tip: '科创板股票，代码 688xxx' },
  { key: 'exclude_bj', label: '排除北交所', tip: '排除北交所股票，代码 8xxxxx/4xxxxx' },
  { key: 'exclude_st', label: '排除 ST/*ST', tip: '排除 ST 及 *ST 股票' },
]

function toggle(section, key) {
  config[section][key] = !config[section][key]
  markDirty()
}

function markDirty() {
  dirty.value = true
  saved.value = false
}

function validate() {
  const errors = []
  const cup = config.cup
  const handle = config.handle

  if (cup.min_duration < 20 || cup.min_duration > 60) errors.push('杯体最短周期需在 20-60 天之间')
  if (cup.max_duration < 100 || cup.max_duration > 250) errors.push('杯体最长周期需在 100-250 天之间')
  if (cup.min_duration >= cup.max_duration) errors.push('杯体最短周期必须小于最长周期')
  if (cup.min_depth < 0.05 || cup.min_depth > 0.20) errors.push('杯体最小深度需在 5%-20% 之间')
  if (cup.max_depth < 0.30 || cup.max_depth > 0.55) errors.push('杯体最大深度需在 30%-55% 之间')
  if (cup.min_depth >= cup.max_depth) errors.push('杯体最小深度必须小于最大深度')
  if (handle.min_duration < 3 || handle.min_duration > 10) errors.push('柄部最短周期需在 3-10 天之间')
  if (handle.max_duration < 20 || handle.max_duration > 40) errors.push('柄部最长周期需在 20-40 天之间')
  if (handle.min_duration >= handle.max_duration) errors.push('柄部最短周期必须小于最长周期')
  if (handle.max_depth < 0.08 || handle.max_depth > 0.25) errors.push('柄部最大回撤需在 8%-25% 之间')

  const liq = config.liquidity
  if (liq.min_avg_turnover < 10000000) errors.push('成交额阈值最低 1000万')
  if (liq.min_stock_price < 1) errors.push('最低股价不能低于 1元')
  if (liq.min_listing_days < 30) errors.push('上市天数最低 30天')

  return errors
}

async function saveConfig() {
  const errors = validate()
  if (errors.length) {
    error.value = errors.join('；')
    return
  }
  saving.value = true
  error.value = ''
  try {
    // Build the payload matching config.yaml structure
    const payload = {
      market: { ...config.market },
      liquidity: { ...config.liquidity },
      cup: {
        min_duration: config.cup.min_duration,
        max_duration: config.cup.max_duration,
        min_depth: config.cup.min_depth,
        max_depth: config.cup.max_depth,
        max_lip_deviation: config.cup.max_lip_deviation,
        min_bottom_roundness: config.cup.min_bottom_roundness,
      },
      handle: {
        min_duration: config.handle.min_duration,
        max_duration: config.handle.max_duration,
        max_depth: config.handle.max_depth,
      },
      breakout: {
        buffer_pct: config.breakout.buffer_pct,
        volume_multiplier: config.breakout.volume_multiplier,
      },
    }
    const res = await updateConfig(payload)
    if (res.status === 'ok') {
      dirty.value = false
      saved.value = true
      setTimeout(() => { saved.value = false }, 3000)
    } else {
      error.value = res.message || '保存失败'
    }
  } catch (e) {
    error.value = '保存失败，请检查后端服务'
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
    }
    dirty.value = false
    saved.value = false
    error.value = ''
  } catch (e) {
    error.value = '加载配置失败'
  }
}

onMounted(async () => {
  try {
    const data = await getConfig()
    if (data.config) {
      Object.assign(config, data.config)
    }
  } catch (e) {
    // use defaults
  }
})
</script>

<style scoped>
.page-content { padding: 20px 24px; max-width: 900px; margin: 0 auto; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.page-sub { font-size: 13px; color: var(--text-muted); margin-bottom: 24px; }

.section {
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px; margin-bottom: 16px;
}
.section-title {
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid var(--border);
}

.toggle-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.toggle-item { display: flex; align-items: center; gap: 10px; cursor: pointer; }
.toggle-label { font-size: 13px; color: var(--text-secondary); min-width: 90px; }
.toggle {
  padding: 4px 14px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted); font-size: 12px; font-weight: 600; cursor: pointer;
}
.toggle.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.param-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 600px) { .param-grid { grid-template-columns: 1fr; } }
.param label { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }
.param .unit { font-size: 11px; color: var(--text-muted); }
.param .default { font-size: 10px; color: var(--text-muted); margin-top: 2px; display: block; }
.param input[type="range"] { width: 100%; accent-color: var(--accent); }
.param input[type="number"] {
  width: 100%; padding: 6px 10px; border-radius: 4px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-primary); font-family: var(--font-mono); font-size: 14px;
}
.range-val { font-family: var(--font-mono); font-size: 18px; font-weight: 700; color: var(--accent); margin-top: 4px; }

.sub-group-title {
  font-size: 12px; color: var(--text-muted); margin: 0 0 10px;
  font-weight: 600;
}

.actions-bar {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-panel); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; margin-top: 20px;
  position: sticky; bottom: 20px;
}
.saved-msg { color: var(--down-green); font-size: 13px; font-weight: 600; }
.error-msg { color: var(--up-red); font-size: 13px; }
.actions-right { display: flex; gap: 10px; }
.btn-reset {
  padding: 8px 18px; border-radius: 4px; border: 1px solid var(--border);
  background: transparent; color: var(--text-secondary); font-size: 13px; cursor: pointer;
}
.btn-save {
  padding: 8px 24px; border-radius: 4px; border: none;
  background: var(--border); color: var(--text-muted); font-size: 13px; font-weight: 600; cursor: pointer;
}
.btn-save.dirty {
  background: var(--accent); color: #fff;
}
</style>
