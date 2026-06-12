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

  async function getTaskStocks(taskId, params = {}) {
    const qs = new URLSearchParams(params).toString()
    const url = `${API_BASE}/scan/tasks/${taskId}/stocks${qs ? '?' + qs : ''}`
    const res = await fetch(url)
    const body = await res.json()
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
  async function getStrategy2BacktestTasks() {
    const res = await fetch(`${API_BASE}/strategy2/backtests`)
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

  return {
    startScan, getScanStatus, getCandidates, getCandidate, getScanTasks,
    getTaskStocks, retryFailedStocks, reEvaluateTask, getConfig, updateConfig,
    runCupHandleBacktest,
    startStrategy2Scan, getStrategy2ScanStatus, getStrategy2Tasks,
    retryStrategy2FailedStocks, reEvaluateStrategy2Task,
    getStrategy2Candidates, getStrategy2Candidate,
    startStrategy2Backtest, getStrategy2BacktestStatus,
    getStrategy2BacktestTasks, getStrategy2BacktestTask,
    getStrategy2BacktestOpportunities, getStrategy2BacktestInsufficientStocks,
    getStrategy2BacktestStockHistory,
  }
}
