import { createRouter, createWebHistory } from 'vue-router'

export const routes = [
  { path: '/', name: 'ScannerConsole', component: () => import('../pages/ScannerConsole.vue') },
  { path: '/tasks', name: 'TaskCenter', component: () => import('../pages/TaskCenter.vue') },
  { path: '/config', name: 'StrategyConfig', component: () => import('../pages/StrategyConfig.vue') },
  { path: '/data/kline-history', name: 'KlineHistory', component: () => import('../pages/KlineHistory.vue') },
  { path: '/stock/:code', name: 'StockDetail', component: () => import('../pages/StockDetail.vue') },
  { path: '/strategy6/results', name: 'Strategy6Results', component: () => import('../pages/Strategy6Results.vue') },
  { path: '/strategy6/batch-evaluation', name: 'Strategy6BatchEvaluation', component: () => import('../pages/Strategy6BatchEvaluation.vue') },
  { path: '/market-breadth', name: 'MarketBreadth', component: () => import('../pages/MarketBreadth.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/strategy6/results' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
