const API_BASE = '/api'

export function useApi() {
  async function startScan() {
    const res = await fetch(`${API_BASE}/scan/start`)
    return res.json()
  }

  async function getScanStatus() {
    const res = await fetch(`${API_BASE}/scan/status`)
    return res.json()
  }

  async function getCandidates(params = {}) {
    const qs = new URLSearchParams(params).toString()
    const res = await fetch(`${API_BASE}/candidates?${qs}`)
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

  return { startScan, getScanStatus, getCandidates, getCandidate, getScanTasks }
}
