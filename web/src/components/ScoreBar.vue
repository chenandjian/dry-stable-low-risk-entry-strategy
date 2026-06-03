<template>
  <div class="score-bar-item">
    <div class="score-row">
      <span class="score-label">{{ label }}</span>
      <span class="score-value" :style="valueColor">{{ current }} / {{ max }} </span>
    </div>
    <div class="score-track">
      <div class="score-fill" :class="barColor" :style="{ width: pct + '%' }"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({
  label: String,
  current: Number,
  max: Number,
})
const pct = computed(() => props.max > 0 ? Math.round(props.current / props.max * 100) : 0)
const barColor = computed(() => {
  if (pct.value >= 85) return 'fill-gold'
  if (pct.value >= 60) return 'fill-blue'
  return 'fill-red'
})
const valueColor = computed(() => {
  if (pct.value >= 85) return 'color: var(--gold)'
  if (pct.value >= 60) return 'color: var(--accent)'
  return 'color: var(--up-red)'
})
</script>

<style scoped>
.score-bar-item { padding: 8px 0; }
.score-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.score-label { font-size: 13px; color: var(--text-secondary); }
.score-value { font-size: 13px; font-family: var(--font-mono); font-weight: 600; }
.score-track { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 2px; transition: width 0.3s; }
.fill-gold { background: var(--gold); }
.fill-blue { background: var(--accent); }
.fill-red { background: var(--up-red); }
</style>
