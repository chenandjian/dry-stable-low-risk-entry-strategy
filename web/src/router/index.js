import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'ScannerConsole', component: () => import('../pages/ScannerConsole.vue') },
  { path: '/results', name: 'ResultsRadar', component: () => import('../pages/ResultsRadar.vue') },
  { path: '/tasks', name: 'TaskCenter', component: () => import('../pages/TaskCenter.vue') },
  { path: '/config', name: 'StrategyConfig', component: () => import('../pages/StrategyConfig.vue') },
  { path: '/backtest/cup-handle/:code?', name: 'SingleStockBacktest', component: () => import('../pages/SingleStockBacktest.vue') },
  { path: '/strategy1/backtest', name: 'Strategy1Backtest', component: () => import('../pages/Strategy1Backtest.vue') },
  { path: '/data/kline-history', name: 'KlineHistory', component: () => import('../pages/KlineHistory.vue') },
  { path: '/stock/:code', name: 'StockDetail', component: () => import('../pages/StockDetail.vue') },
  { path: '/strategy2/results', name: 'Strategy2Results', component: () => import('../pages/Strategy2Results.vue') },
  { path: '/strategy2/backtest', name: 'Strategy2Backtest', component: () => import('../pages/Strategy2Backtest.vue') },
  { path: '/strategy3/results', name: 'Strategy3Results', component: () => import('../pages/Strategy3Results.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
