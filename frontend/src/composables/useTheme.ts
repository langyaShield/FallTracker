import { ref, watch, computed } from 'vue'

type Theme = 'light' | 'dark'

const STORAGE_KEY = 'theme'

function getPreferredTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(t: Theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.remove('light', 'dark')
  root.classList.add(t)
}

// 模块级单例：所有 useTheme() 调用共享同一份主题状态，避免每个组件各自初始化导致的闪烁
const theme = ref<Theme>(getPreferredTheme())

// 初始化时立即同步到 DOM（避免首屏闪烁）
applyTheme(theme.value)

// 仅在主题值变化时同步到 DOM 与 localStorage，初始化时不会重复触发
watch(theme, (t) => {
  applyTheme(t)
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, t)
  }
})

export function useTheme() {
  const toggleTheme = () => {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  return {
    theme,
    toggleTheme,
    isDark: computed(() => theme.value === 'dark'),
  }
}
