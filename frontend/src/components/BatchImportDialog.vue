<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  imported: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const step = ref<'upload' | 'preview' | 'result'>('upload')
const file = ref<File | null>(null)
const headers = ref<string[]>([])
const rows = ref<Record<string, string>[]>([])
const totalRows = ref(0)
const loading = ref(false)
const result = ref<{ created: number; skipped: number; errors: string[] }>({
  created: 0,
  skipped: 0,
  errors: [],
})

const handleFileChange = (uploadFile: { file: File }) => {
  file.value = uploadFile.file
  previewCSV()
}

const previewCSV = async () => {
  if (!file.value) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.value)
    const res = await api.post('/deliveries/import/preview', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    headers.value = res.data.headers
    rows.value = res.data.rows
    totalRows.value = res.data.total
    step.value = 'preview'
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '预览失败'))
  } finally {
    loading.value = false
  }
}

const confirmImport = async () => {
  if (!file.value) return
  loading.value = true
  try {
    const formData = new FormData()
    formData.append('file', file.value)
    const res = await api.post('/deliveries/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    result.value = res.data
    step.value = 'result'
    if (res.data.created > 0) {
      emit('imported')
    }
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '导入失败'))
  } finally {
    loading.value = false
  }
}

const reset = () => {
  step.value = 'upload'
  file.value = null
  headers.value = []
  rows.value = []
  totalRows.value = 0
  result.value = { created: 0, skipped: 0, errors: [] }
}

const close = () => {
  visible.value = false
  reset()
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="CSV 批量导入"
    width="700px"
    @close="close"
  >
    <!-- Step 1: Upload -->
    <div v-if="step === 'upload'" class="upload-step">
      <el-upload
        drag
        accept=".csv"
        :auto-upload="false"
        :show-file-list="false"
        :on-change="handleFileChange"
      >
        <el-icon :size="48"><Upload /></el-icon>
        <div class="upload-text">拖拽 CSV 文件到此处，或点击选择</div>
        <template #tip>
          <div class="upload-tip">
            支持中英文表头：公司/company、岗位/position、状态/status、链接/link、标签/tags、截止日期/deadline、描述/jd_text
          </div>
        </template>
      </el-upload>
    </div>

    <!-- Step 2: Preview -->
    <div v-else-if="step === 'preview'" class="preview-step">
      <p class="preview-info">
        共 <strong>{{ totalRows }}</strong> 条数据，预览前 {{ rows.length }} 条：
      </p>
      <el-table :data="rows" max-height="300" border size="small" stripe>
        <el-table-column
          v-for="h in headers"
          :key="h"
          :prop="h"
          :label="h"
          min-width="100"
          show-overflow-tooltip
        />
      </el-table>
      <div class="preview-actions">
        <el-button @click="step = 'upload'">重新选择</el-button>
        <el-button type="primary" :loading="loading" @click="confirmImport">
          确认导入 {{ totalRows }} 条
        </el-button>
      </div>
    </div>

    <!-- Step 3: Result -->
    <div v-else class="result-step">
      <el-result
        :icon="result.errors.length ? 'warning' : 'success'"
        :title="result.errors.length ? '导入完成（有警告）' : '导入成功'"
      >
        <template #sub-title>
          <p>成功导入 <strong>{{ result.created }}</strong> 条，跳过 <strong>{{ result.skipped }}</strong> 条</p>
          <div v-if="result.errors.length" class="error-list">
            <p v-for="(err, i) in result.errors.slice(0, 10)" :key="i" class="error-item">{{ err }}</p>
            <p v-if="result.errors.length > 10" class="error-more">
              ...还有 {{ result.errors.length - 10 }} 条错误
            </p>
          </div>
        </template>
        <template #extra>
          <el-button type="primary" @click="close">完成</el-button>
        </template>
      </el-result>
    </div>
  </el-dialog>
</template>

<style scoped>
.upload-step {
  text-align: center;
}
.upload-text {
  margin-top: 12px;
  font-size: 14px;
  color: #606266;
}
.upload-tip {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
}
.preview-step {
  padding: 0 4px;
}
.preview-info {
  margin-bottom: 12px;
  font-size: 14px;
}
.preview-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.result-step {
  text-align: center;
}
.error-list {
  text-align: left;
  max-height: 150px;
  overflow-y: auto;
  margin-top: 8px;
}
.error-item {
  font-size: 12px;
  color: #e6a23c;
  margin: 2px 0;
}
.error-more {
  font-size: 12px;
  color: #909399;
}
</style>
