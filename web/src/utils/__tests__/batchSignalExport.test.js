import { describe, expect, it } from 'vitest'
import { selectBatchSignalExportRows } from '../batchSignalExport.js'
import { buildTradingViewWatchlist } from '../tradingViewExport.js'

describe('batch signal union export', () => {
  it.each([
    { priceConvergence: { matched: true } },
    ...['S', 'A+', 'A'].map(grade => ({ emaCompression: { grade, status: 'NOT_CONFIRMED' } })),
    ...['STRONG', 'ULTRA'].map(status => ({ sellingExhaustion: { status } })),
    ...['S', 'A'].map(grade => ({ klineCollectionPatterns: [{ grade, matched: false }] })),
  ])('includes a stock matching just one selected group: %j', diagnostic => {
    const row = { code: '000001', ...diagnostic }
    expect(selectBatchSignalExportRows([row])).toEqual([row])
  })

  it('does not mistake unknown, forming, normal or lower grades for selected signals', () => {
    expect(selectBatchSignalExportRows([
      { code: '000001' },
      { code: '000002', priceConvergence: { matched: false, status: 'FORMING' } },
      { code: '000003', sellingExhaustion: { status: 'NORMAL', score: 100 } },
      { code: '000004', emaCompression: { grade: 'B', extreme: true } },
      { code: '000005', klineCollectionPatterns: [{ grade: 'B', matched: true }] },
    ])).toEqual([])
  })

  it('deduplicates across groups, preserves result order and produces TradingView symbols', () => {
    const rows = [
      { code: '603976', priceConvergence: { matched: true }, emaCompression: { grade: 'S' } },
      { code: '300604', sellingExhaustion: { status: 'STRONG' } },
      { code: '603976', klineCollectionPatterns: [{ grade: 'A' }] },
      { code: 'invalid', emaCompression: { grade: 'S' } },
      { klineCollectionPatterns: [{ grade: 'S' }] },
    ]
    const before = JSON.stringify(rows)
    const selected = selectBatchSignalExportRows(rows)
    expect(selected.map(row => row.code)).toEqual(['603976', '300604'])
    expect(buildTradingViewWatchlist(selected)).toBe('SSE:603976,SZSE:300604')
    expect(JSON.stringify(rows)).toBe(before)
    expect(selectBatchSignalExportRows()).toEqual([])
  })
})
