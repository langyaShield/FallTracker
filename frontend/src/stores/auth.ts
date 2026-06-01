import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<{ id: number; username: string } | null>(null)

  const setToken = (t: string) => {
    token.value = t
    localStorage.setItem('token', t)
    axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
  }

  const clearToken = () => {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    delete axios.defaults.headers.common['Authorization']
  }

  const login = async (username: string, password: string) => {
    const form = new URLSearchParams()
    form.append('username', username)
    form.append('password', password)
    const res = await axios.post(`${API_BASE}/auth/login`, form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    setToken(res.data.access_token)
    await fetchMe()
    return res.data
  }

  const register = async (username: string, password: string) => {
    const res = await axios.post(`${API_BASE}/auth/register`, { username, password })
    return res.data
  }

  const fetchMe = async () => {
    if (!token.value) return
    const res = await axios.get(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token.value}` },
    })
    user.value = res.data
  }

  const logout = () => {
    clearToken()
  }

  if (token.value) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
    fetchMe()
  }

  return { token, user, login, register, logout, fetchMe }
})
