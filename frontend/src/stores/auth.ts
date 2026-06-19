import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/lib/api'

// 模块级守卫：避免 Vite HMR 重新求值本模块时重复注册 window 事件监听
let unauthorizedListenerInstalled = false

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<{ id: number; username: string; is_admin?: boolean; is_disabled?: boolean } | null>(null)

  const setToken = (t: string) => {
    token.value = t
    localStorage.setItem('token', t)
  }

  const clearToken = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  const login = async (username: string, password: string) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    const res = await api.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    setToken(res.data.access_token)
    await fetchMe()
    return res.data
  }

  const register = async (username: string, password: string, invite_code: string) => {
    const res = await api.post('/auth/register', { username, password, invite_code })
    return res.data
  }

  const fetchMe = async () => {
    if (!token.value) return
    const res = await api.get('/auth/me')
    user.value = res.data
  }

  const logout = () => {
    clearToken()
  }

  // 监听 api 模块派发的 401 事件，幂等地清理本地登录态
  // 必须做幂等守卫：Vite HMR 重新求值本模块时 setup 会再次执行，
  // 不加守卫会导致同一事件绑定多个 listener，401 一次触发多次清理
  if (typeof window !== 'undefined' && !unauthorizedListenerInstalled) {
    window.addEventListener('auth:unauthorized', () => {
      if (token.value) {
        clearToken()
      }
    })
    unauthorizedListenerInstalled = true
  }

  // HMR 自清理：模块热替换时重置守卫并清理 listener，
  // 避免旧 store 实例的回调继续监听新 store 触发的同类事件
  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      unauthorizedListenerInstalled = false
      // 注意：此处无法拿到具体的 handler 引用，需配合守卫防止重复注册
    })
  }

  return { token, user, login, register, logout, fetchMe }
})
