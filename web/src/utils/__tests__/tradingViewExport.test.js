import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  buildTradingViewWatchlist,
  downloadTradingViewWatchlist,
  toTradingViewSymbol,
} from '../tradingViewExport.js'

describe('tradingViewExport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('maps A-share codes to TradingView exchange-prefixed symbols', () => {
    expect(toTradingViewSymbol('603976')).toBe('SSE:603976')
    expect(toTradingViewSymbol('688001')).toBe('SSE:688001')
    expect(toTradingViewSymbol('000001')).toBe('SZSE:000001')
    expect(toTradingViewSymbol('300604')).toBe('SZSE:300604')
    expect(toTradingViewSymbol('920001')).toBe('BSE:920001')
    expect(toTradingViewSymbol('830001')).toBe('BSE:830001')
  })

  it('builds a comma-separated, deduplicated TradingView watchlist', () => {
    expect(buildTradingViewWatchlist([
      { code: '603976' }, { code: '300604' }, { code: '603976' },
    ])).toBe('SSE:603976,SZSE:300604')
  })

  it('downloads a plain text watchlist', async () => {
    const originalUrl = globalThis.URL
    const createObjectURL = vi.fn(() => 'blob:tradingview')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...originalUrl, createObjectURL, revokeObjectURL })
    const click = vi.fn()
    let anchor = null
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(tag => {
      const element = originalCreateElement(tag)
      if (tag === 'a') {
        anchor = element
        vi.spyOn(element, 'click').mockImplementation(click)
      }
      return element
    })

    downloadTradingViewWatchlist({
      filename: 'strategy6-filtered.txt',
      rows: [{ code: '603976' }, { code: '300604' }],
    })

    expect(click).toHaveBeenCalledTimes(1)
    expect(anchor.download).toBe('strategy6-filtered.txt')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:tradingview')
    expect(await createObjectURL.mock.calls[0][0].text()).toBe('SSE:603976,SZSE:300604')
  })
})
