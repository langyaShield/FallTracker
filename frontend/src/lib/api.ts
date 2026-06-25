import axios from 'axios'
import { PUBLIC_PATHS } from './constants'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const api = axios.create({
  baseURL: API_BASE,
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

// 响应拦截器：401 自动清除登录态并跳转登录页
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      // 通过自定义事件通知应用层，避免在 api 模块中耦合 router/store
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
      // 兜底直接跳转（避免事件未被监听时无法退出）
      if (!(PUBLIC_PATHS as readonly string[]).includes(window.location.pathname)) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export default api
