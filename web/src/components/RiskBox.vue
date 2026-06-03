<template>
  <div class="risk-box">
    <h4>⚠ {{ title }}</h4>
    <p><slot /></p>
  </div>
</template>

<script setup>
defineProps({ title: { type: String, default: '形态风险' } })
</script>

<style scoped>
.risk-box {
  padding: 14px; background: rgba(249,115,22,0.05);
  border: 1px solid rgba(249,115,22,0.18); border-radius: 5px;
}
.risk-box h4 { font-size: 12px; font-weight: 600; color: var(--warn-orange); margin-bottom: 6px; }
.risk-box p { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
</style>
