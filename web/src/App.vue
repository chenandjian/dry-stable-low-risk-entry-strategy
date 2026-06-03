<template>
  <div id="cuphandle-app">
    <TopNav />
    <router-view />
  </div>
</template>

<script setup>
import TopNav from './components/TopNav.vue'
</script>

<style>
@import './styles/variables.css';
</style>
