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
    validator: v => ['strong', 'medium', 'weak', 'breakout', 'confirm', 'near', 'watch', 'wait', 'volume'].includes(v),
  },
})
</script>

<style scoped>
.badge {
  display: inline-block; font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 2px; white-space: nowrap;
  border: 1px solid transparent; letter-spacing: 0.02em;
}
.badge-strong { background: var(--gold-glow); border-color: rgba(214,168,74,0.28); color: var(--gold); }
.badge-medium { background: var(--accent-glow); border-color: rgba(76,141,255,0.22); color: var(--accent-strong); }
.badge-weak { background: rgba(98,115,134,0.09); border-color: rgba(98,115,134,0.18); color: var(--text-muted); }
.badge-breakout { background: var(--up-red-glow); border-color: rgba(240,68,68,0.22); color: var(--up-red); }
.badge-confirm { background: var(--warn-orange-glow); border-color: rgba(232,144,63,0.22); color: var(--warn-orange); }
.badge-near { background: var(--accent-glow); border-color: rgba(76,141,255,0.2); color: var(--accent-strong); }
.badge-wait { background: rgba(90,106,126,0.1); color: var(--text-muted); }
.badge-watch { background: rgba(90,106,126,0.1); color: var(--text-muted); }
.badge-volume { background: rgba(239,68,68,0.1); color: var(--up-red); }
</style>
