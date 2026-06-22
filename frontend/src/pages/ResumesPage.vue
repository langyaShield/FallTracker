<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Document, View, Delete, Edit, Search, Download,
  RefreshRight, Check, Close, Sort
} from '@element-plus/icons-vue'
import api from '@/lib/api'
import { formatDate } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

interface Resume {
  id: number
  name: string
  file_path: string
  file_size: number
  file_type: string
  ocr_text?: string | null
  ocr_status: string
  ocr_progress: number
  created_at: string
}

const resumes = ref<Resume[]>([])
const total = ref(0)
const loading = ref(false)

// 搜索 & 筛选 & 排序
const searchQuery = ref('')
const filterOcrStatus = ref('')
const sortBy = ref('created_at')
const sortOrder = ref('desc')
let searchTimer: ReturnType<typeof setTimeout> | null = null

// 上传对话框
const uploadDialog = ref(false)
const resumeName = ref('')
const fileList = ref<any[]>([])

// 编辑对话框（重命名 + 文件替换）
const editDialog = ref(false)
const editingResume = ref<Partial<Resume>>({})
const editFileList = ref<any[]>([])

// 预览
const previewUrl = ref('')
const previewDialog = ref(false)

// OCR 文本查看
const ocrDialog = ref(false)
const ocrText = ref('')
const ocrLoading = ref(false)

// 批量选择
const selectedIds = ref<number[]>([])
const selectMode = ref(false)

// OCR 轮询
let pollTimer: ReturnType<typeof setInterval> | null = null

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(pollOcrStatus, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const pollOcrStatus = async () => {
  const processing = resumes.value.filter(r => r.ocr_status === 'processing' || r.ocr_status === 'pending')
  if (processing.length === 0) {
    stopPolling()
    return
  }
  try {
    const res = await api.get('/resumes')
    const updated: Resume[] = res.data?.items || []
    for (const r of resumes.value) {
      const u = updated.find((u: Resume) => u.id === r.id)
      if (u) {
        r.ocr_status = u.ocr_status
        r.ocr_progress = u.ocr_progress
        r.ocr_text = u.ocr_text
      }
    }
  } catch {
    // ignore
  }
}

const fetchResumes = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {
      sort_by: sortBy.value,
      sort_order: sortOrder.value,
    }
    if (filterOcrStatus.value) {
      params.ocr_status = filterOcrStatus.value
    }
    const res = await api.get('/resumes', { params })
    resumes.value = res.data?.items || []
    total.value = res.data?.total || 0
    if (resumes.value.some(r => r.ocr_status === 'processing' || r.ocr_status === 'pending')) {
      startPolling()
    }
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取简历失败'))
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  clearTimeout(searchTimer!)
  searchTimer = setTimeout(async () => {
    if (!searchQuery.value.trim()) {
      fetchResumes()
      return
    }
    try {
      const res = await api.get('/resumes/search', {
        params: { q: searchQuery.value }
      })
      resumes.value = res.data?.items || []
      total.value = res.data?.total || 0
    } catch {
      ElMessage.error('搜索失败')
    }
  }, 300)
}

const clearSearch = () => {
  searchQuery.value = ''
  fetchResumes()
}

const handleSortChange = () => {
  fetchResumes()
}

const handleFilterChange = () => {
  fetchResumes()
}

// ─── 上传 ───

const handleUpload = async () => {
  if (!fileList.value.length || !resumeName.value) {
    ElMessage.warning('请填写名称并选择文件')
    return
  }
  const form = new FormData()
  form.append('file', fileList.value[0].raw)
  form.append('name', resumeName.value)
  try {
    await api.post('/resumes', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('上传成功，OCR正在后台处理中...')
    uploadDialog.value = false
    fileList.value = []
    resumeName.value = ''
    fetchResumes()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '上传失败'))
  }
}

// ─── 编辑（重命名 + 文件替换） ───

const openEdit = (resume: Resume) => {
  editingResume.value = { ...resume }
  editFileList.value = []
  editDialog.value = true
}

const saveEdit = async () => {
  if (!editingResume.value.name) {
    ElMessage.warning('名称不能为空')
    return
  }
  const form = new FormData()
  form.append('name', editingResume.value.name!)
  if (editFileList.value.length > 0) {
    form.append('file', editFileList.value[0].raw)
  }
  try {
    await api.put(`/resumes/${editingResume.value.id}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(editFileList.value.length > 0 ? '更新成功，文件已替换，OCR重新处理中' : '重命名成功')
    editDialog.value = false
    editFileList.value = []
    fetchResumes()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '更新失败'))
  }
}

// ─── 预览 ───

const previewResume = async (id: number) => {
  try {
    const res = await api.get(`/resumes/${id}/preview`, {
      responseType: 'blob',
    })
    const blob = new Blob([res.data], { type: 'application/pdf' })
    previewUrl.value = URL.createObjectURL(blob)
    previewDialog.value = true
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '预览失败'))
  }
}

const closePreview = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

// ─── 下载 ───

const downloadResume = async (resume: Resume) => {
  try {
    const res = await api.get(`/resumes/${resume.id}/download`, {
      responseType: 'blob',
    })
    const ext = resume.file_type || '.pdf'
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${resume.name}${ext}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '下载失败'))
  }
}

// ─── 删除（带确认） ───

const deleteResume = async (resume: Resume) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除简历「${resume.name}」吗？此操作不可恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await api.delete(`/resumes/${resume.id}`)
    ElMessage.success('删除成功')
    fetchResumes()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(extractErrorMessage(e, '删除失败'))
    }
  }
}

// ─── 批量删除 ───

const toggleSelectMode = () => {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selectedIds.value = []
  }
}

const toggleSelect = (id: number) => {
  const idx = selectedIds.value.indexOf(id)
  if (idx >= 0) {
    selectedIds.value.splice(idx, 1)
  } else {
    selectedIds.value.push(id)
  }
}

const isSelected = (id: number) => selectedIds.value.includes(id)

const selectAll = () => {
  if (selectedIds.value.length === resumes.value.length) {
    selectedIds.value = []
  } else {
    selectedIds.value = resumes.value.map(r => r.id)
  }
}

const batchDelete = async () => {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先选择要删除的简历')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要删除选中的 ${selectedIds.value.length} 份简历吗？此操作不可恢复。`,
      '批量删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    await api.post('/resumes/batch-delete', { ids: selectedIds.value })
    ElMessage.success(`成功删除 ${selectedIds.value.length} 份简历`)
    selectedIds.value = []
    selectMode.value = false
    fetchResumes()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(extractErrorMessage(e, '批量删除失败'))
    }
  }
}

// ─── 重新OCR ───

const reOcr = async (resume: Resume) => {
  try {
    await ElMessageBox.confirm(
      `确定要重新对「${resume.name}」进行OCR识别吗？`,
      '重新OCR',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'info' }
    )
    await api.post(`/resumes/${resume.id}/re-ocr`)
    ElMessage.success('已重新触发OCR')
    fetchResumes()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(extractErrorMessage(e, '重新OCR失败'))
    }
  }
}

// ─── OCR 文本查看 ───

const viewOcrText = async (resume: Resume) => {
  if (resume.ocr_status !== 'done') {
    ElMessage.warning('OCR尚未完成，请稍候')
    return
  }
  ocrLoading.value = true
  ocrDialog.value = true
  try {
    const res = await api.get(`/resumes/${resume.id}`)
    ocrText.value = res.data.ocr_text || '暂无OCR文本'
  } catch {
    ocrText.value = '获取OCR文本失败'
  } finally {
    ocrLoading.value = false
  }
}

// ─── 工具函数 ───

const ocrStatusLabel = (status: string) => {
  switch (status) {
    case 'pending': return '等待处理'
    case 'processing': return '处理中'
    case 'done': return '已完成'
    case 'failed': return '处理失败'
    default: return status
  }
}

const ocrStatusType = (status: string) => {
  switch (status) {
    case 'pending': return 'info'
    case 'processing': return 'warning'
    case 'done': return 'success'
    case 'failed': return 'danger'
    default: return 'info'
  }
}

const formatFileSize = (bytes: number) => {
  if (!bytes) return '未知'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const fileTypeIcon = (type: string) => {
  if (!type) return '📄'
  if (type === '.pdf') return '📕'
  if (type === '.docx') return '📘'
  return '🖼️'
}

onMounted(fetchResumes)
onUnmounted(() => {
  stopPolling()
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <div class="resumes-page">
    <PageHeader title="简历管理">
      <el-input
        v-model="searchQuery"
        placeholder="搜索名称或内容..."
        clearable
        :prefix-icon="Search"
        @input="handleSearch"
        @clear="clearSearch"
        style="width: 240px; margin-right: 12px"
      />
      <el-select
        v-model="filterOcrStatus"
        placeholder="OCR状态"
        clearable
        style="width: 130px; margin-right: 12px"
        @change="handleFilterChange"
      >
        <el-option label="等待处理" value="pending" />
        <el-option label="处理中" value="processing" />
        <el-option label="已完成" value="done" />
        <el-option label="处理失败" value="failed" />
      </el-select>
      <el-select
        v-model="sortBy"
        style="width: 120px; margin-right: 8px"
        @change="handleSortChange"
      >
        <el-option label="按时间" value="created_at" />
        <el-option label="按名称" value="name" />
      </el-select>
      <el-select
        v-model="sortOrder"
        style="width: 100px; margin-right: 12px"
        @change="handleSortChange"
      >
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
      <el-button
        :type="selectMode ? 'warning' : 'default'"
        @click="toggleSelectMode"
      >{{ selectMode ? '取消选择' : '批量操作' }}</el-button>
      <el-button
        v-if="selectMode"
        type="danger"
        :disabled="selectedIds.length === 0"
        @click="batchDelete"
      >删除选中 ({{ selectedIds.length }})</el-button>
      <el-button
        v-if="selectMode"
        @click="selectAll"
      >{{ selectedIds.length === resumes.length ? '取消全选' : '全选' }}</el-button>
      <el-button type="primary" :icon="Plus" @click="uploadDialog = true">上传简历</el-button>
    </PageHeader>

    <div class="list-summary">
      <span>共 {{ total }} 份简历</span>
    </div>

    <div v-loading="loading" class="resume-list">
      <el-card
        v-for="resume in resumes"
        :key="resume.id"
        class="resume-card"
        :class="{ 'card-selected': isSelected(resume.id) }"
        @click="selectMode && toggleSelect(resume.id)"
      >
        <!-- 选择模式下显示勾选框 -->
        <div v-if="selectMode" class="select-check" @click.stop="toggleSelect(resume.id)">
          <el-icon v-if="isSelected(resume.id)" :size="20" color="#409eff"><Check /></el-icon>
          <el-icon v-else :size="20" color="#c0c4cc"><Close /></el-icon>
        </div>

        <div class="resume-info">
          <span class="file-type-icon">{{ fileTypeIcon(resume.file_type) }}</span>
          <div class="resume-meta">
            <div class="resume-name">{{ resume.name }}</div>
            <div class="resume-sub">
              <span>{{ formatDate(resume.created_at) }}</span>
              <span class="file-size">{{ formatFileSize(resume.file_size) }}</span>
              <span class="file-ext">{{ resume.file_type?.replace('.', '').toUpperCase() }}</span>
            </div>
          </div>
        </div>

        <div class="ocr-status-area">
          <div class="ocr-status-row">
            <el-tag :type="ocrStatusType(resume.ocr_status)" size="small">
              {{ ocrStatusLabel(resume.ocr_status) }}
            </el-tag>
            <span v-if="resume.ocr_status === 'processing'" class="ocr-percent">{{ resume.ocr_progress }}%</span>
          </div>
          <el-progress
            v-if="resume.ocr_status === 'processing' || resume.ocr_status === 'pending'"
            :percentage="resume.ocr_progress"
            :stroke-width="6"
            :show-text="false"
            style="margin-top: 6px"
          />
        </div>

        <div v-if="resume.ocr_status === 'done' && resume.ocr_text" class="ocr-preview">
          {{ resume.ocr_text.slice(0, 150) }}{{ resume.ocr_text.length > 150 ? '...' : '' }}
        </div>

        <div class="resume-actions" @click.stop>
          <el-button type="primary" text :icon="View" @click="previewResume(resume.id)">预览</el-button>
          <el-button text :icon="Download" @click="downloadResume(resume)">下载</el-button>
          <el-button text :icon="Edit" @click="openEdit(resume)">编辑</el-button>
          <el-button
            v-if="resume.ocr_status === 'done' || resume.ocr_status === 'failed'"
            text
            :icon="RefreshRight"
            @click="reOcr(resume)"
          >重新OCR</el-button>
          <el-button
            v-if="resume.ocr_status === 'done'"
            text
            @click="viewOcrText(resume)"
          >OCR文本</el-button>
          <el-button type="danger" text :icon="Delete" @click="deleteResume(resume)">删除</el-button>
        </div>
      </el-card>
      <el-empty v-if="!loading && resumes.length === 0" description="暂无简历" />
    </div>

    <!-- 上传对话框 -->
    <el-dialog v-model="uploadDialog" title="上传简历" width="500px">
      <el-form label-width="80px">
        <el-form-item label="简历名称">
          <el-input v-model="resumeName" placeholder="如：后端开发-字节跳动" />
        </el-form-item>
        <el-form-item label="简历文件">
          <el-upload
            v-model:file-list="fileList"
            accept=".pdf,.png,.jpg,.jpeg,.bmp,.tiff,.docx"
            :auto-upload="false"
            :limit="1"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <div class="upload-tip">支持 PDF / 图片 / Word，单文件不超过 10MB</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框（重命名 + 文件替换） -->
    <el-dialog v-model="editDialog" title="编辑简历" width="500px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="editingResume.name" placeholder="简历名称" />
        </el-form-item>
        <el-form-item label="替换文件">
          <el-upload
            v-model:file-list="editFileList"
            accept=".pdf,.png,.jpg,.jpeg,.bmp,.tiff,.docx"
            :auto-upload="false"
            :limit="1"
          >
            <el-button type="primary">选择新文件</el-button>
            <template #tip>
              <div class="upload-tip">选择文件将替换原简历并重新OCR，不选则仅修改名称</div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 预览对话框 -->
    <el-dialog v-model="previewDialog" title="简历预览" width="80%" @close="closePreview">
      <iframe v-if="previewUrl" :src="previewUrl" class="pdf-preview" />
    </el-dialog>

    <!-- OCR文本查看对话框 -->
    <el-dialog v-model="ocrDialog" title="OCR识别文本" width="700px">
      <div v-loading="ocrLoading" class="ocr-text-content">
        <pre class="ocr-text">{{ ocrText }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.resumes-page {
  height: 100%;
}

.list-summary {
  font-size: 13px;
  color: #94a3b8;
  margin-bottom: 12px;
}

.resume-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.resume-card {
  transition: all 0.2s;
  cursor: default;
  position: relative;
}

.resume-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.card-selected {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.2);
}

.select-check {
  position: absolute;
  top: 12px;
  right: 12px;
  cursor: pointer;
  z-index: 1;
}

.resume-info {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.file-type-icon {
  font-size: 28px;
  line-height: 1;
}

.resume-meta {
  flex: 1;
  min-width: 0;
}

.resume-name {
  font-weight: 600;
  font-size: 15px;
  color: #1e3a5f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resume-sub {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
  display: flex;
  gap: 10px;
  align-items: center;
}

.file-size {
  color: #64748b;
}

.file-ext {
  background: #f1f5f9;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  color: #475569;
}

.ocr-status-area {
  margin-bottom: 12px;
}

.ocr-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ocr-percent {
  font-size: 12px;
  color: #f59e0b;
  font-weight: 600;
}

.ocr-preview {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
  padding: 8px;
  background: #f8fafc;
  border-radius: 6px;
  margin-bottom: 12px;
  max-height: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.resume-actions {
  display: flex;
  justify-content: flex-end;
  gap: 2px;
  flex-wrap: wrap;
}

.pdf-preview {
  width: 100%;
  height: 70vh;
  border: none;
}

.ocr-text-content {
  max-height: 60vh;
  overflow-y: auto;
}

.ocr-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  margin: 0;
  padding: 16px;
  background: #f8fafc;
  border-radius: 8px;
}

.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
