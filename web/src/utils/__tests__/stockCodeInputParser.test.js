import { describe, expect, it } from 'vitest'
import { parseStockCodeInput } from '../stockCodeInputParser.js'

describe('parseStockCodeInput', () => {
  it('keeps plain lists compatible and normalizes exchange-prefixed codes', () => {
    expect(parseStockCodeInput('601857\nSZSE:002384, sh600938；601857')).toEqual({
      codes: ['601857', '002384', '600938'],
      invalidCodes: [],
      format: 'plain',
      sourceColumn: '',
    })
  })

  it('extracts only the code column from a TradingView Chinese CSV export', () => {
    const input = [
      '商品代码,描述,价格,价格 - 货币,"价格变动 %, 1天","成交量, 1天"',
      '601857,中国石油,11.32,CNY,0.17,119202683',
      '601138,工业富联,65.24,CNY,0.75,76150565',
      '600938,中国海油,34.18,CNY,-0.61,39152090',
      '601857,中国石油,11.32,CNY,0.17,119202683',
    ].join('\n')

    expect(parseStockCodeInput(input)).toEqual({
      codes: ['601857', '601138', '600938'],
      invalidCodes: [],
      format: 'csv',
      sourceColumn: '商品代码',
    })
  })

  it('supports quoted CSV values, BOM, English headers, and reports invalid code cells', () => {
    const input = '\uFEFFSymbol,Description,Note\n"SSE:601857","中国石油","能源, 大盘"\nBAD,"无效",x\n"SZ002384","东山精密",x'

    expect(parseStockCodeInput(input)).toEqual({
      codes: ['601857', '002384'],
      invalidCodes: ['BAD'],
      format: 'csv',
      sourceColumn: 'Symbol',
    })
  })

  it('does not treat an ordinary comma-separated list as CSV without a known header', () => {
    expect(parseStockCodeInput('601857,ABC,002384')).toEqual({
      codes: ['601857', '002384'],
      invalidCodes: ['ABC'],
      format: 'plain',
      sourceColumn: '',
    })
  })
})
