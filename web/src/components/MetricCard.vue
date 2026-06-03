<template>
  <div class="metric-card">
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
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 16px 18px;
}
.metric-label { font-size: 12px; color: var(--text-muted); margin-bottom: 6px; }
.metric-value { font-size: 30px; font-weight: 700; font-family: var(--font-mono); line-height: 1.1; }
.metric-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.color-primary { color: var(--text-primary); }
.color-gold { color: var(--gold); }
.color-red { color: var(--up-red); }
.color-blue { color: var(--accent); }
.color-orange { color: var(--warn-orange); }
</style>
