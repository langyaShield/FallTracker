import { shallowRef, computed, h, onUnmounted } from 'vue'
import { ElNotification, ElButton, ElMessage } from 'element-plus'

interface UndoDeleteOptions<T> {
  deleteFn: (item: T) => Promise<void>
  onSuccess?: () => void
  onError?: (item: T, error: unknown) => void
  duration?: number
  getId: (item: T) => string | number
  getName?: (item: T) => string
}

interface PendingItem<T> {
  item: T
  timer: number
  closeNotification: () => void
}

export function useUndoDelete<T>(options: UndoDeleteOptions<T>) {
  const pendingItems = shallowRef<Map<string | number, PendingItem<T>>>(new Map())
  const duration = options.duration ?? 2000

  const requestDelete = (item: T) => {
    const id = options.getId(item)
    if (pendingItems.value.has(id)) return

    const name = options.getName?.(item) ?? String(id)
    let cancelled = false

    const notification = ElNotification({
      title: '已移至待删除',
      message: h('div', { style: 'display:flex;align-items:center;gap:12px;flex-wrap:wrap' }, [
        h('span', null, `"${name}" 将在 ${duration / 1000} 秒后彻底删除`),
        h(ElButton, {
          size: 'small',
          type: 'primary',
          onClick: () => {
            cancelled = true
            cancelDelete(id)
          },
        }, () => '撤销'),
      ]),
      type: 'info',
      duration: duration,
      showClose: false,
      onClose: () => {
        if (!cancelled) {
          confirmDelete(id)
        }
      },
    })

    pendingItems.value.set(id, {
      item,
      timer: window.setTimeout(() => {
        if (!cancelled) {
          confirmDelete(id)
        }
      }, duration),
      closeNotification: () => notification.close(),
    })
  }

  const cancelDelete = (id: string | number) => {
    const pending = pendingItems.value.get(id)
    if (!pending) return
    window.clearTimeout(pending.timer)
    pending.closeNotification()
    pendingItems.value.delete(id)
  }

  const confirmDelete = async (id: string | number) => {
    const pending = pendingItems.value.get(id)
    if (!pending) return
    window.clearTimeout(pending.timer)
    pending.closeNotification()
    pendingItems.value.delete(id)
    try {
      await options.deleteFn(pending.item)
      options.onSuccess?.()
    } catch (e: unknown) {
      const name = options.getName?.(pending.item) ?? String(id)
      ElMessage.error(`删除 "${name}" 失败`)
      if (options.onError) {
        options.onError(pending.item, e)
      }
    }
  }

  // 组件卸载时清理所有待处理的定时器，防止内存泄漏和意外删除
  const cleanup = () => {
    for (const [id, pending] of pendingItems.value) {
      window.clearTimeout(pending.timer)
      pending.closeNotification()
    }
    pendingItems.value.clear()
  }

  onUnmounted(cleanup)

  const pendingIds = computed(() => new Set(pendingItems.value.keys()))

  return {
    pendingItems,
    pendingIds,
    requestDelete,
    cancelDelete,
    confirmDelete,
    cleanup,
  }
}
