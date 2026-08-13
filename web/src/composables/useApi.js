const API_BASE = '/api'

export function useApi() {
  async function startScan() {
    const res = await fetch(`${API_BASE}/scan/start`)
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getScanStatus() {
    const res = await fetch(`${API_BASE}/scan/status`)
    return res.json()
  }

  async function getCandidates(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const url = `${API_BASE}/candidates${qs ? '?' + qs : ''}`
    const res = await fetch(url)
    return res.json()
  }

  async function getCandidate(code) {
    const res = await fetch(`${API_BASE}/candidate/${code}`)
    if (!res.ok) return null
    return res.json()
  }

  async function getScanTasks() {
    const res = await fetch(`${API_BASE}/scan/tasks`)
    return res.json()
  }

  async function getSchedulerLogs(limit = 100) {
    const res = await fetch(`${API_BASE}/scheduler/logs?limit=${encodeURIComponent(limit)}`)
    return res.json().catch(() => ({ scheduler: {}, events: [] }))
  }

  async function getTaskStocks(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const url = `${API_BASE}/scan/tasks/${taskId}/stocks${qs ? '?' + qs : ''}`
    const res = await fetch(url)
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getKlineHistory(params = {}) {
    const { code, ...query } = params
    const cleanQuery = Object.fromEntries(
      Object.entries(query).filter(([, value]) => value !== '' && value !== null && value !== undefined)
    )
    const qs = new URLSearchParams(cleanQuery).toString()
    const res = await fetch(`${API_BASE}/stock/${encodeURIComponent(code)}/kline-history${qs ? '?' + qs : ''}`)
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function retryFailedStocks(taskId) {
    const res = await fetch(`${API_BASE}/scan/tasks/${taskId}/retry-failed`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function reEvaluateTask(taskId) {
    const res = await fetch(`${API_BASE}/scan/tasks/${taskId}/re-evaluate`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getConfig() {
    try {
      const res = await fetch(`${API_BASE}/config`)
      return res.json()
    } catch { return { config: {} } }
  }

  async function updateConfig(data) {
    try {
      const res = await fetch(`${API_BASE}/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
      return res.json()
    } catch { return { status: 'error', message: '保存失败' } }
  }

  async function runCupHandleBacktest(code, payload) {
    const res = await fetch(`${API_BASE}/stock/${code}/backtest/cup-handle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  // Strategy2 API
  async function startStrategy2Scan() {
    const res = await fetch(`${API_BASE}/strategy2/scans`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy2ScanStatus() {
    const res = await fetch(`${API_BASE}/strategy2/scans/status`)
    return res.json()
  }

  async function getStrategy2Tasks() {
    const res = await fetch(`${API_BASE}/strategy2/tasks`)
    return res.json()
  }

  async function retryStrategy2FailedStocks(taskId) {
    const res = await fetch(`${API_BASE}/strategy2/tasks/${encodeURIComponent(taskId)}/retry-failed`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function reEvaluateStrategy2Task(taskId) {
    const res = await fetch(`${API_BASE}/strategy2/tasks/${encodeURIComponent(taskId)}/re-evaluate`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy2Candidates(taskId) {
    const qs = taskId ? `?task_id=${taskId}` : ''
    const res = await fetch(`${API_BASE}/strategy2/candidates${qs}`)
    return res.json()
  }

  async function getStrategy2Candidate(code, taskId) {
    const qs = taskId ? `?task_id=${taskId}` : ''
    const res = await fetch(`${API_BASE}/strategy2/candidates/${code}${qs}`)
    if (!res.ok) return null
    return res.json()
  }

  // Strategy3 API
  async function startStrategy3Scan() {
    const res = await fetch(`${API_BASE}/strategy3/scans`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getKlineHealth(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/kline-health${qs ? '?' + qs : ''}`)
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function refreshKlineData(code) {
    const res = await fetch(`${API_BASE}/stock/${encodeURIComponent(code)}/kline-refresh`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function refreshKlineHealth(params = {}) {
    const res = await fetch(`${API_BASE}/kline-health/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy3ScanStatus() {
    const res = await fetch(`${API_BASE}/strategy3/scans/status`)
    return res.json()
  }

  async function getStrategy3Tasks() {
    const res = await fetch(`${API_BASE}/strategy3/tasks`)
    return res.json()
  }

  async function retryStrategy3FailedStocks(taskId) {
    const res = await fetch(`${API_BASE}/strategy3/tasks/${encodeURIComponent(taskId)}/retry-failed`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function reEvaluateStrategy3Task(taskId) {
    const res = await fetch(`${API_BASE}/strategy3/tasks/${encodeURIComponent(taskId)}/re-evaluate`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy3Candidates(taskId) {
    const qs = taskId ? `?task_id=${taskId}` : ''
    const res = await fetch(`${API_BASE}/strategy3/candidates${qs}`)
    return res.json()
  }

  async function getStrategy3Candidate(code, taskId) {
    const qs = taskId ? `?task_id=${taskId}` : ''
    const res = await fetch(`${API_BASE}/strategy3/candidates/${code}${qs}`)
    if (!res.ok) return null
    return res.json()
  }

  // Strategy4 API
  async function startStrategy4Scan() {
    const res = await fetch(`${API_BASE}/strategy4/scans`, { method: 'POST' })
    const body = await res.json()
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy4ScanStatus() {
    const res = await fetch(`${API_BASE}/strategy4/scans/status`)
    return res.json()
  }

  async function getStrategy4Tasks() {
    const res = await fetch(`${API_BASE}/strategy4/tasks`)
    return res.json()
  }

  async function getStrategy4Topics(taskId) {
    const res = await fetch(`${API_BASE}/strategy4/tasks/${encodeURIComponent(taskId)}/topics`)
    return res.json().catch(() => ({ topics: [] }))
  }

  async function getStrategy4Leaders(taskId) {
    const res = await fetch(`${API_BASE}/strategy4/tasks/${encodeURIComponent(taskId)}/leaders`)
    return res.json().catch(() => ({ leaders: [] }))
  }

  async function getStrategy4Candidates(taskId) {
    const res = await fetch(`${API_BASE}/strategy4/tasks/${encodeURIComponent(taskId)}/candidates`)
    return res.json().catch(() => ({ candidates: [] }))
  }

  async function getStrategy4Candidate(taskId, code) {
    const res = await fetch(`${API_BASE}/strategy4/tasks/${encodeURIComponent(taskId)}/candidates/${encodeURIComponent(code)}`)
    if (!res.ok) return null
    return res.json()
  }

  async function getStrategy4TrackedTopics(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/strategy4/tracking/topics${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ topics: [] }))
  }

  async function getStrategy4TrackedLeaders(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/strategy4/tracking/leaders${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ leaders: [] }))
  }

  async function getStrategy4TrackingEvents(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/strategy4/tracking/events${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ events: [] }))
  }

  // Strategy5 API
  async function startStrategy5Scan() {
    const res = await fetch(`${API_BASE}/strategy5/scans`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy5ScanStatus() {
    const res = await fetch(`${API_BASE}/strategy5/scans/status`)
    return res.json().catch(() => ({ running: false, stats: {} }))
  }

  async function getStrategy5Tasks() {
    const res = await fetch(`${API_BASE}/strategy5/tasks`)
    return res.json().catch(() => ({ tasks: [] }))
  }

  async function getStrategy5Candidates(taskId) {
    const res = await fetch(`${API_BASE}/strategy5/tasks/${encodeURIComponent(taskId)}/candidates`)
    return res.json().catch(() => ({ candidates: [] }))
  }

  async function getStrategy5Candidate(taskId, code) {
    const res = await fetch(`${API_BASE}/strategy5/tasks/${encodeURIComponent(taskId)}/candidates/${encodeURIComponent(code)}`)
    if (!res.ok) return null
    return res.json()
  }

  // Strategy6 API
  async function startStrategy6Scan() {
    const res = await fetch(`${API_BASE}/strategy6/scans`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function analyzeCleanK(payload) {
    const res = await fetch(`${API_BASE}/stock/clean-k/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function startTickFlowFullRefresh() {
    const res = await fetch(`${API_BASE}/tickflow/full-refresh`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getTickFlowFullRefreshStatus() {
    const res = await fetch(`${API_BASE}/tickflow/full-refresh/status`)
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function checkTickFlowFreshness(stockCode) {
    const res = await fetch(`${API_BASE}/tickflow/freshness-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_code: stockCode }),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }

  async function getStrategy6ScanStatus() {
    const res = await fetch(`${API_BASE}/strategy6/scans/status`)
    return res.json().catch(() => ({ running: false, stats: {} }))
  }

  async function getStrategy6Tasks() {
    const res = await fetch(`${API_BASE}/strategy6/tasks`)
    return res.json().catch(() => ({ tasks: [] }))
  }

  async function getStrategy6Candidates(taskId) {
    const res = await fetch(`${API_BASE}/strategy6/tasks/${encodeURIComponent(taskId)}/candidates`)
    return res.json().catch(() => ({ candidates: [] }))
  }

  async function getStrategy6MarketSnapshot(taskId) {
    const res = await fetch(`${API_BASE}/strategy6/tasks/${encodeURIComponent(taskId)}/market-snapshot`)
    if (!res.ok) throw new Error(`strategy6 market snapshot failed: ${res.status}`)
    return res.json().catch(() => ({ snapshot: null }))
  }

  async function getStrategy6Lifecycle(taskId) {
    const res = await fetch(`${API_BASE}/strategy6/tasks/${encodeURIComponent(taskId)}/lifecycle`)
    if (!res.ok) throw new Error(`strategy6 lifecycle failed: ${res.status}`)
    return res.json().catch(() => ({ lifecycle: [] }))
  }

  async function getStrategy6Candidate(taskId, code) {
    const res = await fetch(`${API_BASE}/strategy6/tasks/${encodeURIComponent(taskId)}/candidates/${encodeURIComponent(code)}`)
    if (!res.ok) return null
    return res.json()
  }

  async function downloadStrategy6Report(taskId) {
    const res = await fetch(`${API_BASE}/strategy6/tasks/${encodeURIComponent(taskId)}/report.xlsx`)
    if (!res.ok) throw new Error('strategy6 report export failed')
    return res.blob()
  }

  // Strategy2 Backtest API
  async function startStrategy2Backtest(payload) {
    const res = await fetch(`${API_BASE}/strategy2/backtests`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }
  async function getStrategy2BacktestStatus() {
    const res = await fetch(`${API_BASE}/strategy2/backtests/status`)
    return res.json().catch(() => ({ running: false, stats: {} }))
  }
  async function getStrategy2BacktestTasks(params = null) {
    const qs = params ? params.toString() : ''
    const res = await fetch(`${API_BASE}/strategy2/backtests${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ tasks: [] }))
  }
  async function getStrategy2BacktestTask(taskId) {
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}`)
    return res.json().catch(() => null)
  }
  async function getStrategy2BacktestOpportunities(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const url = `${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/opportunities${qs ? '?' + qs : ''}`
    const res = await fetch(url)
    return res.json().catch(() => ({ opportunities: [], total: 0 }))
  }
  async function getStrategy2BacktestInsufficientStocks(taskId) {
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/insufficient-stocks`)
    return res.json().catch(() => ({ stocks: [], total: 0 }))
  }
  async function getStrategy2BacktestStockHistory(taskId, code) {
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/stocks/${encodeURIComponent(code)}`)
    return res.json().catch(() => ({ opportunities: [], total: 0 }))
  }
  async function getStrategy2BacktestStocks(taskId, status = '') {
    const qs = status ? `?status=${encodeURIComponent(status)}` : ''
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/stocks${qs}`)
    return res.json().catch(() => ({ stocks: [], total: 0 }))
  }
  async function strategy2BacktestAction(taskId, action) {
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/${action}`, { method: 'POST' })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }
  async function previewStrategy2BacktestExperiment(payload) {
    const res = await fetch(`${API_BASE}/strategy2/backtests/experiments/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }
  async function getStrategy2BacktestComparison(taskId, baselineTaskId) {
    const qs = new URLSearchParams({ baselineTaskId }).toString()
    const res = await fetch(`${API_BASE}/strategy2/backtests/${encodeURIComponent(taskId)}/comparison?${qs}`)
    return res.json().catch(() => ({ comparable: false, reasons: ['request_failed'] }))
  }

  // Strategy1 Backtest API
  async function startStrategy1Backtest(payload) {
    const res = await fetch(`${API_BASE}/strategy1/backtests`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }
  async function getStrategy1BacktestStatus() {
    const res = await fetch(`${API_BASE}/strategy1/backtests/status`)
    return res.json().catch(() => ({ running: false, stats: {} }))
  }
  async function getStrategy1BacktestTasks(params = null) {
    const qs = params ? params.toString() : ''
    const res = await fetch(`${API_BASE}/strategy1/backtests${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ tasks: [], total: 0 }))
  }
  async function getStrategy1BacktestTask(taskId) {
    const res = await fetch(`${API_BASE}/strategy1/backtests/${encodeURIComponent(taskId)}`)
    return res.json().catch(() => null)
  }
  async function getStrategy1BacktestOpportunities(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/strategy1/backtests/${encodeURIComponent(taskId)}/opportunities${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ opportunities: [], total: 0 }))
  }
  async function getStrategy1BacktestSignals(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/strategy1/backtests/${encodeURIComponent(taskId)}/signals${qs ? '?' + qs : ''}`)
    return res.json().catch(() => ({ signals: [], total: 0 }))
  }
  async function getStrategy1BacktestStocks(taskId, status = '') {
    const qs = status ? `?status=${encodeURIComponent(status)}` : ''
    const res = await fetch(`${API_BASE}/strategy1/backtests/${encodeURIComponent(taskId)}/stocks${qs}`)
    return res.json().catch(() => ({ stocks: [], total: 0 }))
  }
  async function previewStrategy1BacktestExperiment(payload) {
    const res = await fetch(`${API_BASE}/strategy1/backtests/experiments/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const body = await res.json().catch(() => ({}))
    return { ...body, ok: res.ok, statusCode: res.status }
  }
  async function getStrategy1BacktestComparison(taskId, baselineTaskId) {
    const qs = new URLSearchParams({ baselineTaskId }).toString()
    const res = await fetch(`${API_BASE}/strategy1/backtests/${encodeURIComponent(taskId)}/comparison?${qs}`)
    return res.json().catch(() => ({ comparable: false, reasons: ['request_failed'] }))
  }
  const resumeStrategy2Backtest = taskId => strategy2BacktestAction(taskId, 'resume')
  const cancelStrategy2Backtest = taskId => strategy2BacktestAction(taskId, 'cancel')
  const retryFailedStrategy2Backtest = taskId => strategy2BacktestAction(taskId, 'retry-failed')

  return {
    startScan, getScanStatus, getCandidates, getCandidate, getScanTasks,
    getSchedulerLogs, getKlineHistory, analyzeCleanK, getKlineHealth, refreshKlineData, refreshKlineHealth,
    startTickFlowFullRefresh, getTickFlowFullRefreshStatus, checkTickFlowFreshness,
    getTaskStocks, retryFailedStocks, reEvaluateTask, getConfig, updateConfig,
    runCupHandleBacktest,
    startStrategy2Scan, getStrategy2ScanStatus, getStrategy2Tasks,
    retryStrategy2FailedStocks, reEvaluateStrategy2Task,
    getStrategy2Candidates, getStrategy2Candidate,
    startStrategy3Scan, getStrategy3ScanStatus, getStrategy3Tasks,
    retryStrategy3FailedStocks, reEvaluateStrategy3Task,
    getStrategy3Candidates, getStrategy3Candidate,
    startStrategy4Scan, getStrategy4ScanStatus, getStrategy4Tasks,
    getStrategy4Topics, getStrategy4Leaders, getStrategy4Candidates,
    getStrategy4Candidate, getStrategy4TrackedTopics, getStrategy4TrackedLeaders,
    getStrategy4TrackingEvents,
    startStrategy5Scan, getStrategy5ScanStatus, getStrategy5Tasks,
    getStrategy5Candidates, getStrategy5Candidate,
    startStrategy6Scan, getStrategy6ScanStatus, getStrategy6Tasks,
    getStrategy6Candidates, getStrategy6MarketSnapshot, getStrategy6Lifecycle, getStrategy6Candidate, downloadStrategy6Report,
    startStrategy2Backtest, getStrategy2BacktestStatus,
    getStrategy2BacktestTasks, getStrategy2BacktestTask,
    getStrategy2BacktestOpportunities, getStrategy2BacktestInsufficientStocks,
    getStrategy2BacktestStockHistory, getStrategy2BacktestStocks,
    previewStrategy2BacktestExperiment, getStrategy2BacktestComparison,
    resumeStrategy2Backtest, cancelStrategy2Backtest, retryFailedStrategy2Backtest,
    startStrategy1Backtest, getStrategy1BacktestStatus,
    getStrategy1BacktestTasks, getStrategy1BacktestTask,
    getStrategy1BacktestOpportunities, getStrategy1BacktestSignals,
    getStrategy1BacktestStocks, previewStrategy1BacktestExperiment,
    getStrategy1BacktestComparison,
  }
}
