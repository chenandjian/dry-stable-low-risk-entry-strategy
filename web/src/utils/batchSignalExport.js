import { toTradingViewSymbol } from './tradingViewExport.js'

export function selectBatchSignalExportRows(rows = [], normalizeCode = toTradingViewSymbol) {
  const seen = new Set()
  return rows.filter(item => {
    const symbol = normalizeCode(item?.code)
    if (!symbol || seen.has(symbol)) return false
    const matched = item.priceConvergence?.matched === true
      || ['S', 'A+', 'A'].includes(item.emaCompression?.grade)
      || ['STRONG', 'ULTRA'].includes(item.sellingExhaustion?.status)
      || (Array.isArray(item.klineCollectionPatterns)
        && item.klineCollectionPatterns.some(pattern => ['S', 'A'].includes(pattern?.grade)))
    if (!matched) return false
    seen.add(symbol)
    return true
  })
}
