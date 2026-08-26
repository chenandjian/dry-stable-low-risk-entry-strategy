<template>
  <nav class="topnav">
    <div class="topnav-brand">
      <span class="brand-mark">S6</span>
      <span class="brand-copy">
        <strong>VCP 决策终端</strong>
        <small>STRATEGY 6</small>
      </span>
    </div>
    <div class="topnav-tabs">
      <router-link to="/" class="topnav-tab" :class="{ active: isActive('/') }">策略6扫描</router-link>
      <router-link to="/strategy6/results" class="topnav-tab" :class="{ active: isActive('/strategy6/results') }">策略6候选</router-link>
      <router-link to="/strategy6/batch-evaluation" class="topnav-tab" :class="{ active: isActive('/strategy6/batch-evaluation') }">批量评分</router-link>
      <router-link to="/data/kline-history" class="topnav-tab" :class="{ active: isActive('/data/kline-history') }">K线数据</router-link>
      <router-link to="/tasks" class="topnav-tab" :class="{ active: isActive('/tasks') }">任务中心</router-link>
      <router-link to="/config" class="topnav-tab" :class="{ active: isActive('/config') }">策略配置</router-link>
    </div>
    <div class="topnav-right">
      <span class="market-indicator" :class="marketSessionClass">{{ marketSessionText }}</span>
      <span class="data-date">数据日 {{ latestTradeDate || '--' }}</span>
      <span class="last-scan">扫描 {{ lastScan || '--' }}</span>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const lastScan = ref('')
const latestTradeDate = ref('')
const marketSessionText = ref('A股休市')
const marketSessionClass = ref('closed')
let marketClock = null

function isActive(path) {
  if (path === '/') return route.path === '/' || route.path === ''
  return route.path.startsWith(path)
}

function updateMarketSession() {
  const now = new Date()
  const weekday = now.getDay() >= 1 && now.getDay() <= 5
  const minutes = now.getHours() * 60 + now.getMinutes()
  const open = weekday && ((minutes >= 570 && minutes <= 690) || (minutes >= 780 && minutes <= 900))
  const paused = weekday && minutes > 690 && minutes < 780
  marketSessionText.value = open ? 'A股交易中' : paused ? '午间休市' : 'A股休市'
  marketSessionClass.value = open ? 'open' : paused ? 'paused' : 'closed'
}

onMounted(async () => {
  updateMarketSession()
  marketClock = setInterval(updateMarketSession, 60_000)
  try {
    const res = await fetch('/api/strategy6/tasks')
    const data = await res.json()
    const tasks = data.tasks || []
    if (tasks.length) {
      const d = tasks[0].date || tasks[0].started_at
      lastScan.value = d ? d.slice(5, 16) : d
      latestTradeDate.value = tasks[0].latest_trade_date || ''
    }
  } catch (e) {
    console.error('Failed to fetch last scan:', e)
  }
})

onUnmounted(() => { if (marketClock) clearInterval(marketClock) })
</script>

<style scoped>
.topnav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 54px;
  background: rgba(11, 17, 27, 0.96); border-bottom: 1px solid var(--border);
  box-shadow: 0 6px 24px rgba(0,0,0,0.18);
  position: sticky; top: 0; z-index: 100;
}
.topnav-brand {
  min-width: 210px; display: flex; align-items: center; gap: 10px;
}
.brand-mark {
  display: grid; place-items: center; width: 32px; height: 28px;
  border: 1px solid rgba(214,168,74,0.5); color: var(--gold);
  font: 700 13px/1 var(--font-mono); letter-spacing: 0.08em;
}
.brand-copy { display: flex; flex-direction: column; line-height: 1.1; }
.brand-copy strong { color: var(--text-primary); font-size: 13px; letter-spacing: 0.04em; }
.brand-copy small { color: var(--text-muted); font: 9px/1.2 var(--font-mono); letter-spacing: 0.16em; margin-top: 3px; }
.topnav-tabs { display: flex; height: 100%; }
.topnav-tab {
  display: flex; align-items: center; padding: 0 18px; font-size: 13px; color: var(--text-secondary);
  border-bottom: 2px solid transparent; text-decoration: none;
  transition: color 0.15s, background 0.15s, border-color 0.15s;
}
.topnav-tab:hover { color: var(--text-primary); background: rgba(255,255,255,0.018); text-decoration: none; }
.topnav-tab.active { color: #fff; border-bottom-color: var(--gold); background: linear-gradient(180deg, transparent, rgba(214,168,74,0.055)); }
.topnav-right { min-width: 310px; display: flex; justify-content: flex-end; align-items: center; gap: 12px; font: 11px/1 var(--font-mono); color: var(--text-muted); }
.market-indicator { color: var(--text-secondary); }
.market-indicator::before { content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; }
.market-indicator.open::before { background: var(--up-red); box-shadow: 0 0 8px var(--up-red); }
.market-indicator.paused::before { background: var(--gold); }
.market-indicator.closed::before { background: var(--text-muted); }
.data-date { color: var(--text-secondary); }
.btn-primary {
  background: var(--accent); color: #fff; border: none;
  padding: 6px 16px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.btn-primary:hover { opacity: 0.9; }
@media (max-width: 1100px) {
  .topnav-brand { min-width: auto; }
  .brand-copy { display: none; }
  .topnav-right { min-width: auto; }
  .last-scan { display: none; }
}
@media (max-width: 760px) {
  .topnav { padding: 0 10px; overflow-x: auto; }
  .topnav-tab { padding: 0 10px; white-space: nowrap; }
  .topnav-right { display: none; }
}
</style>
