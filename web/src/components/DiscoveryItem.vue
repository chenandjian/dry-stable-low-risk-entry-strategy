<template>
  <div class="discovery-item" @click="$emit('click')">
    <div class="signal-bar" :class="barClass"></div>
    <div class="info">
      <div class="top-row">
        <span class="code">{{ code }}</span>
        <span class="name">{{ name }}</span>
        <SignalBadge :type="ratingType">{{ ratingLabel }}</SignalBadge>
        <SignalBadge :type="statusType">{{ statusLabel }}</SignalBadge>
      </div>
      <div class="detail-row">
        {{ detail }}
      </div>
    </div>
    <div class="score" :class="scoreColor">{{ score }}</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import SignalBadge from './SignalBadge.vue'

const props = defineProps({
  code: String,
  name: String,
  score: Number,
  rating: String,     // 'strong' | 'medium' | 'weak'
  status: String,     // 'breakout' | 'near' | 'watch'
  detail: String,
})
defineEmits(['click'])

const barClass = computed(() => {
  if (props.status === 'breakout') return 'bar-red'
  if (props.status === 'near') return 'bar-orange'
  return 'bar-blue'
})
const ratingType = computed(() => props.rating || 'medium')
const ratingLabel = computed(() => ({
  strong: '强候选', medium: '中等候选', weak: '弱候选'
})[props.rating] || '候选')
const statusType = computed(() => props.status || 'watch')
const statusLabel = computed(() => ({
  breakout: '已突破', near: '接近突破', watch: '观察'
})[props.status] || '观察')
const scoreColor = computed(() => {
  if (props.score >= 80) return 'score-gold'
  if (props.score >= 70) return 'score-blue'
  return 'score-muted'
})
</script>

<style scoped>
.discovery-item {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; border-bottom: 1px solid rgba(31,42,58,0.5);
  cursor: pointer; transition: background 0.1s;
}
.discovery-item:hover { background: rgba(79,125,255,0.04); }
.signal-bar { width: 3px; height: 36px; border-radius: 2px; flex-shrink: 0; }
.bar-red { background: var(--up-red); }
.bar-orange { background: var(--warn-orange); }
.bar-blue { background: var(--accent); }
.info { flex: 1; min-width: 0; }
.top-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.code { font-family: var(--font-mono); color: var(--accent); font-size: 13px; font-weight: 600; }
.name { color: var(--text-primary); font-size: 13px; }
.detail-row { font-size: 11px; color: var(--text-muted); margin-top: 3px; }
.score { font-size: 20px; font-weight: 700; font-family: var(--font-mono); flex-shrink: 0; }
.score-gold { color: var(--gold); }
.score-blue { color: var(--text-primary); }
.score-muted { color: var(--text-muted); }
</style>
