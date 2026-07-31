<template>
  <div class="metric-card" :class="`metric-${color}`">
    <div class="metric-label">{{ label }}</div>
    <div class="metric-value" :class="colorClass">{{ value }}</div>
    <div class="metric-sub">{{ sub }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  label: String,
  value: [String, Number],
  sub: String,
  color: { type: String, default: 'primary' },
})
const colorClass = computed(() => `color-${props.color}`)
</script>

<style scoped>
.metric-card {
  position: relative; overflow: hidden;
  background: linear-gradient(180deg, var(--bg-card), rgba(16,24,36,0.72));
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 15px 18px 14px;
}
.metric-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: var(--border-light);
}
.metric-red::before { background: var(--up-red); }
.metric-gold::before { background: var(--gold); }
.metric-blue::before { background: var(--accent); }
.metric-orange::before { background: var(--warn-orange); }
.metric-label { font-size: 11px; color: var(--text-secondary); margin-bottom: 7px; letter-spacing: 0.04em; }
.metric-value { font-size: 28px; font-weight: 700; font-family: var(--font-mono); line-height: 1.1; font-variant-numeric: tabular-nums; }
.metric-sub { font: 10px/1.3 var(--font-mono); color: var(--text-muted); margin-top: 5px; }
.color-primary { color: var(--text-primary); }
.color-gold { color: var(--gold); }
.color-red { color: var(--up-red); }
.color-blue { color: var(--accent); }
.color-orange { color: var(--warn-orange); }
</style>
