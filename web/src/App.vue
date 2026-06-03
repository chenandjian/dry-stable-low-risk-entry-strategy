<template>
  <div id="cuphandle-app">
    <TopNav @startScan="goToScanner" />
    <router-view />
  </div>
</template>

<script setup>
import TopNav from './components/TopNav.vue'
import { useRouter } from 'vue-router'

const router = useRouter()
function goToScanner() {
  router.push('/')
}
</script>

<style>
@import './styles/variables.css';
</style>
