const CODE_COLUMN_ALIASES = new Set(['商品代码', '股票代码', '代码', 'symbol', 'ticker'])

function normalizeHeader(value) {
  return String(value ?? '').replace(/^\uFEFF/, '').trim().toLowerCase()
}

function normalizeCode(value) {
  const raw = String(value ?? '').trim().toUpperCase()
  if (/^\d{6}$/.test(raw)) return raw
  const exchangePrefixed = raw.match(/^(?:SSE|SZSE|BSE):(\d{6})$/)
  if (exchangePrefixed) return exchangePrefixed[1]
  const compactPrefixed = raw.match(/^(?:SH|SZ|BJ)(\d{6})$/)
  return compactPrefixed ? compactPrefixed[1] : ''
}

function parseCsvRows(input) {
  const rows = []
  let row = []
  let field = ''
  let quoted = false

  for (let index = 0; index < input.length; index += 1) {
    const char = input[index]
    if (char === '"') {
      if (quoted && input[index + 1] === '"') {
        field += '"'
        index += 1
      } else {
        quoted = !quoted
      }
    } else if (char === ',' && !quoted) {
      row.push(field)
      field = ''
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && input[index + 1] === '\n') index += 1
      row.push(field)
      if (row.some(value => value.trim())) rows.push(row)
      row = []
      field = ''
    } else {
      field += char
    }
  }

  row.push(field)
  if (row.some(value => value.trim())) rows.push(row)
  return rows
}

function unique(values) {
  return [...new Set(values)]
}

export function parseStockCodeInput(input) {
  const text = String(input ?? '')
  const csvRows = parseCsvRows(text)
  const header = csvRows[0] || []
  const codeColumnIndex = header.findIndex(value => CODE_COLUMN_ALIASES.has(normalizeHeader(value)))

  if (codeColumnIndex >= 0) {
    const rawCodes = csvRows.slice(1).map(row => row[codeColumnIndex]?.trim()).filter(Boolean)
    return {
      codes: unique(rawCodes.map(normalizeCode).filter(Boolean)),
      invalidCodes: unique(rawCodes.filter(value => !normalizeCode(value))),
      format: 'csv',
      sourceColumn: header[codeColumnIndex].replace(/^\uFEFF/, '').trim(),
    }
  }

  const rawCodes = text.split(/[\s,，;；]+/).map(value => value.trim()).filter(Boolean)
  return {
    codes: unique(rawCodes.map(normalizeCode).filter(Boolean)),
    invalidCodes: unique(rawCodes.filter(value => !normalizeCode(value))),
    format: 'plain',
    sourceColumn: '',
  }
}
