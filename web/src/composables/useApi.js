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
    return res.json()
  }

  async function retryFailedStocks(taskId) {
    const res = await fetch(`${API_BASE}/scan/tasks/${taskId}/retry-failed`, { method: 'POST' })
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

  return {
    startScan, getScanStatus, getCandidates, getCandidate, getScanTasks,
    getTaskStocks, retryFailedStocks, getConfig, updateConfig,
    runCupHandleBacktest,
  }
}
