<template>
  <nav class="topnav">
    <div class="topnav-brand">
      CupHandle<span class="accent">Scan</span>
    </div>
    <div class="topnav-tabs">
      <router-link to="/" class="topnav-tab" active-class="active">机会雷达</router-link>
      <router-link to="/results" class="topnav-tab" active-class="active">候选列表</router-link>
      <router-link to="/tasks" class="topnav-tab" active-class="active">任务中心</router-link>
    </div>
    <div class="topnav-right">
      <span class="market-indicator">A股市场</span>
      <span class="last-scan">上次扫描: --</span>
      <button class="btn-primary" @click="$emit('startScan')">开始扫描</button>
    </div>
  </nav>
</template>

<script setup>
defineEmits(['startScan'])
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
