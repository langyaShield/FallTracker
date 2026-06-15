<script setup lang="ts">
/**
 * T1-2: 站内通知中心
 *
 * 顶部铃铛 + 下拉面板：
 * - 红点显示未读数
 * - 下拉面板显示最近 20 条，点击跳转
 * - 全部已读 / 全部清空
 * - 30s 轮询未读数
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'

interface NotificationItem {
  id: number
  type: string
  title: string
  body: string | null
  link: string | null
  is_read: boolean
  created_at: string
}

const router = useRouter()
const unreadCount = ref(0)
const items = ref<NotificationItem[]>([])
const loading = ref(false)
const panelOpen = ref(false)
const total = ref(0)

let pollTimer: ReturnType<typeof setInterval> | null = null

const badgeValue = computed(() => (unreadCount.value > 99 ? '99+' : String(unreadCount.value)))
const hasUnread = computed(() => unreadCount.value > 0)

async function fetchUnreadCount() {
  try {
    const res = await api.get('/notifications/unread-count')
    unreadCount.value = res.data.unread_count || 0
  } catch {
    // 静默失败，不影响其他功能
  }
}

async function fetchList() {
  loading.value = true
  try {
    const res = await api.get('/notifications', { params: { limit: 20 } })
    items.value = res.data.items || []
    unreadCount.value = res.data.unread_count || 0
    total.value = res.data.total || 0
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取通知失败'))
  } finally {
    loading.value = false
  }
}

async function markAllRead() {
  try {
    await api.post('/notifications/mark-read', {})
    unreadCount.value = 0
    items.value = items.value.map((n) => ({ ...n, is_read: true }))
    ElMessage.success('已全部标记为已读')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '操作失败'))
  }
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('确认清空所有通知？此操作不可恢复。', '清空通知', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  // 逐条删除（接口未提供批量删除，简单实现）
  try {
    for (const n of items.value) {
      await api.delete(`/notifications/${n.id}`)
    }
    items.value = []
    unreadCount.value = 0
    total.value = 0
    ElMessage.success('已清空')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '清空失败'))
  }
}

async function handleItemClick(n: NotificationItem) {
  // 单击标记已读 + 跳转
  if (!n.is_read) {
    try {
      await api.post('/notifications/mark-read', { ids: [n.id] })
      n.is_read = true
      unreadCount.value = Math.max(0, unreadCount.value - 1)
    } catch {
      // 忽略
    }
  }
  panelOpen.value = false
  if (n.link) {
    router.push(n.link)
  }
}

function handleVisibleChange(open: boolean) {
  if (open && items.value.length === 0) {
    fetchList()
  }
}

onMounted(() => {
  fetchUnreadCount()
  // 30s 轮询
  pollTimer = setInterval(fetchUnreadCount, 30_000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <el-popover
    :width="380"
    placement="bottom-end"
    trigger="click"
    v-model:visible="panelOpen"
    @show="handleVisibleChange(true)"
  >
    <template #reference>
      <el-badge :value="badgeValue" :hidden="!hasUnread" :max="99" class="notif-badge">
        <el-button text circle size="large" class="notif-bell">
          <el-icon :size="20"><Bell /></el-icon>
        </el-button>
      </el-badge>
    </template>

    <div class="notif-panel">
      <div class="notif-header">
        <span class="notif-title">
          通知
          <span v-if="total > 0" class="notif-meta">共 {{ total }} 条</span>
        </span>
        <div class="notif-actions">
          <el-button
            text
            size="small"
            :disabled="!hasUnread"
            @click="markAllRead"
          >全部已读</el-button>
          <el-button
            text
            size="small"
            :disabled="items.length === 0"
            @click="clearAll"
          >清空</el-button>
        </div>
      </div>

      <div v-loading="loading" class="notif-list">
        <el-empty v-if="!loading && items.length === 0" description="暂无通知" :image-size="80" />
        <div
          v-for="n in items"
          :key="n.id"
          class="notif-item"
          :class="{ unread: !n.is_read }"
          @click="handleItemClick(n)"
        >
          <div class="notif-item-title">{{ n.title }}</div>
          <div v-if="n.body" class="notif-item-body">{{ n.body }}</div>
          <div class="notif-item-time">{{ new Date(n.created_at).toLocaleString('zh-CN') }}</div>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.notif-badge {
  display: inline-flex;
  align-items: center;
}

.notif-bell {
  color: #cbd5e1;
  transition: color 0.2s;
}

.notif-bell:hover {
  color: #f59e0b;
}

.notif-panel {
  max-height: 480px;
  display: flex;
  flex-direction: column;
}

.notif-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 4px 12px;
  border-bottom: 1px solid #f1f5f9;
}

.notif-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e3a5f;
}

.notif-meta {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 400;
  margin-left: 8px;
}

.notif-actions {
  display: flex;
  gap: 4px;
}

.notif-list {
  margin-top: 8px;
  max-height: 360px;
  overflow-y: auto;
}

.notif-item {
  padding: 12px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid #f1f5f9;
}

.notif-item:hover {
  background: #f8fafc;
}

.notif-item.unread {
  background: #fffbeb;
}

.notif-item.unread::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  background: #f59e0b;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: middle;
}

.notif-item-title {
  font-size: 14px;
  font-weight: 500;
  color: #1e293b;
  margin-bottom: 4px;
}

.notif-item-body {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin-bottom: 4px;
  word-break: break-word;
}

.notif-item-time {
  font-size: 11px;
  color: #94a3b8;
}
</style>
