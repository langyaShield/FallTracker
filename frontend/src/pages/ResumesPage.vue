<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Document, View, Delete, Edit, Search } from '@element-plus/icons-vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

interface Resume {
  id: number
  name: string
  file_path: string
  ocr_text?: string | null
  ocr_status: string  // pending / processing / done / failed
  ocr_progress: number  // 0-100
  created_at: string
}

const resumes = ref<Resume[]>([])
const loading = ref(false)
const uploadDialog = ref(false)
const resumeName = ref('')
const fileList = ref<any[]>([])
const previewUrl = ref('')
const previewDialog = ref(false)

// Rename state
const renameDialog = ref(false)
const renamingResume = ref<Partial<Resume>>({})

// OCR text state
const ocrDialog = ref(false)
const ocrText = ref('')
const ocrLoading = ref(false)

// Search state
const searchQuery = ref('')
let searchTimer: any = null

// Progress polling
let pollTimer: any = null

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
    const ids = processing.map(r => r.id)
    const res = await axios.get(`${API_BASE}/resumes`)
    const updated: Resume[] = res.data || []
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
    const res = await axios.get(`${API_BASE}/resumes`)
    resumes.value = res.data || []
    // Start polling if any resume is still processing
    if (resumes.value.some(r => r.ocr_status === 'processing' || r.ocr_status === 'pending')) {
      startPolling()
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取简历失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(async () => {
    if (!searchQuery.value.trim()) {
      fetchResumes()
      return
    }
    try {
      const res = await axios.get(`${API_BASE}/resumes/search`, {
        params: { q: searchQuery.value }
      })
      resumes.value = res.data || []
    } catch (e: any) {
      ElMessage.error('搜索失败')
    }
  }, 300)
}

const clearSearch = () => {
  searchQuery.value = ''
  fetchResumes()
}

const handleUpload = async () => {
  if (!fileList.value.length || !resumeName.value) {
    ElMessage.warning('请填写名称并选择文件')
    return
  }
  const form = new FormData()
  form.append('file', fileList.value[0].raw)
  form.append('name', resumeName.value)
  try {
    await axios.post(`${API_BASE}/resumes`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('上传成功，OCR正在后台处理中...')
    uploadDialog.value = false
    fileList.value = []
    resumeName.value = ''
    fetchResumes()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  }
}

const previewResume = async (id: number) => {
  try {
    const res = await axios.get(`${API_BASE}/resumes/${id}/preview`, {
      responseType: 'blob',
    })
    const blob = new Blob([res.data], { type: 'application/pdf' })
    previewUrl.value = URL.createObjectURL(blob)
    previewDialog.value = true
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '预览失败')
  }
}

const closePreview = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
  }
}

const deleteResume = async (id: number) => {
  try {
    await axios.delete(`${API_BASE}/resumes/${id}`)
    ElMessage.success('删除成功')
    fetchResumes()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// Rename
const openRename = (resume: Resume) => {
  renamingResume.value = { ...resume }
  renameDialog.value = true
}

const saveRename = async () => {
  if (!renamingResume.value.name) return
  try {
    await axios.put(`${API_BASE}/resumes/${renamingResume.value.id}`, {
      name: renamingResume.value.name,
    })
    ElMessage.success('重命名成功')
    renameDialog.value = false
    fetchResumes()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '重命名失败')
  }
}

// OCR text view
const viewOcrText = async (resume: Resume) => {
  if (resume.ocr_status !== 'done') {
    ElMessage.warning('OCR尚未完成，请稍候')
    return
  }
  ocrLoading.value = true
  ocrDialog.value = true
  try {
    const res = await axios.get(`${API_BASE}/resumes/${resume.id}`)
    ocrText.value = res.data.ocr_text || '暂无OCR文本'
  } catch {
    ocrText.value = '获取OCR文本失败'
  } finally {
    ocrLoading.value = false
  }
}

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

const formatDate = (s: string) => {
  if (!s) return '-'
  const d = new Date(s)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

onMounted(fetchResumes)
onUnmounted(stopPolling)
</script>

<template>
  <div class="resumes-page">
    <div class="page-header">
      <h2>简历管理</h2>
      <div class="header-right">
        <el-input
          v-model="searchQuery"
          placeholder="搜索简历内容..."
          clearable
          :prefix-icon="Search"
          @input="handleSearch"
          @clear="clearSearch"
          style="width: 280px; margin-right: 12px"
        />
        <el-button type="primary" :icon="Plus" @click="uploadDialog = true">上传简历</el-button>
      </div>
    </div>

    <div v-loading="loading" class="resume-list">
      <el-card v-for="resume in resumes" :key="resume.id" class="resume-card">
        <div class="resume-info">
          <el-icon class="resume-icon" :size="40"><Document /></el-icon>
          <div class="resume-meta">
            <div class="resume-name">{{ resume.name }}</div>
            <div class="resume-date">{{ formatDate(resume.created_at) }}</div>
          </div>
        </div>

        <!-- OCR Status & Progress -->
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
            :status="resume.ocr_status === 'processing' ? undefined : undefined"
            :stroke-width="6"
            :show-text="false"
            style="margin-top: 6px"
          />
        </div>

        <!-- OCR text preview (only when done) -->
        <div v-if="resume.ocr_status === 'done' && resume.ocr_text" class="ocr-preview">
          {{ resume.ocr_text.slice(0, 150) }}{{ resume.ocr_text.length > 150 ? '...' : '' }}
        </div>

        <div class="resume-actions">
          <el-button type="primary" text :icon="View" @click="previewResume(resume.id)">预览</el-button>
          <el-button text :icon="Edit" @click="openRename(resume)">重命名</el-button>
          <el-button
            v-if="resume.ocr_status === 'done'"
            text
            @click="viewOcrText(resume)"
          >OCR文本</el-button>
          <el-button type="danger" text :icon="Delete" @click="deleteResume(resume.id)">删除</el-button>
        </div>
      </el-card>
      <el-empty v-if="resumes.length === 0" description="暂无简历" />
    </div>

    <el-dialog v-model="uploadDialog" title="上传简历" width="500px">
      <el-form label-width="80px">
        <el-form-item label="简历名称">
          <el-input v-model="resumeName" placeholder="如：后端开发-字节跳动" />
        </el-form-item>
        <el-form-item label="PDF文件">
          <el-upload
            v-model:file-list="fileList"
            accept=".pdf"
            :auto-upload="false"
            :limit="1"
          >
            <el-button type="primary">选择文件</el-button>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="renameDialog" title="重命名简历" width="400px">
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="renamingResume.name" placeholder="简历名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renameDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRename">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewDialog" title="简历预览" width="80%" @close="closePreview">
      <iframe v-if="previewUrl" :src="previewUrl" class="pdf-preview" />
    </el-dialog>

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

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #1e3a5f;
}

.header-right {
  display: flex;
  align-items: center;
}

.resume-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.resume-card {
  transition: all 0.2s;
}

.resume-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.resume-info {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}

.resume-icon {
  color: #ef4444;
}

.resume-name {
  font-weight: 600;
  font-size: 15px;
  color: #1e3a5f;
}

.resume-date {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
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
  gap: 4px;
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
</style>
