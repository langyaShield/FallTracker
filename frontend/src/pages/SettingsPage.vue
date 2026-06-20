<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Upload, Refresh, Delete, Check } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

const loading = ref(false)
const saving = ref(false)

const llmApiKey = ref('')
const llmApiBase = ref('https://api.deepseek.com/v1')
const llmModel = ref('deepseek-chat')

const keyMasked = ref(true)

const fetchSettings = async () => {
  loading.value = true
  try {
    const res = await api.get('/settings')
    llmApiKey.value = res.data.llm_api_key || ''
    llmApiBase.value = res.data.llm_api_base || 'https://api.deepseek.com/v1'
    llmModel.value = res.data.llm_model || 'deepseek-chat'
    keyMasked.value = !!res.data.llm_api_key && res.data.llm_api_key.includes('*')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取设置失败'))
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    const payload: Record<string, string> = {
      llm_api_base: llmApiBase.value,
      llm_model: llmModel.value,
    }
    if (!keyMasked.value && llmApiKey.value) {
      payload.llm_api_key = llmApiKey.value
    }
    await api.put('/settings', payload)
    ElMessage.success('保存成功')
    fetchSettings()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

const onKeyInput = () => {
  keyMasked.value = false
}

// ─── 数据备份（本地） ───
const exporting = ref(false)
const importing = ref(false)
const importResult = ref<Record<string, number> | null>(null)

const exportData = async () => {
  exporting.value = true
  try {
    const res = await api.get('/backup/export', { responseType: 'blob' })
    const blob = new Blob([res.data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const disposition = res.headers?.['content-disposition']
    let filename = `falltracker_backup_${new Date().toISOString().slice(0, 10)}.json`
    if (disposition) {
      const match = disposition.match(/filename="?([^"]+)"?/)
      if (match) filename = match[1]
    }
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('数据导出成功')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '导出失败'))
  } finally {
    exporting.value = false
  }
}

const handleImportFile = async (uploadFile: any) => {
  const file = uploadFile.raw || uploadFile
  if (!file) return

  try {
    await ElMessageBox.confirm(
      '导入将先删除当前所有数据，再从备份文件恢复。此操作不可撤销，确定继续？',
      '确认导入',
      { confirmButtonText: '确定导入', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  importing.value = true
  importResult.value = null
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await api.post('/backup/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    importResult.value = res.data.imported
    ElMessage.success('数据导入成功')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '导入失败'))
  } finally {
    importing.value = false
  }
}

const importLabelMap: Record<string, string> = {
  user_settings: '用户设置',
  crawler_configs: '爬虫配置',
  crawler_results: '爬虫结果',
  resumes: '简历',
  deliveries: '投递记录',
  interview_events: '面试事件',
  reviews: '面试复盘',
  notifications: '通知',
}

// ─── 腾讯云 COS 配置 ───
const cosSaving = ref(false)
const cosSecretId = ref('')
const cosSecretKey = ref('')
const cosBucket = ref('')
const cosRegion = ref('')
const cosPath = ref('backups/')
const cosSecretIdMasked = ref(true)
const cosSecretKeyMasked = ref(true)
const cosConfigured = ref(false)
const cosCollapse = ref<string[]>([])
const cosAutoBackupHours = ref(0)

const COS_REGIONS = [
  { label: '北京', value: 'ap-beijing' },
  { label: '上海', value: 'ap-shanghai' },
  { label: '广州', value: 'ap-guangzhou' },
  { label: '成都', value: 'ap-chengdu' },
  { label: '重庆', value: 'ap-chongqing' },
  { label: '南京', value: 'ap-nanjing' },
  { label: '香港', value: 'ap-hongkong' },
  { label: '新加坡', value: 'ap-singapore' },
  { label: '东京', value: 'ap-tokyo' },
  { label: '首尔', value: 'ap-seoul' },
  { label: '孟买', value: 'ap-mumbai' },
  { label: '曼谷', value: 'ap-bangkok' },
  { label: '硅谷', value: 'na-siliconvalley' },
  { label: '弗吉尼亚', value: 'na-ashburn' },
  { label: '多伦多', value: 'na-toronto' },
  { label: '法兰克福', value: 'eu-frankfurt' },
  { label: '莫斯科', value: 'eu-moscow' },
]

const fetchCosSettings = async () => {
  try {
    const res = await api.get('/settings/cos')
    cosSecretId.value = res.data.cos_secret_id || ''
    cosSecretKey.value = res.data.cos_secret_key || ''
    cosBucket.value = res.data.cos_bucket || ''
    cosRegion.value = res.data.cos_region || ''
    cosPath.value = res.data.cos_path || 'backups/'
    cosSecretIdMasked.value = !!res.data.cos_secret_id && res.data.cos_secret_id.includes('*')
    cosSecretKeyMasked.value = !!res.data.cos_secret_key && res.data.cos_secret_key.includes('*')
    cosConfigured.value = !!(res.data.cos_bucket && res.data.cos_region)
    cosAutoBackupHours.value = res.data.cos_auto_backup_hours || 0
  } catch {
    // 可能未配置，忽略
  }
}

const saveCosSettings = async () => {
  cosSaving.value = true
  try {
    const payload: Record<string, string | number> = {
      cos_bucket: cosBucket.value,
      cos_region: cosRegion.value,
      cos_path: cosPath.value || 'backups/',
      cos_auto_backup_hours: cosAutoBackupHours.value,
    }
    if (!cosSecretIdMasked.value && cosSecretId.value) {
      payload.cos_secret_id = cosSecretId.value
    }
    if (!cosSecretKeyMasked.value && cosSecretKey.value) {
      payload.cos_secret_key = cosSecretKey.value
    }
    await api.put('/settings/cos', payload)
    ElMessage.success('COS 配置保存成功')
    fetchCosSettings()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存 COS 配置失败'))
  } finally {
    cosSaving.value = false
  }
}

// ─── 云端备份操作 ───
const cosUploading = ref(false)
const cosListing = ref(false)
const cosRestoring = ref(false)
const cosBackupList = ref<Array<{ key: string; size: number; last_modified: string }>>([])
const selectedCosFile = ref('')
const cosImportResult = ref<Record<string, number> | null>(null)

const uploadToCos = async () => {
  cosUploading.value = true
  try {
    const res = await api.post('/backup/upload-to-cos')
    ElMessage.success(`上传成功: ${res.data.file_key} (${(res.data.size / 1024).toFixed(1)} KB)`)
    // 刷新列表
    listCosBackups()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '上传到云端失败'))
  } finally {
    cosUploading.value = false
  }
}

const listCosBackups = async () => {
  cosListing.value = true
  try {
    const res = await api.get('/backup/cos-list')
    cosBackupList.value = res.data || []
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取云端备份列表失败'))
  } finally {
    cosListing.value = false
  }
}

const restoreFromCos = async () => {
  if (!selectedCosFile.value) {
    ElMessage.warning('请先选择要恢复的备份文件')
    return
  }

  try {
    await ElMessageBox.confirm(
      '恢复将先删除当前所有数据，再从云端备份恢复。此操作不可撤销，确定继续？',
      '确认恢复',
      { confirmButtonText: '确定恢复', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  cosRestoring.value = true
  cosImportResult.value = null
  try {
    const formData = new FormData()
    formData.append('file_key', selectedCosFile.value)
    const res = await api.post('/backup/restore-from-cos', formData)
    cosImportResult.value = res.data.imported
    ElMessage.success('从云端恢复数据成功')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '从云端恢复失败'))
  } finally {
    cosRestoring.value = false
  }
}

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const formatDate = (dateStr: string) => {
  try {
    return new Date(dateStr).toLocaleString('zh-CN')
  } catch {
    return dateStr
  }
}

const getBackupType = (key: string) => {
  if (key.includes('_auto_')) return 'auto'
  if (key.includes('_manual_')) return 'manual'
  return 'unknown'
}

const getBackupTypeLabel = (key: string) => {
  const type = getBackupType(key)
  if (type === 'auto') return '自动备份'
  if (type === 'manual') return '手动备份'
  return '备份'
}

// ─── COS 文件管理 ───
const cosDeleting = ref(false)
const cosRenaming = ref(false)
const renameDialogVisible = ref(false)
const renameTarget = ref('')
const renameNewName = ref('')

const deleteCosBackup = async (fileKey: string) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除备份文件 ${fileKey} 吗？此操作不可撤销。`,
      '确认删除',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  cosDeleting.value = true
  try {
    const formData = new FormData()
    formData.append('file_key', fileKey)
    await api.post('/backup/cos-delete', formData)
    ElMessage.success('备份已删除')
    if (selectedCosFile.value === fileKey) {
      selectedCosFile.value = ''
    }
    listCosBackups()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '删除失败'))
  } finally {
    cosDeleting.value = false
  }
}

const openRenameDialog = (fileKey: string) => {
  renameTarget.value = fileKey
  // 提取文件名（去掉路径前缀）
  const parts = fileKey.split('/')
  const filename = parts[parts.length - 1]
  renameNewName.value = filename.replace('.json', '')
  renameDialogVisible.value = true
}

const confirmRename = async () => {
  if (!renameNewName.value.trim()) {
    ElMessage.warning('请输入新文件名')
    return
  }

  cosRenaming.value = true
  try {
    const formData = new FormData()
    formData.append('file_key', renameTarget.value)
    formData.append('new_name', renameNewName.value.trim())
    await api.post('/backup/cos-rename', formData)
    ElMessage.success('备份已重命名')
    renameDialogVisible.value = false
    listCosBackups()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '重命名失败'))
  } finally {
    cosRenaming.value = false
  }
}

onMounted(() => {
  fetchSettings()
  fetchCosSettings().then(() => {
    if (cosConfigured.value) {
      listCosBackups()
    }
  })
})
</script>

<template>
  <div class="settings-page" v-loading="loading">
    <PageHeader title="设置" />

    <el-card class="settings-card">
      <template #header>
        <span class="card-title">LLM API 配置</span>
      </template>
      <p class="card-desc">配置用于面试复盘AI总结的大语言模型API。支持 OpenAI 兼容接口（DeepSeek、OpenAI、智谱、通义千问等）。</p>

      <el-form label-width="120px" style="max-width: 600px; margin-top: 20px">
        <el-form-item label="API Key">
          <el-input
            v-model="llmApiKey"
            type="password"
            show-password
            placeholder="输入你的 API Key"
            @input="onKeyInput"
          />
        </el-form-item>

        <el-form-item label="API Base URL">
          <el-input v-model="llmApiBase" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>

        <el-form-item label="模型名称">
          <el-input v-model="llmModel" placeholder="deepseek-chat" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveSettings">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据备份 -->
    <el-card class="settings-card" style="margin-top: 20px">
      <template #header>
        <span class="card-title">数据备份</span>
      </template>
      <p class="card-desc">导出当前所有数据为 JSON 文件，可用于数据备份或迁移到其他设备。导入时可选择合并或覆盖。</p>

      <div class="backup-section">
        <div class="backup-row">
          <div class="backup-info">
            <span class="backup-label">本地导出</span>
            <span class="backup-hint">将所有投递、面试、简历、爬虫等数据导出为 JSON 文件下载到本地</span>
          </div>
          <el-button type="primary" :icon="Download" :loading="exporting" @click="exportData">
            导出备份
          </el-button>
        </div>

        <el-divider />

        <div class="backup-row">
          <div class="backup-info">
            <span class="backup-label">本地导入</span>
            <span class="backup-hint">从本地 JSON 备份文件恢复数据（将覆盖当前所有数据）</span>
          </div>
          <div class="import-controls">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".json"
              :on-change="handleImportFile"
            >
              <el-button type="success" :icon="Upload" :loading="importing">
                选择文件并导入
              </el-button>
            </el-upload>
          </div>
        </div>

        <!-- 导入结果 -->
        <div v-if="importResult" class="import-result">
          <h4>导入结果</h4>
          <div class="result-grid">
            <div v-for="(count, key) in importResult" :key="key" class="result-item">
              <span class="result-count">{{ count }}</span>
              <span class="result-label">{{ importLabelMap[key] || key }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 腾讯云 COS 云端备份 -->
    <el-card class="settings-card" style="margin-top: 20px">
      <template #header>
        <span class="card-title">云端备份（腾讯云 COS）</span>
      </template>
      <p class="card-desc">将数据备份到腾讯云对象存储，实现云端保存和跨设备恢复。需先配置 COS 参数。</p>

      <!-- COS 配置 -->
      <el-collapse v-model="cosCollapse" class="cos-collapse">
        <el-collapse-item title="COS 参数配置" name="config">
          <el-form label-width="130px" style="max-width: 600px">
            <el-form-item label="SecretId">
              <el-input
                v-model="cosSecretId"
                type="password"
                show-password
                placeholder="腾讯云 API SecretId"
                @input="cosSecretIdMasked = false"
              />
            </el-form-item>

            <el-form-item label="SecretKey">
              <el-input
                v-model="cosSecretKey"
                type="password"
                show-password
                placeholder="腾讯云 API SecretKey"
                @input="cosSecretKeyMasked = false"
              />
            </el-form-item>

            <el-form-item label="存储桶名称">
              <el-input v-model="cosBucket" placeholder="如 falltracker-1234567890" />
            </el-form-item>

            <el-form-item label="地域">
              <el-select v-model="cosRegion" placeholder="选择地域" filterable style="width: 100%">
                <el-option
                  v-for="r in COS_REGIONS"
                  :key="r.value"
                  :label="`${r.label} (${r.value})`"
                  :value="r.value"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="存储路径">
              <el-input v-model="cosPath" placeholder="backups/" />
            </el-form-item>

            <el-form-item label="自动备份">
              <el-select v-model="cosAutoBackupHours" placeholder="选择自动备份间隔" style="width: 100%">
                <el-option :value="0" label="关闭自动备份" />
                <el-option :value="1" label="每 1 小时" />
                <el-option :value="2" label="每 2 小时" />
                <el-option :value="4" label="每 4 小时" />
                <el-option :value="6" label="每 6 小时" />
                <el-option :value="12" label="每 12 小时" />
                <el-option :value="24" label="每 24 小时" />
                <el-option :value="48" label="每 48 小时" />
                <el-option :value="168" label="每 7 天" />
              </el-select>
              <div class="auto-backup-hint">
                开启后，系统将按设定间隔自动将数据备份到 COS，文件名标记为"自动备份"
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="cosSaving" @click="saveCosSettings">保存 COS 配置</el-button>
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>

      <!-- 云端操作 -->
      <div class="cloud-section">
        <div class="backup-row">
          <div class="backup-info">
            <span class="backup-label">上传到云端</span>
            <span class="backup-hint">将当前数据备份并上传到腾讯云 COS</span>
          </div>
          <el-button
            type="primary"
            :icon="Upload"
            :loading="cosUploading"
            :disabled="!cosConfigured"
            @click="uploadToCos"
          >
            上传备份
          </el-button>
        </div>

        <el-divider />

        <div class="backup-row">
          <div class="backup-info">
            <span class="backup-label">从云端恢复</span>
            <span class="backup-hint">从 COS 下载备份文件并恢复数据（将覆盖当前所有数据）</span>
          </div>
          <div class="import-controls">
            <el-button
              :icon="Refresh"
              :loading="cosListing"
              :disabled="!cosConfigured"
              @click="listCosBackups"
            >
              刷新列表
            </el-button>
          </div>
        </div>

        <div v-if="!cosConfigured" class="mode-hint" style="color: #f59e0b; background: #fffbeb; border-color: #fde68a;">
          请先在上方配置 COS 参数并保存，才能使用云端备份功能
        </div>

        <!-- 云端备份列表 -->
        <div v-if="cosBackupList.length > 0" class="cos-list">
          <el-table
            :data="cosBackupList"
            size="small"
            highlight-current-row
            :row-class-name="({ row }: any) => selectedCosFile === row.key ? 'selected-row' : ''"
            @current-change="(row: any) => selectedCosFile = row?.key || ''"
          >
            <el-table-column width="50" align="center">
              <template #default="{ row }">
                <el-icon v-if="selectedCosFile === row.key" color="#16a34a" :size="18">
                  <Check />
                </el-icon>
              </template>
            </el-table-column>
            <el-table-column label="文件名" prop="key" min-width="200" />
            <el-table-column label="类型" width="100">
              <template #default="{ row }">
                <el-tag
                  :type="getBackupType(row.key) === 'auto' ? 'warning' : 'success'"
                  size="small"
                >
                  {{ getBackupTypeLabel(row.key) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="100">
              <template #default="{ row }">{{ formatSize(row.size) }}</template>
            </el-table-column>
            <el-table-column label="修改时间" width="180">
              <template #default="{ row }">{{ formatDate(row.last_modified) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="140" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="openRenameDialog(row.key)">重命名</el-button>
                <el-button link type="danger" size="small" :loading="cosDeleting" @click="deleteCosBackup(row.key)">
                  <el-icon><Delete /></el-icon>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div style="margin-top: 12px; text-align: right;">
            <el-button
              type="success"
              :loading="cosRestoring"
              :disabled="!selectedCosFile"
              @click="restoreFromCos"
            >
              恢复选中的备份
            </el-button>
          </div>
        </div>

        <div v-else-if="cosConfigured && !cosListing" class="mode-hint">
          暂无云端备份，点击"刷新列表"查看或"上传备份"创建新备份
        </div>

        <!-- 云端恢复结果 -->
        <div v-if="cosImportResult" class="import-result">
          <h4>恢复结果</h4>
          <div class="result-grid">
            <div v-for="(count, key) in cosImportResult" :key="key" class="result-item">
              <span class="result-count">{{ count }}</span>
              <span class="result-label">{{ importLabelMap[key] || key }}</span>
            </div>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 重命名对话框 -->
    <el-dialog v-model="renameDialogVisible" title="重命名备份" width="400px">
      <el-form label-width="80px">
        <el-form-item label="新文件名">
          <el-input v-model="renameNewName" placeholder="输入新文件名（不含路径）">
            <template #append>.json</template>
          </el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="cosRenaming" @click="confirmRename">确认</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.settings-page {
  height: 100%;
}

.settings-card {
  max-width: 800px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
  color: #1e3a5f;
}

.card-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}

/* ─── 数据备份 ─── */
.backup-section {
  margin-top: 8px;
}

.backup-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}

.backup-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.backup-label {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}

.backup-hint {
  font-size: 12px;
  color: #94a3b8;
}

.import-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mode-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #94a3b8;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
}

.import-result {
  margin-top: 16px;
  padding: 16px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
}

.import-result h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: #166534;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.result-item {
  text-align: center;
  padding: 8px;
  background: #fff;
  border-radius: 6px;
  border: 1px solid #dcfce7;
}

.result-count {
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: #166534;
}

.result-label {
  display: block;
  font-size: 12px;
  color: #64748b;
  margin-top: 2px;
}

/* ─── COS 云端备份 ─── */
.cos-collapse {
  margin-bottom: 16px;
  border: none;
}

.cos-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  background: #f8fafc;
  padding: 0 12px;
  border-radius: 6px;
}

.cos-collapse :deep(.el-collapse-item__wrap) {
  border: none;
}

.cloud-section {
  margin-top: 8px;
}

.cos-list {
  margin-top: 12px;
}

.cos-list :deep(.selected-row) {
  background-color: #f0fdf4 !important;
}

.cos-list :deep(.selected-row td:first-child) {
  border-left: 3px solid #16a34a;
}

.auto-backup-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}
</style>
