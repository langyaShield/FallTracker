import { AxiosError } from 'axios'

/** 提取后端 FastAPI 抛出的 detail 错误信息，否则回退到默认消息 */
export function extractErrorMessage(e: unknown, fallback = '操作失败'): string {
  if (e instanceof AxiosError) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      // Pydantic 校验错误：detail 是 [{loc, msg, type}, ...]
      const first = detail[0]
      if (first && typeof first === 'object' && 'msg' in first) {
        return String((first as { msg: unknown }).msg)
      }
    }
    if (e.message) return e.message
  }
  if (e instanceof Error) return e.message
  return fallback
}
