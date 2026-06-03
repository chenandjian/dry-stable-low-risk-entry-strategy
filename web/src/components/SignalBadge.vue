<template>
  <span class="badge" :class="`badge-${type}`">
    <slot />
  </span>
</template>

<script setup>
defineProps({
  type: {
    type: String,
    default: 'medium',
    validator: v => ['strong', 'medium', 'weak', 'breakout', 'near', 'watch', 'volume'].includes(v),
  },
})
</script>

<style scoped>
.badge {
  display: inline-block; font-size: 11px; font-weight: 600;
  padding: 3px 10px; border-radius: 3px; white-space: nowrap;
}
.badge-strong { background: rgba(245,158,11,0.15); color: var(--gold); }
.badge-medium { background: rgba(79,125,255,0.12); color: var(--accent); }
.badge-weak { background: rgba(90,106,126,0.12); color: var(--text-muted); }
.badge-breakout { background: rgba(239,68,68,0.12); color: var(--up-red); }
.badge-near { background: rgba(249,115,22,0.12); color: var(--warn-orange); }
.badge-watch { background: rgba(90,106,126,0.1); color: var(--text-muted); }
.badge-volume { background: rgba(239,68,68,0.1); color: var(--up-red); }
</style>
