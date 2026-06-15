/** 格式化为 "X月X日 HH:mm" 格式 */
export function formatDateTime(s: string): string {
  if (!s) return '-'
  const d = new Date(s)
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 格式化为 "YYYY-MM-DD" 格式 */
export function formatDate(s: string): string {
  if (!s) return '-'
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 格式化为 "M/D HH:mm" 简短格式 */
export function formatShortDateTime(s: string): string {
  if (!s) return '-'
  const d = new Date(s)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 使用浏览器本地化时间格式（zh-CN），如 "2026/6/15 14:30:00" */
export function formatLocaleDateTime(s: string | null | undefined): string {
  if (!s) return '-'
  const d = new Date(s)
  if (isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN', { hour12: false })
}
