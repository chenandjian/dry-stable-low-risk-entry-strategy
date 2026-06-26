function csvCell(value) {
  if (value == null) return ''
  const text = String(value)
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

export function buildCsvContent({ columns, rows }) {
  const header = columns.map(col => csvCell(col.header)).join(',')
  const body = rows.map(row => columns.map(col => csvCell(col.value(row))).join(','))
  return '\ufeff' + [header, ...body].join('\n')
}

export function downloadCsv({ filename, columns, rows }) {
  const content = buildCsvContent({ columns, rows })
  const blob = new Blob([content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
