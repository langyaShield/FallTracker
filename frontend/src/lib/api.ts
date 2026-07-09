import axios, { type AxiosRequestConfig, type AxiosError } from 'axios'
import { PUBLIC_PATHS } from './constants'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  paramsSerializer: {
    serialize: (params) => {
      // Support repeated keys for List[str] params (e.g. status=pending&status=applied)
      const parts: string[] = []
      for (const [key, value] of Object.entries(params)) {
        if (value == null) continue
        const values = Array.isArray(value) ? value : [value]
        for (const v of values) {
          parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(v)}`)
        }
      }
      return parts.join('&')
    },
  },
})

// 请求拦截器：自动附加 token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Token 刷新：并发 401 时只刷新一次，其余请求排队等待新 token
let isRefreshing = false
let failedQueue: Array<{ resolve: (token: string) => void; reject: (e: unknown) => void }> = []

const redirectToLogin = () => {
  localStorage.removeItem('token')
  // 通过自定义事件通知应用层，避免在 api 模块中耦合 router/store
  window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  // 兜底直接跳转（避免事件未被监听时无法退出）
  if (!(PUBLIC_PATHS as readonly string[]).includes(window.location.pathname)) {
    window.location.href = '/login'
  }
}

// 响应拦截器：401 时尝试刷新 token 并重试原请求，刷新失败再退出登录
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as (AxiosRequestConfig & { _retry?: boolean }) | undefined
    // auth 请求自身的 401（如登录失败、refresh 失效）不触发刷新，避免死循环
    const isAuthRequest = originalRequest?.url?.includes('/auth/')

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthRequest) {
      // 已有刷新在进行中：排队等待
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${token}` }
              resolve(api(originalRequest))
            },
            reject,
          })
        })
      }

      originalRequest._retry = true
      isRefreshing = true
      try {
        // 用独立 axios 调用 refresh，避免再次触发本拦截器
        const res = await axios.post(
          `${API_BASE}/auth/refresh`,
          null,
          { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } },
        )
        const newToken = res.data.access_token
        localStorage.setItem('token', newToken)
        window.dispatchEvent(new CustomEvent('auth:token-refreshed', { detail: newToken }))
        // 唤醒排队请求
        failedQueue.forEach(({ resolve }) => resolve(newToken))
        failedQueue = []
        // 重试原请求
        originalRequest.headers = { ...originalRequest.headers, Authorization: `Bearer ${newToken}` }
        return api(originalRequest)
      } catch {
        failedQueue.forEach(({ reject }) => reject(error))
        failedQueue = []
        redirectToLogin()
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    // 非可刷新的 401（auth 请求失败或已重试过）：清登录态跳转
    if (error.response?.status === 401) {
      redirectToLogin()
    }
    return Promise.reject(error)
  }
)

export default api
