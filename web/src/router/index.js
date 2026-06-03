import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'ScannerConsole', component: () => import('../pages/ScannerConsole.vue') },
  { path: '/results', name: 'ResultsRadar', component: () => import('../pages/ResultsRadar.vue') },
  { path: '/tasks', name: 'TaskCenter', component: () => import('../pages/TaskCenter.vue') },
  { path: '/config', name: 'StrategyConfig', component: () => import('../pages/StrategyConfig.vue') },
  { path: '/stock/:code', name: 'StockDetail', component: () => import('../pages/StockDetail.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
