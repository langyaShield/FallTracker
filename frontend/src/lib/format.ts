/** 将日期字符串解析为 Date，非法或空值返回 null */
function toDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

/** 格式化为 "X月X日 HH:mm" 格式 */
export function formatDateTime(s: string): string {
  const d = toDate(s)
  if (!d) return '-'
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 格式化为 "YYYY-MM-DD" 格式 */
export function formatDate(s: string): string {
  const d = toDate(s)
  if (!d) return '-'
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** 格式化为 "M/D HH:mm" 简短格式 */
export function formatShortDateTime(s: string): string {
  const d = toDate(s)
  if (!d) return '-'
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 使用浏览器本地化时间格式（zh-CN），如 "2026/6/15 14:30:00" */
export function formatLocaleDateTime(s: string | null | undefined): string {
  const d = toDate(s)
  if (!d) return '-'
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 根据截止时间计算紧急程度：过期 / 紧急(24h内) / 临近(48h内) / 正常 */
export function getDeadlineUrgency(deadline?: string | null): 'expired' | 'urgent' | 'warning' | 'normal' {
  if (!deadline) return 'normal'
  const diff = new Date(deadline).getTime() - Date.now()
  if (diff < 0) return 'expired'
  if (diff <= 24 * 60 * 60 * 1000) return 'urgent'
  if (diff <= 48 * 60 * 60 * 1000) return 'warning'
  return 'normal'
}

/** 格式化文件大小为可读字符串 */
export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes == null || bytes <= 0) return '未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 格式化日期字符串为中文格式，如 "2026/7/11 14:30:00" */
export function formatDateLocale(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return '-'
  }
}
