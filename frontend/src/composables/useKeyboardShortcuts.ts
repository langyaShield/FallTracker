import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

interface ShortcutDef {
  key: string
  ctrl?: boolean
  meta?: boolean
  label: string
  handler: () => void
}

/**
 * 全局键盘快捷键 composable
 *
 * - Ctrl+K / Cmd+K：聚焦当前页面的搜索输入
 * - N：在投递大盘页面时打开新增投递对话框
 * - Escape：关闭所有打开的 el-dialog / el-drawer
 * - ? 按钮：hover 显示快捷键列表
 */
export function useKeyboardShortcuts() {
  const router = useRouter()
  const route = useRoute()
  const showHints = ref(false)

  const shortcuts = ref<ShortcutDef[]>([])

  function isInputElement(): boolean {
    const el = document.activeElement
    if (!el) return false
    const tag = el.tagName.toLowerCase()
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true
    if ((el as HTMLElement).isContentEditable) return true
    return false
  }

  function focusSearchInput() {
    // Try to find the search input on the current page
    const selectors = [
      '.filter-toolbar .el-input__inner',
      '.search-input .el-input__inner',
      '.page-header .el-input__inner',
      '.resumes-page .el-input__inner',
    ]
    for (const sel of selectors) {
      const input = document.querySelector<HTMLInputElement>(sel)
      if (input) {
        input.focus()
        input.select()
        return
      }
    }
  }

  function openNewDelivery() {
    // Only on dashboard page; trigger the "新增投递" button
    if (route.path !== '/dashboard') return
    const btn = document.querySelector<HTMLButtonElement>('.dashboard-page .header-right .el-button--primary')
    if (btn) btn.click()
  }

  function closeDialogs() {
    // Close all visible el-dialog overlays
    document.querySelectorAll<HTMLElement>('.el-overlay').forEach(overlay => {
      if (overlay.style.display !== 'none') {
        // Click the overlay to trigger dialog close (el-dialog has close-on-click-modal)
        // Better approach: find the close button
        const closeBtn = overlay.querySelector<HTMLButtonElement>('.el-dialog__headerbtn')
        if (closeBtn) closeBtn.click()
      }
    })
    // Also close drawers
    document.querySelectorAll<HTMLElement>('.el-drawer__headerbtn').forEach(btn => {
      btn.click()
    })
  }

  function handleKeydown(e: KeyboardEvent) {
    const isInput = isInputElement()

    // Escape always works (close dialogs)
    if (e.key === 'Escape') {
      closeDialogs()
      return
    }

    // Ctrl+K / Cmd+K: focus search (works even in inputs)
    if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      focusSearchInput()
      return
    }

    // Single-key shortcuts: only when NOT in an input field
    if (isInput) return

    if (e.key === 'n' || e.key === 'N') {
      e.preventDefault()
      openNewDelivery()
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeydown)

    shortcuts.value = [
      { key: 'Ctrl+K', label: '聚焦搜索', handler: focusSearchInput },
      { key: 'N', label: '新增投递（大盘页）', handler: openNewDelivery },
      { key: 'Esc', label: '关闭对话框', handler: closeDialogs },
    ]
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
  })

  return { shortcuts, showHints }
}
