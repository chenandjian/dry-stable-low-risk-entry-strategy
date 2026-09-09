export function toTradingViewSymbol(code) {
  const value = String(code || '').trim()
  if (!/^\d{6}$/.test(value)) return null
  if (/^(4|8|92)/.test(value)) return `BSE:${value}`
  if (/^(0|1|2|3)/.test(value)) return `SZSE:${value}`
  if (/^(5|6|9)/.test(value)) return `SSE:${value}`
  return null
}

export function buildTradingViewWatchlist(rows) {
  const symbols = (rows || [])
    .map(row => toTradingViewSymbol(row?.code))
    .filter(Boolean)
  return [...new Set(symbols)].join(',')
}

export function downloadTradingViewWatchlist({ filename, rows }) {
  const content = buildTradingViewWatchlist(rows)
  if (!content) return false
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
  return true
}
