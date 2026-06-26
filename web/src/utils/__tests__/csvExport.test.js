import { describe, expect, it, vi, afterEach } from 'vitest'
import { buildCsvContent, downloadCsv } from '../csvExport.js'

describe('csvExport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('builds utf8 csv with escaped cells', () => {
    const csv = buildCsvContent({
      columns: [
        { header: '代码', value: row => row.code },
        { header: '名称', value: row => row.name },
        { header: '备注', value: row => row.note },
      ],
      rows: [
        { code: '000001', name: '平安银行', note: '强,候选' },
        { code: '000002', name: '万科"A"', note: '换行\n测试' },
      ],
    })

    expect(csv).toBe('\ufeff代码,名称,备注\n000001,平安银行,"强,候选"\n000002,"万科""A""","换行\n测试"')
  })

  it('downloads csv with the requested filename', async () => {
    const originalUrl = globalThis.URL
    const createObjectURL = vi.fn(() => 'blob:csv-url')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...originalUrl, createObjectURL, revokeObjectURL })

    const click = vi.fn()
    let anchor = null
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation(tag => {
      const el = originalCreateElement(tag)
      if (tag === 'a') {
        anchor = el
        vi.spyOn(el, 'click').mockImplementation(click)
      }
      return el
    })

    downloadCsv({
      filename: 'strategy-candidates.csv',
      columns: [{ header: '代码', value: row => row.code }],
      rows: [{ code: '000001' }],
    })

    expect(click).toHaveBeenCalled()
    expect(anchor.download).toBe('strategy-candidates.csv')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:csv-url')
    const blob = createObjectURL.mock.calls[0][0]
    expect(await blob.text()).toBe('代码\n000001')
  })
})
