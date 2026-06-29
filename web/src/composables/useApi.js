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
    getSchedulerLogs, getKlineHistory, getKlineHealth,
    getTaskStocks, retryFailedStocks, reEvaluateTask, getConfig, updateConfig,
    runCupHandleBacktest,
    startStrategy2Scan, getStrategy2ScanStatus, getStrategy2Tasks,
    retryStrategy2FailedStocks, reEvaluateStrategy2Task,
    getStrategy2Candidates, getStrategy2Candidate,
    startStrategy3Scan, getStrategy3ScanStatus, getStrategy3Tasks,
    retryStrategy3FailedStocks, reEvaluateStrategy3Task,
    getStrategy3Candidates, getStrategy3Candidate,
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
