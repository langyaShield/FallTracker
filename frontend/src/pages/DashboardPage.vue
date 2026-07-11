<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search, Download, Upload, Delete, Grid, List, ArrowDown } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { useUndoDelete } from '@/composables/useUndoDelete'
import { STATUS_COLUMNS, STATUS_LABEL_MAP, STATUS_COLOR_MAP } from '@/lib/constants'
import { formatDateTime, getDeadlineUrgency } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import BatchImportDialog from '@/components/BatchImportDialog.vue'

const router = useRouter()
const route = useRoute()

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
const loading = ref(true)
const initialLoading = ref(true)  // 仅首次加载显示骨架屏，后续搜索/排序静默刷新
const dataReady = ref(false)  // 首次数据加载完成后才渲染内容
const dialogVisible = ref(false)
const editing = ref<Partial<Delivery>>({})

// 删除撤销
const { pendingIds: deletingDeliveryIds, requestDelete: requestDeleteDelivery } = useUndoDelete<Delivery>({
  getId: (d) => d.id,
  getName: (d) => `${d.company} - ${d.position}`,
  deleteFn: async (d) => {
    await api.delete(`/deliveries/${d.id}`)
  },
  onSuccess: () => fetchDeliveries(),
})

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

const sortOption = ref('created_at_desc')

const sortOptions = [
  { label: '创建时间 ↓', value: 'created_at_desc' },
  { label: '创建时间 ↑', value: 'created_at_asc' },
  { label: '最近更新 ↓', value: 'updated_at_desc' },
  { label: '截止日期 ↑', value: 'deadline_asc' },
  { label: '公司 A-Z', value: 'company_asc' },
]

const clearFilters = () => {
  searchQuery.value = ''
  debouncedSearch.value = ''
  sortOption.value = 'created_at_desc'
}

const hasActiveFilters = computed(() => {
  return debouncedSearch.value !== '' || sortOption.value !== 'created_at_desc'
})

// Build query params from current filter state and fetch from backend
const buildQueryParams = () => {
  const params: Record<string, string | string[]> = {}

  // text search
  const q = debouncedSearch.value.trim()
  if (q) {
    params.search = q
  }

  // sort
  const sort = sortOption.value
  if (sort === 'created_at_desc') {
    params.sort_by = 'created_at'
    params.sort_order = 'desc'
  } else if (sort === 'created_at_asc') {
    params.sort_by = 'created_at'
    params.sort_order = 'asc'
  } else if (sort === 'updated_at_desc') {
    params.sort_by = 'updated_at'
    params.sort_order = 'desc'
  } else if (sort === 'deadline_asc') {
    params.sort_by = 'deadline'
    params.sort_order = 'asc'
  } else if (sort === 'company_asc') {
    params.sort_by = 'company'
    params.sort_order = 'asc'
  }

  return params
}

// Deliveries returned from backend are already filtered/sorted
const filteredDeliveries = computed(() => deliveries.value.filter((d) => !deletingDeliveryIds.value.has(d.id)))

// --- View mode (kanban / list) ---
const viewMode = ref<'kanban' | 'list'>(
  (localStorage.getItem('dashboard_view_mode') as 'kanban' | 'list') || 'kanban'
)

watch(viewMode, (v) => {
  localStorage.setItem('dashboard_view_mode', v)
})

// --- Kanban column collapse state ---
const collapsedColumns = ref<Set<string>>(new Set())

const toggleColumn = (key: string) => {
  const s = new Set(collapsedColumns.value)
  if (s.has(key)) {
    s.delete(key)
  } else {
    s.add(key)
  }
  collapsedColumns.value = s
}

const allColumnsCollapsed = computed(() =>
  STATUS_COLUMNS.length > 0 && STATUS_COLUMNS.every((c) => collapsedColumns.value.has(c.key))
)

const toggleAllColumns = () => {
  if (allColumnsCollapsed.value) {
    collapsedColumns.value = new Set()
  } else {
    collapsedColumns.value = new Set(STATUS_COLUMNS.map((c) => c.key))
  }
}

// --- List view sorting ---
const listSortProp = ref<string>('')
const listSortOrder = ref<string>('')

const onListSortChange = ({ prop, order }: { prop: string; order: string | null }) => {
  listSortProp.value = prop || ''
  listSortOrder.value = order || ''
}

const sortedListDeliveries = computed(() => {
  if (!listSortProp.value || !listSortOrder.value) return filteredDeliveries.value
  const arr = [...filteredDeliveries.value]
  const prop = listSortProp.value as keyof Delivery
  const asc = listSortOrder.value === 'ascending' ? 1 : -1
  arr.sort((a, b) => {
    const va = a[prop] ?? ''
    const vb = b[prop] ?? ''
    if (va < vb) return -1 * asc
    if (va > vb) return 1 * asc
    return 0
  })
  return arr
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
      add_tags: [tag],
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
  const count = selectedIds.value.size
  try {
    await ElMessageBox.confirm(
      `即将永久删除 ${count} 条投递记录及关联数据，此操作不可恢复。确认继续？`,
      '批量删除确认',
      {
        type: 'warning',
        confirmButtonText: `确认删除 ${count} 条记录`,
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      }
    )
  } catch {
    return
  }
  // 二次确认
  try {
    await ElMessageBox.confirm(
      `再次确认：真的要删除这 ${count} 条记录吗？`,
      '二次确认',
      {
        type: 'error',
        confirmButtonText: `确定删除 ${count} 条`,
        cancelButtonText: '我再想想',
        confirmButtonClass: 'el-button--danger',
      }
    )
  } catch {
    return
  }
  try {
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
const urgencyBorderColor = (urgency: string): string => {
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
  // 首次加载显示骨架屏，后续搜索/排序静默刷新保留旧数据
  if (initialLoading.value) {
    loading.value = true
  }
  try {
    const params = buildQueryParams()
    const res = await api.get('/deliveries', { params })
    deliveries.value = res.data || []
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取投递列表失败'))
  } finally {
    loading.value = false
    if (initialLoading.value) {
      // 骨架屏至少显示 300ms，避免闪现
      setTimeout(() => {
        initialLoading.value = false
        dataReady.value = true
      }, 300)
    }
  }
}

// Re-fetch when search/sort filters change
watch([debouncedSearch, sortOption], () => {
  fetchDeliveries()
})

const fetchResumes = async () => {
  try {
    const res = await api.get('/resumes')
    resumes.value = res.data?.items || []
  } catch (e) {
    console.warn('简历列表加载失败', e)
  }
}

const openAdd = (defaultStatus?: string) => {
  editing.value = { status: defaultStatus || 'pending', tags: [], deadline: null }
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

const deleteDelivery = (item: Delivery) => {
  requestDeleteDelivery(item)
}

// Drag feedback: briefly highlight card after successful drop
const highlightedId = ref<number | null>(null)

const updateStatus = async (item: Delivery, newStatus: string) => {
  try {
    await api.put(`/deliveries/${item.id}`, { status: newStatus })
    item.status = newStatus
    // Flash green highlight on the card
    highlightedId.value = item.id
    setTimeout(() => { highlightedId.value = null }, 600)
    ElMessage.success('状态更新成功')
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '更新失败'))
  }
}

onMounted(() => {
  fetchDeliveries()
  fetchResumes()
  // 从首页跳转时自动打开新增投递弹窗
  if (route.query.openAdd === 'true') {
    openAdd()
    router.replace({ query: {} })
  }
})
</script>

<template>
  <div class="dashboard-page">
    <!-- 首次加载骨架屏 -->
    <div v-if="!dataReady" class="kanban-board">
      <div v-for="col in STATUS_COLUMNS" :key="col.key" class="kanban-column skeleton-column">
        <div class="column-header" :style="{ borderColor: col.color }">
          <el-skeleton :rows="0" animated>
            <template #template>
              <el-skeleton-item variant="text" style="width: 60px" />
            </template>
          </el-skeleton>
        </div>
        <div v-for="i in 3" :key="i" style="padding: 12px">
          <el-skeleton :rows="3" animated />
        </div>
      </div>
    </div>

    <template v-if="dataReady">
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
        <el-button-group class="view-toggle">
          <el-button :type="viewMode === 'kanban' ? 'primary' : 'default'" :icon="Grid" size="small" aria-label="看板视图" @click="viewMode = 'kanban'" />
          <el-button :type="viewMode === 'list' ? 'primary' : 'default'" :icon="List" size="small" aria-label="列表视图" @click="viewMode = 'list'" />
        </el-button-group>
        <el-button
          v-if="viewMode === 'kanban'"
          size="small"
          @click="toggleAllColumns"
        >
          {{ allColumnsCollapsed ? '展开全部' : '收起全部' }}
        </el-button>
        <el-button
          :type="batchMode ? 'warning' : 'default'"
          size="small"
          @click="toggleBatchMode"
        >
          {{ batchMode ? '退出批量' : '批量操作' }}
        </el-button>
      </div>
    </div>

    <!-- Empty state -->
    <div v-if="!loading && !initialLoading && deliveries.length === 0" class="empty-board">
      <el-empty :description="hasActiveFilters ? '没有匹配的投递记录，试试调整筛选条件' : '还没有投递记录'">
        <template v-if="!hasActiveFilters" #default>
          <p class="empty-board-hint">点击右上角「新增投递」开始记录你的求职进展</p>
          <div class="empty-board-actions">
            <el-button type="primary" :icon="Plus" @click="openAdd()">新增第一条投递</el-button>
            <el-button :icon="Upload" @click="importDialogVisible = true">批量导入</el-button>
          </div>
        </template>
        <template v-else #default>
          <div class="empty-board-actions">
            <el-button @click="clearFilters">清除筛选条件</el-button>
          </div>
        </template>
      </el-empty>
    </div>

    <!-- Kanban view -->
    <template v-else-if="viewMode === 'kanban'">
      <div class="kanban-board" :class="{ 'batch-mode': batchMode }">
        <div
          v-for="col in STATUS_COLUMNS"
          :key="col.key"
          class="kanban-column"
          :class="{ 'drag-over': dragOverColumn === col.key }"
        >
        <div class="column-header" :style="{ borderColor: col.color }" @click="toggleColumn(col.key)">
          <span class="column-title">{{ col.label }}</span>
          <div class="column-header-right">
            <el-tag size="small" :style="{ backgroundColor: col.color + '20', color: col.color, borderColor: col.color }">
              {{ groupedDeliveries[col.key]?.length || 0 }}
            </el-tag>
            <button
              class="column-add-btn"
              :title="`添加${col.label}投递`"
              @click.stop="openAdd(col.key)"
            >+</button>
            <el-icon class="column-collapse-icon" :class="{ 'is-collapsed': collapsedColumns.has(col.key) }">
              <ArrowDown />
            </el-icon>
          </div>
        </div>
        <div
          v-show="!collapsedColumns.has(col.key)"
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
              'card-highlighted': highlightedId === item.id,
            }"
            :style="{ borderLeftColor: urgencyBorderColor(getDeadlineUrgency(item.deadline)) }"
            draggable="true"
            tabindex="0"
            role="button"
            :aria-label="`${item.company} - ${item.position}`"
            @click.stop="onCardClick(item)"
            @keydown.enter.prevent="onCardClick(item)"
            @keydown.space.prevent="onCardClick(item)"
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
                  @click.stop="deleteDelivery(item)"
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
    </template>

    <!-- List view -->
    <div v-else v-loading="initialLoading" class="list-view" :class="{ 'batch-mode': batchMode }">
      <el-table
        :data="sortedListDeliveries"
        style="width: 100%"
        highlight-current-row
        @row-click="(row: Delivery) => router.push(`/delivery/${row.id}`)"
        @sort-change="onListSortChange"
        row-class-name="list-row"
      >
        <el-table-column prop="company" label="公司" min-width="120" sortable="custom" />
        <el-table-column prop="position" label="岗位" min-width="140" sortable="custom" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="100" sortable="custom">
          <template #default="{ row }">
            <el-tag
              size="small"
              :style="{ backgroundColor: (STATUS_COLOR_MAP[row.status] || '#94a3b8') + '20', color: STATUS_COLOR_MAP[row.status] || '#94a3b8', borderColor: STATUS_COLOR_MAP[row.status] || '#94a3b8' }"
            >
              {{ STATUS_LABEL_MAP[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tags" label="标签" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="tag in row.tags" :key="tag" size="small" class="tag">{{ tag }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="deadline" label="截止日期" width="160" sortable="custom">
          <template #default="{ row }">
            <span v-if="row.deadline">{{ formatDateTime(row.deadline) }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="160" sortable="custom">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right" @click.stop>
          <template #default="{ row }">
            <el-dropdown
              size="small"
              trigger="click"
              @command="(status: string) => updateStatus(row, status)"
            >
              <el-button text size="small" type="primary" @click.stop>推进状态</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="s in STATUS_COLUMNS.filter((s) => s.key !== row.status)"
                    :key="s.key"
                    :command="s.key"
                  >
                    {{ s.label }}
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>
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
      <el-form label-width="80px" @keyup.enter="saveDelivery">
        <el-form-item label="公司" required>
          <el-input v-model="editing.company" placeholder="公司名称（必填）" />
        </el-form-item>
        <el-form-item label="岗位" required>
          <el-input v-model="editing.position" placeholder="岗位名称（必填）" />
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
    </template>
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
  max-width: 240px;
  width: 100%;
}

.sort-select {
  min-width: 100px;
  max-width: 140px;
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
  padding-bottom: 8px;
  background:
    linear-gradient(to right, #f1f5f9 0%, transparent 16px),
    linear-gradient(to left, #f1f5f9 0%, transparent 16px);
  background-attachment: local, local;
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

/* --- Skeleton Loading --- */
.skeleton-card {
  padding: 14px;
  margin-bottom: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
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

/* Drag-drop success highlight */
.kanban-card.card-highlighted {
  animation: flash-green 0.6s ease;
}

@keyframes flash-green {
  0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.5); }
  50% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0.2); background: #f0fdf4; }
  100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
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
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.position {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-time {
  font-size: 12px;
  color: #64748b;
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
  opacity: 0.4;
  padding: 2px 6px;
  font-size: 12px;
  transition: opacity 0.2s;
}

.kanban-card:hover .delete-btn {
  opacity: 1;
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

/* --- Column header add button (E2) --- */
.column-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.column-collapse-icon {
  color: #64748b;
  font-size: 14px;
  transition: transform 0.2s;
  cursor: pointer;
}

.column-collapse-icon.is-collapsed {
  transform: rotate(-90deg);
}

.column-header {
  cursor: pointer;
}

.column-add-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1.5px solid #cbd5e1;
  background: transparent;
  color: #64748b;
  font-size: 15px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  padding: 0;
}

.column-header:hover .column-add-btn {
  opacity: 1;
}

.column-add-btn:hover {
  border-color: #3b82f6;
  color: #3b82f6;
  background: #eff6ff;
}

/* --- View toggle (X2) --- */
.view-toggle {
  flex-shrink: 0;
}

/* --- List view (X2) --- */
.list-view {
  height: calc(100vh - 210px);
  overflow-y: auto;
}

.list-view.batch-mode {
  height: calc(100vh - 270px);
}

.list-row {
  cursor: pointer;
}

.text-muted {
  color: #c0c4cc;
}

/* Empty board guide */
.empty-board {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  text-align: center;
}

.empty-board-hint {
  font-size: 14px;
  color: #64748b;
  margin: 0 0 8px 0;
}

.empty-board-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-top: 16px;
}

/* 移动端适配 */
@media (max-width: 768px) {
  .search-input {
    max-width: 100%;
  }

  .sort-select {
    max-width: 100%;
    width: 100%;
  }

  .kanban-board {
    height: calc(100dvh - 220px);
  }

  .kanban-board.batch-mode {
    height: calc(100dvh - 340px);
  }

  .kanban-column {
    min-width: 220px;
  }

  .kanban-card {
    padding: 10px;
  }

  .list-view {
    height: calc(100dvh - 220px);
  }

  .list-view.batch-mode {
    height: calc(100dvh - 340px);
  }

  .batch-bar {
    flex-direction: column;
    align-items: flex-start;
    padding: 10px 12px;
    gap: 10px;
  }

  .batch-bar-actions {
    width: 100%;
  }

  .batch-select {
    width: 100%;
  }

  .batch-tag-input {
    width: 100%;
  }
}
</style>
