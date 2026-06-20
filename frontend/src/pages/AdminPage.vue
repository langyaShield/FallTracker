<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Lock, Unlock, Plus, CopyDocument, Delete } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

interface AdminUser {
  id: number
  username: string
  is_admin: boolean
  is_disabled: boolean
  created_at: string | null
  delivery_count: number
  resume_count: number
}

interface InviteCodeItem {
  id: number
  code: string
  is_used: boolean
  used_by_username: string | null
  expires_at: string | null
  created_at: string | null
}

const loading = ref(false)
const users = ref<AdminUser[]>([])
const searchQuery = ref('')

const filteredUsers = computed(() => {
  if (!searchQuery.value) return users.value
  const q = searchQuery.value.toLowerCase()
  return users.value.filter(u => u.username.toLowerCase().includes(q))
})

const fetchUsers = async () => {
  loading.value = true
  try {
    const res = await api.get('/admin/users')
    users.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取用户列表失败'))
  } finally {
    loading.value = false
  }
}

const disableUser = async (user: AdminUser) => {
  try {
    await ElMessageBox.confirm(
      `确定要禁用用户 "${user.username}" 吗？禁用后该用户将无法登录和使用系统。`,
      '禁用用户',
      { confirmButtonText: '确定禁用', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.post(`/admin/users/${user.id}/disable`)
    ElMessage.success(`已禁用用户 ${user.username}`)
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '禁用失败'))
  }
}

const enableUser = async (user: AdminUser) => {
  try {
    await api.post(`/admin/users/${user.id}/enable`)
    ElMessage.success(`已启用用户 ${user.username}`)
    fetchUsers()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '启用失败'))
  }
}

const formatDate = (dateStr: string | null) => {
  if (!dateStr) return '-'
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

const totalUsers = computed(() => users.value.length)
const activeUsers = computed(() => users.value.filter(u => !u.is_disabled).length)
const disabledUsers = computed(() => users.value.filter(u => u.is_disabled).length)

// ─── 邀请码管理 ───
const inviteCodes = ref<InviteCodeItem[]>([])
const inviteLoading = ref(false)
const generateCount = ref(5)
const generateExpires = ref<number | null>(null)
const generating = ref(false)

const expiresOptions = [
  { label: '永不过期', value: null },
  { label: '1小时', value: 1 },
  { label: '24小时', value: 24 },
  { label: '7天', value: 168 },
  { label: '30天', value: 720 },
]

const fetchInviteCodes = async () => {
  inviteLoading.value = true
  try {
    const res = await api.get('/admin/invite-codes')
    inviteCodes.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取邀请码列表失败'))
  } finally {
    inviteLoading.value = false
  }
}

const generateInviteCodes = async () => {
  generating.value = true
  try {
    const payload: { count: number; expires_hours?: number } = { count: generateCount.value }
    if (generateExpires.value !== null) {
      payload.expires_hours = generateExpires.value
    }
    const res = await api.post('/admin/invite-codes', payload)
    ElMessage.success(`已生成 ${res.data.length} 个邀请码`)
    fetchInviteCodes()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '生成邀请码失败'))
  } finally {
    generating.value = false
  }
}

const copyCode = async (code: string) => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(code)
    } else {
      // Fallback for non-HTTPS contexts
      const textarea = document.createElement('textarea')
      textarea.value = code
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    ElMessage.success('已复制邀请码')
  } catch {
    ElMessage.error('复制失败')
  }
}

const unusedCount = computed(() => inviteCodes.value.filter(c => !c.is_used).length)

const cleaningUp = ref(false)
const cleanupExpiredCodes = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要删除所有已过期的邀请码吗？此操作不可撤销。',
      '清理过期邀请码',
      { confirmButtonText: '确定清理', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  cleaningUp.value = true
  try {
    const res = await api.delete('/admin/invite-codes/expired')
    if (res.data.deleted > 0) {
      ElMessage.success(`已删除 ${res.data.deleted} 个过期邀请码`)
    } else {
      ElMessage.info('没有过期的邀请码需要清理')
    }
    fetchInviteCodes()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '清理失败'))
  } finally {
    cleaningUp.value = false
  }
}

onMounted(() => {
  fetchUsers()
  fetchInviteCodes()
})
</script>

<template>
  <div class="admin-page" v-loading="loading">
    <PageHeader title="用户管理" />

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card">
        <span class="stat-value">{{ totalUsers }}</span>
        <span class="stat-label">总用户数</span>
      </div>
      <div class="stat-card stat-active">
        <span class="stat-value">{{ activeUsers }}</span>
        <span class="stat-label">正常用户</span>
      </div>
      <div class="stat-card stat-disabled">
        <span class="stat-value">{{ disabledUsers }}</span>
        <span class="stat-label">已禁用</span>
      </div>
      <div class="stat-card stat-invite">
        <span class="stat-value">{{ unusedCount }}</span>
        <span class="stat-label">可用邀请码</span>
      </div>
    </div>

    <!-- 用户列表 -->
    <el-card class="table-card">
      <template #header>
        <span class="card-title">用户列表</span>
      </template>
      <div class="table-header">
        <el-input
          v-model="searchQuery"
          placeholder="搜索用户名"
          :prefix-icon="Search"
          clearable
          style="max-width: 300px"
        />
      </div>

      <el-table :data="filteredUsers" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="username" label="用户名" min-width="120">
          <template #default="{ row }">
            <span>{{ row.username }}</span>
            <el-tag v-if="row.is_admin" type="warning" size="small" style="margin-left: 6px">管理员</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_disabled ? 'danger' : 'success'" size="small">
              {{ row.is_disabled ? '已禁用' : '正常' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="投递数" width="90" align="center">
          <template #default="{ row }">
            <span class="count-num">{{ row.delivery_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="简历数" width="90" align="center">
          <template #default="{ row }">
            <span class="count-num">{{ row.resume_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="注册时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_disabled"
              type="danger"
              size="small"
              text
              :icon="Lock"
              :disabled="row.is_admin"
              @click="disableUser(row)"
            >
              禁用
            </el-button>
            <el-button
              v-else
              type="success"
              size="small"
              text
              :icon="Unlock"
              @click="enableUser(row)"
            >
              启用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 邀请码管理 -->
    <el-card class="table-card" style="margin-top: 20px">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">邀请码管理</span>
          <el-button
            type="warning"
            size="small"
            :icon="Delete"
            :loading="cleaningUp"
            @click="cleanupExpiredCodes"
          >
            清理过期邀请码
          </el-button>
        </div>
      </template>

      <!-- 生成邀请码 -->
      <div class="invite-generate">
        <div class="generate-row">
          <span class="generate-label">生成数量</span>
          <el-input-number v-model="generateCount" :min="1" :max="50" size="small" style="width: 120px" />
        </div>
        <div class="generate-row">
          <span class="generate-label">有效时长</span>
          <el-select v-model="generateExpires" size="small" style="width: 140px">
            <el-option
              v-for="opt in expiresOptions"
              :key="String(opt.value)"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <el-button type="primary" :icon="Plus" :loading="generating" @click="generateInviteCodes">
          生成邀请码
        </el-button>
      </div>

      <!-- 邀请码列表 -->
      <el-table :data="inviteCodes" stripe style="width: 100%; margin-top: 16px" v-loading="inviteLoading">
        <el-table-column label="邀请码" min-width="140">
          <template #default="{ row }">
            <code class="invite-code">{{ row.code }}</code>
            <el-button
              size="small"
              text
              :icon="CopyDocument"
              @click="copyCode(row.code)"
              style="margin-left: 4px"
            />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_used ? 'info' : 'success'" size="small">
              {{ row.is_used ? '已使用' : '未使用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="使用者" width="120">
          <template #default="{ row }">
            {{ row.used_by_username || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="过期时间" width="180">
          <template #default="{ row }">
            {{ row.expires_at ? formatDate(row.expires_at) : '永不过期' }}
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.admin-page {
  height: 100%;
}

.stats-row {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid #e2e8f0;
  min-width: 140px;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
}

.stat-label {
  font-size: 13px;
  color: #94a3b8;
}

.stat-active .stat-value {
  color: #16a34a;
}

.stat-disabled .stat-value {
  color: #dc2626;
}

.stat-invite .stat-value {
  color: #2563eb;
}

.table-card {
  max-width: 900px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
  color: #1e3a5f;
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.count-num {
  font-weight: 600;
  color: #1e293b;
}

/* ─── 邀请码管理 ─── */
.invite-generate {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.generate-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.generate-label {
  font-size: 14px;
  color: #64748b;
  white-space: nowrap;
}

.invite-code {
  font-family: 'Courier New', monospace;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 1px;
}
</style>
