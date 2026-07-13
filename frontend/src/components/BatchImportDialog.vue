<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { previewCsvImport, importCsv } from '@/modules/applications/commands'
import type { ImportResult } from '@/modules/applications/types'
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
const rawHeaders = ref<string[]>([])
const rows = ref<Record<string, string>[]>([])
const totalRows = ref(0)
const loading = ref(false)
const result = ref<ImportResult>({
  created: 0,
  skipped: 0,
  errors: [],
})

// 列映射
const FIELD_OPTIONS = [
  { label: '公司', value: 'company' },
  { label: '岗位', value: 'position' },
  { label: '状态', value: 'status' },
  { label: '链接', value: 'link' },
  { label: '标签', value: 'tags' },
  { label: '截止日期', value: 'deadline' },
  { label: 'JD描述', value: 'jd_text' },
  { label: '(忽略此列)', value: '__ignore__' },
] as const

const columnMapping = ref<Record<string, string>>({})

const handleFileChange = (uploadFile: { file: File }) => {
  file.value = uploadFile.file
  previewCSV()
}

const previewCSV = async () => {
  if (!file.value) return
  loading.value = true
  try {
    const data = await previewCsvImport(file.value)
    headers.value = data.headers
    rawHeaders.value = data.raw_headers || data.headers
    rows.value = data.rows
    totalRows.value = data.total
    // Initialize mapping from auto-detected headers
    const map: Record<string, string> = {}
    rawHeaders.value.forEach((raw, i) => {
      map[raw] = headers.value[i] || raw
    })
    columnMapping.value = map
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
    // Build custom mapping JSON (rawHeader -> deliveryField)
    const mappingJson: Record<string, string> = {}
    for (const [raw, field] of Object.entries(columnMapping.value)) {
      if (field !== '__ignore__') {
        mappingJson[raw] = field
      }
    }
    const importResult = await importCsv(file.value, mappingJson)
    result.value = importResult
    step.value = 'result'
    if (importResult.created > 0) {
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
  rawHeaders.value = []
  rows.value = []
  totalRows.value = 0
  columnMapping.value = {}
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
    width="90%"
    style="max-width: 700px"
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

      <!-- 列映射配置 -->
      <div class="mapping-section">
        <div class="mapping-title">列映射配置</div>
        <div class="mapping-table">
          <div v-for="raw in rawHeaders" :key="raw" class="mapping-row">
            <span class="mapping-raw-header">{{ raw }}</span>
            <span class="mapping-arrow">→</span>
            <el-select
              v-model="columnMapping[raw]"
              size="small"
              class="mapping-select"
            >
              <el-option
                v-for="opt in FIELD_OPTIONS"
                :key="opt.value"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </div>
        </div>
      </div>

      <el-table :data="rows" max-height="240" border size="small" stripe style="margin-top: 12px">
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
.mapping-section {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 8px;
}
.mapping-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e3a5f;
  margin-bottom: 10px;
}
.mapping-table {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 10px;
}
.mapping-raw-header {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
  min-width: 50px;
}
.mapping-arrow {
  color: #64748b;
  font-size: 14px;
}
.mapping-select {
  width: 120px;
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
