/**
 * 格式化时长（秒 → 可读字符串）
 */
export const formatDuration = (seconds: number) => {
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  return `${(seconds / 3600).toFixed(1)}小时`
}

/**
 * 数字补零
 */
export const pad = (n: number) => String(n).padStart(2, '0')

/**
 * 格式化日期时间：YYYY-MM-DD HH:mm:ss
 */
export const formatDateTime = (date: Date | string | number): string => {
  const d = date instanceof Date ? date : new Date(date)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

/**
 * 格式化短日期时间：YYYY/MM/DD HH:mm
 */
export const formatDateTimeShort = (date: Date | string | number): string => {
  const d = date instanceof Date ? date : new Date(date)
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 格式化日期：YYYY-MM-DD
 */
export const formatDate = (date: Date | string | number): string => {
  const d = date instanceof Date ? date : new Date(date)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
