<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Download, Upload, Delete } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { STATUS_COLUMNS } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import BatchImportDialog from '@/components/BatchImportDialog.vue'

const router = useRouter()

interface Delivery {
  id: number
  company: string
  position: string
  status: string
  tags: string[]
  link?: string
  jd_text?: string
  resume_id?: number | null
  deadline?: string | null
  created_at: string
  updated_at: string
}

interface Resume {
  id: number
  name: string
}

const deliveries = ref<Delivery[]>([])
const resumes = ref<Resume[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref<Partial<Delivery>>({})

// Drag state
const draggedItem = ref<Delivery | null>(null)
const dragOverColumn = ref<string | null>(null)
const wasDragged = ref(false)

// --- Search & Filter state ---
const searchQuery = ref('')
const debouncedSearch = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

watch(searchQuery, (val) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    debouncedSearch.value = val
  }, 300)
})

const activeStatusFilters = ref<Set<string>>(new Set())
const sortOption = ref('created_at_desc')

const sortOptions = [
  { label: '创建时间 ↓', value: 'created_at_desc' },
  { label: '创建时间 ↑', value: 'created_at_asc' },
  { label: '截止日期 ↑', value: 'deadline_asc' },
  { label: '公司 A-Z', value: 'company_asc' },
]

const toggleStatusFilter = (key: string) => {
  const s = new Set(activeStatusFilters.value)
  if (s.has(key)) {
    s.delete(key)
  } else {
    s.add(key)
  }
  activeStatusFilters.value = s
}

const clearFilters = () => {
  searchQuery.value = ''
  debouncedSearch.value = ''
  activeStatusFilters.value = new Set()
  sortOption.value = 'created_at_desc'
}

const hasActiveFilters = computed(() => {
  return debouncedSearch.value !== '' || activeStatusFilters.value.size > 0
})

const filteredDeliveries = computed(() => {
  let list = deliveries.value.slice()

  // text search
  const q = debouncedSearch.value.trim().toLowerCase()
  if (q) {
    list = list.filter((d) => {
      return (
        d.company.toLowerCase().includes(q) ||
        d.position.toLowerCase().includes(q) ||
        (d.tags || []).some((t) => t.toLowerCase().includes(q))
      )
    })
  }

  // status filter
  if (activeStatusFilters.value.size > 0) {
    list = list.filter((d) => activeStatusFilters.value.has(d.status))
  }

  // sort
  const sort = sortOption.value
  list.sort((a, b) => {
    if (sort === 'created_at_desc') {
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    }
    if (sort === 'created_at_asc') {
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
    }
    if (sort === 'deadline_asc') {
      const da = a.deadline ? new Date(a.deadline).getTime() : Infinity
      const db = b.deadline ? new Date(b.deadline).getTime() : Infinity
      return da - db
    }
    if (sort === 'company_asc') {
      return a.company.localeCompare(b.company, 'zh-CN')
    }
    return 0
  })

  return list
})

// --- Batch operation state ---
const batchMode = ref(false)
const selectedIds = ref<Set<number>>(new Set())

const toggleBatchMode = () => {
  batchMode.value = !batchMode.value
  if (!batchMode.value) {
    selectedIds.value = new Set()
  }
}

const toggleSelect = (id: number) => {
  const s = new Set(selectedIds.value)
  if (s.has(id)) {
    s.delete(id)
  } else {
    s.add(id)
  }
  selectedIds.value = s
}

const selectAll = () => {
  const allSelected = filteredDeliveries.value.every((d) => selectedIds.value.has(d.id))
  if (allSelected) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(filteredDeliveries.value.map((d) => d.id))
  }
}

const batchStatusValue = ref('')
const batchTagInput = ref('')
const batchLoading = ref(false)

const batchUpdateStatus = async () => {
  if (!batchStatusValue.value || selectedIds.value.size === 0) return
  batchLoading.value = true
  try {
    await api.put('/deliveries/batch/status', {
      ids: Array.from(selectedIds.value),
      status: batchStatusValue.value,
    })
    ElMessage.success('批量更新状态成功')
    selectedIds.value = new Set()
    batchStatusValue.value = ''
    fetchDeliveries()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '批量更新失败'))
  } finally {
    batchLoading.value = false
  }
}

const batchAddTags = async () => {
  const tag = batchTagInput.value.trim()
  if (!tag || selectedIds.value.size === 0) return
  batchLoading.value = true
  try {
    await api.put('/deliveries/batch/tags', {
      ids: Array.from(selectedIds.value),
      tags: [tag],
    })
    ElMessage.success('批量添加标签成功')
    selectedIds.value = new Set()
    batchTagInput.value = ''
    fetchDeliveries()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '批量添加标签失败'))
  } finally {
    batchLoading.value = false
  }
}

const batchDelete = async () => {
  if (selectedIds.value.size === 0) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${selectedIds.value.size} 条投递记录吗？`, '批量删除', {
      type: 'warning',
    })
    batchLoading.value = true
    await api.delete('/deliveries/batch', {
      data: { ids: Array.from(selectedIds.value) },
    })
    ElMessage.success('批量删除成功')
    selectedIds.value = new Set()
    fetchDeliveries()
  } catch {
    // cancelled or error
  } finally {
    batchLoading.value = false
  }
}

// --- Import / Export ---
const importDialogVisible = ref(false)

const handleExport = async () => {
  try {
    const res = await api.get('/deliveries/export', { responseType: 'blob' })
    const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `deliveries_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '导出失败'))
  }
}

const handleImported = () => {
  fetchDeliveries()
}

// --- Deadline urgency ---
const getDeadlineUrgency = (deadline?: string | null): 'urgent' | 'warning' | 'expired' | null => {
  if (!deadline) return null
  const now = Date.now()
  const dl = new Date(deadline).getTime()
  const diff = dl - now
  if (diff < 0) return 'expired'
  if (diff <= 24 * 60 * 60 * 1000) return 'urgent'
  if (diff <= 48 * 60 * 60 * 1000) return 'warning'
  return null
}

const urgencyBorderColor = (urgency: string | null): string => {
  if (urgency === 'expired') return '#991b1b'
  if (urgency === 'urgent') return '#ef4444'
  if (urgency === 'warning') return '#f97316'
  return 'transparent'
}

// --- Drag & Drop handlers ---
const onDragStart = (e: DragEvent, item: Delivery) => {
  draggedItem.value = item
  wasDragged.value = false
  e.dataTransfer?.setData('text/plain', String(item.id))
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
  }
  requestAnimationFrame(() => {
    if (e.target instanceof HTMLElement) {
      e.target.classList.add('dragging')
    }
  })
}

const onDragEnd = (e: DragEvent) => {
  wasDragged.value = true
  draggedItem.value = null
  dragOverColumn.value = null
  if (e.target instanceof HTMLElement) {
    e.target.classList.remove('dragging')
  }
}

const onDragOver = (e: DragEvent, columnKey: string) => {
  e.preventDefault()
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move'
  }
  dragOverColumn.value = columnKey
}

const onDragLeave = (_e: DragEvent, columnKey: string) => {
  if (dragOverColumn.value === columnKey) {
    dragOverColumn.value = null
  }
}

const onDrop = async (e: DragEvent, targetStatus: string) => {
  e.preventDefault()
  dragOverColumn.value = null
  const item = draggedItem.value
  if (!item) return
  if (item.status === targetStatus) return
  await updateStatus(item, targetStatus)
}

const onCardClick = (item: Delivery) => {
  if (wasDragged.value) {
    wasDragged.value = false
    return
  }
  if (batchMode.value) {
    toggleSelect(item.id)
    return
  }
  router.push(`/delivery/${item.id}`)
}

const groupedDeliveries = computed(() => {
  const map: Record<string, Delivery[]> = {}
  for (const col of STATUS_COLUMNS) {
    map[col.key] = filteredDeliveries.value.filter((d) => d.status === col.key)
  }
  return map
})

const fetchDeliveries = async () => {
  loading.value = true
  try {
    const res = await api.get('/deliveries')
    deliveries.value = res.data || []
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取投递列表失败'))
  } finally {
    loading.value = false
  }
}

const fetchResumes = async () => {
  try {
    const res = await api.get('/resumes')
    resumes.value = res.data || []
  } catch {
    // ignore
  }
}

const openAdd = () => {
  editing.value = { status: 'pending', tags: [], deadline: null }
  dialogVisible.value = true
}

const saveDelivery = async () => {
  if (!editing.value.company || !editing.value.position) {
    ElMessage.warning('请填写公司和岗位')
    return
  }
  try {
    if (editing.value.id) {
      await api.put(`/deliveries/${editing.value.id}`, editing.value)
      ElMessage.success('更新成功')
    } else {
      await api.post('/deliveries', editing.value)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    fetchDeliveries()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const deleteDelivery = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除这条投递记录吗？', '提示', { type: 'warning' })
    await api.delete(`/deliveries/${id}`)
    ElMessage.success('删除成功')
    fetchDeliveries()
  } catch {
    // cancelled
  }
}

const updateStatus = async (item: Delivery, newStatus: string) => {
  try {
    await api.put(`/deliveries/${item.id}`, { status: newStatus })
    item.status = newStatus
    ElMessage.success('状态更新成功')
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '更新失败'))
  }
}

onMounted(() => {
  fetchDeliveries()
  fetchResumes()
})
</script>

<template>
  <div class="dashboard-page">
    <PageHeader title="投递大盘">
      <el-button :icon="Upload" @click="importDialogVisible = true">导入</el-button>
      <el-button :icon="Download" @click="handleExport">导出</el-button>
      <el-button type="primary" :icon="Plus" @click="openAdd">新增投递</el-button>
    </PageHeader>

    <!-- Search & Filter Toolbar -->
    <div class="filter-toolbar">
      <div class="filter-row">
        <el-input
          v-model="searchQuery"
          placeholder="搜索公司、岗位、标签..."
          :prefix-icon="Search"
          clearable
          class="search-input"
        />
        <div class="status-filters">
          <el-button
            v-for="col in STATUS_COLUMNS"
            :key="col.key"
            :type="activeStatusFilters.has(col.key) ? 'primary' : 'default'"
            size="small"
            @click="toggleStatusFilter(col.key)"
            class="status-filter-btn"
          >
            {{ col.label }}
          </el-button>
        </div>
        <el-select v-model="sortOption" placeholder="排序" class="sort-select">
          <el-option
            v-for="opt in sortOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-button v-if="hasActiveFilters" size="small" @click="clearFilters">清除筛选</el-button>
        <span class="filter-count">匹配 {{ filteredDeliveries.length }} 条</span>
        <el-button
          :type="batchMode ? 'warning' : 'default'"
          size="small"
          @click="toggleBatchMode"
        >
          {{ batchMode ? '退出批量' : '批量操作' }}
        </el-button>
      </div>
    </div>

    <div v-loading="loading" class="kanban-board" :class="{ 'batch-mode': batchMode }">
      <div
        v-for="col in STATUS_COLUMNS"
        :key="col.key"
        class="kanban-column"
        :class="{ 'drag-over': dragOverColumn === col.key }"
      >
        <div class="column-header" :style="{ borderColor: col.color }">
          <span class="column-title">{{ col.label }}</span>
          <el-tag size="small" :style="{ backgroundColor: col.color + '20', color: col.color, borderColor: col.color }">
            {{ groupedDeliveries[col.key]?.length || 0 }}
          </el-tag>
        </div>
        <div
          class="column-body"
          @dragover="onDragOver($event, col.key)"
          @dragleave="onDragLeave($event, col.key)"
          @drop="onDrop($event, col.key)"
        >
          <div
            v-for="item in groupedDeliveries[col.key]"
            :key="item.id"
            class="kanban-card"
            :class="{
              'card-urgent': getDeadlineUrgency(item.deadline) === 'urgent',
              'card-warning': getDeadlineUrgency(item.deadline) === 'warning',
              'card-expired': getDeadlineUrgency(item.deadline) === 'expired',
              'card-selected': selectedIds.has(item.id),
            }"
            :style="{ borderLeftColor: urgencyBorderColor(getDeadlineUrgency(item.deadline)) }"
            draggable="true"
            @click.stop="onCardClick(item)"
            @dragstart="onDragStart($event, item)"
            @dragend="onDragEnd"
          >
            <div class="card-top-row">
              <el-checkbox
                v-if="batchMode"
                :model-value="selectedIds.has(item.id)"
                @click.stop
                @change="toggleSelect(item.id)"
                class="batch-checkbox"
              />
              <div class="card-header">
                <span class="company">{{ item.company }}</span>
                <el-button
                  v-if="!batchMode"
                  text
                  size="small"
                  type="danger"
                  @click.stop="deleteDelivery(item.id)"
                  class="delete-btn"
                >
                  删除
                </el-button>
              </div>
            </div>
            <div class="position">{{ item.position }}</div>
            <div class="card-time">{{ formatDateTime(item.created_at) }}</div>
            <div v-if="item.deadline" class="card-deadline" :class="{
              'deadline-urgent': getDeadlineUrgency(item.deadline) === 'urgent',
              'deadline-warning': getDeadlineUrgency(item.deadline) === 'warning',
              'deadline-expired': getDeadlineUrgency(item.deadline) === 'expired',
            }">
              <span class="deadline-label">Deadline:</span> {{ formatDateTime(item.deadline) }}
              <el-tag v-if="getDeadlineUrgency(item.deadline) === 'expired'" size="small" type="danger" class="expired-tag">已过期</el-tag>
            </div>
            <div class="card-tags">
              <el-tag v-for="tag in item.tags" :key="tag" size="small" class="tag">{{ tag }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Batch action bar -->
    <div v-if="batchMode" class="batch-bar">
      <div class="batch-bar-left">
        <el-checkbox
          :model-value="filteredDeliveries.length > 0 && filteredDeliveries.every((d) => selectedIds.has(d.id))"
          :indeterminate="selectedIds.size > 0 && !filteredDeliveries.every((d) => selectedIds.has(d.id))"
          @change="selectAll"
        >
          全选
        </el-checkbox>
        <span class="batch-count">已选 {{ selectedIds.size }} 条</span>
      </div>
      <div class="batch-bar-actions">
        <el-select v-model="batchStatusValue" placeholder="批量改状态" clearable class="batch-select">
          <el-option v-for="s in STATUS_COLUMNS" :key="s.key" :label="s.label" :value="s.key" />
        </el-select>
        <el-button
          type="primary"
          size="small"
          :disabled="!batchStatusValue || selectedIds.size === 0"
          :loading="batchLoading"
          @click="batchUpdateStatus"
        >
          应用状态
        </el-button>
        <el-input
          v-model="batchTagInput"
          placeholder="添加标签"
          size="small"
          class="batch-tag-input"
          @keyup.enter="batchAddTags"
        />
        <el-button
          type="primary"
          size="small"
          :disabled="!batchTagInput.trim() || selectedIds.size === 0"
          :loading="batchLoading"
          @click="batchAddTags"
        >
          添加标签
        </el-button>
        <el-button
          type="danger"
          size="small"
          :icon="Delete"
          :disabled="selectedIds.size === 0"
          :loading="batchLoading"
          @click="batchDelete"
        >
          批量删除
        </el-button>
      </div>
    </div>

    <!-- Add/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="editing.id ? '编辑投递' : '新增投递'" width="500px">
      <el-form label-width="80px">
        <el-form-item label="公司">
          <el-input v-model="editing.company" placeholder="公司名称" />
        </el-form-item>
        <el-form-item label="岗位">
          <el-input v-model="editing.position" placeholder="岗位名称" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="editing.status" placeholder="选择状态" style="width: 100%">
            <el-option v-for="s in STATUS_COLUMNS" :key="s.key" :label="s.label" :value="s.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select-v2
            v-model="editing.tags"
            :options="[]"
            placeholder="输入标签按回车"
            allow-create
            multiple
            filterable
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="JD链接">
          <el-input v-model="editing.link" placeholder="招聘链接" />
        </el-form-item>
        <el-form-item label="JD描述">
          <el-input v-model="editing.jd_text" type="textarea" :rows="3" placeholder="岗位描述" />
        </el-form-item>
        <el-form-item label="简历">
          <el-select v-model="editing.resume_id" placeholder="选择简历（可选）" clearable style="width: 100%">
            <el-option v-for="r in resumes" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker
            v-model="editing.deadline"
            type="datetime"
            placeholder="选择截止日期（可选）"
            style="width: 100%"
            value-format="YYYY-MM-DDTHH:mm"
            clearable
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveDelivery">保存</el-button>
      </template>
    </el-dialog>

    <!-- Import Dialog -->
    <BatchImportDialog v-model="importDialogVisible" @imported="handleImported" />
  </div>
</template>

<style scoped>
.dashboard-page {
  height: 100%;
}

/* --- Filter Toolbar --- */
.filter-toolbar {
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.search-input {
  width: 240px;
}

.status-filters {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.status-filter-btn {
  border-radius: 16px;
}

.sort-select {
  width: 140px;
}

.filter-count {
  font-size: 13px;
  color: #64748b;
  white-space: nowrap;
}

/* --- Kanban Board --- */
.kanban-board {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  height: calc(100vh - 210px);
  transition: height 0.2s;
}

.kanban-board.batch-mode {
  height: calc(100vh - 270px);
}

.kanban-column {
  flex: 1;
  min-width: 240px;
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.column-header {
  padding: 16px;
  border-bottom: 3px solid;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.column-title {
  font-weight: 600;
  font-size: 15px;
  color: #334155;
}

.column-body {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
}

/* --- Kanban Card --- */
.kanban-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-left: 3px solid transparent;
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 10px;
  cursor: grab;
  transition: all 0.2s;
  user-select: none;
}

.kanban-card:active {
  cursor: grabbing;
}

.kanban-card.dragging {
  opacity: 0.4;
  transform: scale(1.02);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
}

.kanban-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.kanban-card.card-selected {
  border-color: #3b82f6;
  background: #eff6ff;
}

/* Urgency border colors */
.kanban-card.card-urgent {
  border-left-color: #ef4444;
}

.kanban-card.card-warning {
  border-left-color: #f97316;
}

.kanban-card.card-expired {
  border-left-color: #991b1b;
}

.kanban-column.drag-over .column-body {
  background: #f0f9ff;
  border-radius: 8px;
}

.kanban-column.drag-over {
  box-shadow: 0 0 0 2px #3b82f6 inset;
  border-radius: 12px;
}

/* --- Card internals --- */
.card-top-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.batch-checkbox {
  margin-top: 2px;
  flex-shrink: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  flex: 1;
}

.company {
  font-weight: 600;
  font-size: 15px;
  color: #1e3a5f;
}

.position {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 4px;
}

.card-time {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 8px;
}

.card-deadline {
  font-size: 12px;
  color: #f59e0b;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.card-deadline.deadline-urgent {
  color: #ef4444;
}

.card-deadline.deadline-warning {
  color: #f97316;
}

.card-deadline.deadline-expired {
  color: #991b1b;
}

.deadline-label {
  font-weight: 600;
}

.expired-tag {
  margin-left: 4px;
}

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  font-size: 12px;
}

.delete-btn {
  visibility: hidden;
  padding: 2px 6px;
  font-size: 12px;
}

.kanban-card:hover .delete-btn {
  visibility: visible;
}

/* --- Batch Action Bar --- */
.batch-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: #fff;
  border-top: 1px solid #e2e8f0;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.08);
  z-index: 100;
}

.batch-bar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.batch-count {
  font-size: 14px;
  color: #1e3a5f;
  font-weight: 600;
}

.batch-bar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.batch-select {
  width: 140px;
}

.batch-tag-input {
  width: 120px;
}
</style>
