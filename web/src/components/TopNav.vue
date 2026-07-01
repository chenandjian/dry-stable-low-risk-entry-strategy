<template>
  <nav class="topnav">
    <div class="topnav-brand">
      CupHandle<span class="accent">Scan</span>
    </div>
    <div class="topnav-tabs">
      <router-link to="/" class="topnav-tab" :class="{ active: isActive('/') }">机会雷达</router-link>
      <router-link to="/results" class="topnav-tab" :class="{ active: isActive('/results') }">候选列表</router-link>
      <router-link to="/strategy2/results" class="topnav-tab" :class="{ active: isActive('/strategy2/results') }">策略2</router-link>
      <router-link to="/strategy3/results" class="topnav-tab" :class="{ active: isActive('/strategy3/results') }">策略3候选</router-link>
      <router-link to="/strategy4/results" class="topnav-tab" :class="{ active: isActive('/strategy4/results') }">策略4热点</router-link>
      <router-link to="/strategy1/backtest" class="topnav-tab" :class="{ active: isActive('/strategy1/backtest') }">策略1回测</router-link>
      <router-link to="/strategy2/backtest" class="topnav-tab" :class="{ active: isActive('/strategy2/backtest') }">策略2回测</router-link>
      <router-link to="/backtest/cup-handle" class="topnav-tab" :class="{ active: isActive('/backtest/cup-handle') }">单股回测</router-link>
      <router-link to="/data/kline-history" class="topnav-tab" :class="{ active: isActive('/data/kline-history') }">K线数据</router-link>
      <router-link to="/tasks" class="topnav-tab" :class="{ active: isActive('/tasks') }">任务中心</router-link>
      <router-link to="/config" class="topnav-tab" :class="{ active: isActive('/config') }">策略配置</router-link>
    </div>
    <div class="topnav-right">
      <span class="market-indicator">A股市场</span>
      <span class="last-scan">上次扫描: {{ lastScan || '--' }}</span>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const lastScan = ref('')

function isActive(path) {
  if (path === '/') return route.path === '/' || route.path === ''
  return route.path.startsWith(path)
}

onMounted(async () => {
  try {
    const res = await fetch('/api/scan/tasks')
    const data = await res.json()
    const tasks = data.tasks || []
    if (tasks.length) {
      const d = tasks[0].date
      lastScan.value = d ? d.slice(5, 16) : d
    }
  } catch (e) {
    console.error('Failed to fetch last scan:', e)
  }
})
</script>

<style scoped>
.topnav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 24px; height: 48px;
  background: var(--bg-panel); border-bottom: 1px solid var(--border);
}
.topnav-brand {
  font-size: 16px; font-weight: 700; color: var(--text-primary);
  display: flex; align-items: center; gap: 6px;
}
.topnav-brand .accent { color: var(--accent); }
.topnav-tabs { display: flex; }
.topnav-tab {
  padding: 13px 18px; font-size: 13px; color: var(--text-secondary);
  border-bottom: 2px solid transparent; text-decoration: none;
  transition: all 0.15s;
}
.topnav-tab:hover { color: var(--text-primary); }
.topnav-tab.active { color: var(--text-primary); border-bottom-color: var(--accent); }
.topnav-right { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--text-secondary); }
.market-indicator::before { content: ''; display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: var(--up-red); margin-right: 6px; }
.btn-primary {
  background: var(--accent); color: #fff; border: none;
  padding: 6px 16px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.btn-primary:hover { opacity: 0.9; }
</style>
