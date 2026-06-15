<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { STATUS_COLUMNS } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

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
// wasDragged 用 ref 暴露，便于 HMR 序列化与未来可观察
const wasDragged = ref(false)

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
  router.push(`/delivery/${item.id}`)
}

const groupedDeliveries = computed(() => {
  const map: Record<string, Delivery[]> = {}
  for (const col of STATUS_COLUMNS) {
    map[col.key] = deliveries.value.filter((d) => d.status === col.key)
  }
  return map
})

const fetchDeliveries = async () => {
  loading.value = true
  try {
    const res = await api.get('/deliveries')
    deliveries.value = res.data || []
  } catch (e: any) {
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
  } catch (e: any) {
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
  } catch (e: any) {
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
      <el-button type="primary" :icon="Plus" @click="openAdd">新增投递</el-button>
    </PageHeader>

    <div v-loading="loading" class="kanban-board">
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
            draggable="true"
            @click.stop="onCardClick(item)"
            @dragstart="onDragStart($event, item)"
            @dragend="onDragEnd"
          >
            <div class="card-header">
              <span class="company">{{ item.company }}</span>
              <el-button
                text
                size="small"
                type="danger"
                @click.stop="deleteDelivery(item.id)"
                class="delete-btn"
              >
                删除
              </el-button>
            </div>
            <div class="position">{{ item.position }}</div>
            <div class="card-time">{{ formatDateTime(item.created_at) }}</div>
            <div v-if="item.deadline" class="card-deadline">
              <span class="deadline-label">Deadline:</span> {{ formatDateTime(item.deadline) }}
            </div>
            <div class="card-tags">
              <el-tag v-for="tag in item.tags" :key="tag" size="small" class="tag">{{ tag }}</el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

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
  </div>
</template>

<style scoped>
.dashboard-page {
  height: 100%;
}

.kanban-board {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  height: calc(100vh - 140px);
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

.kanban-card {
  background: #fff;
  border: 1px solid #e2e8f0;
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

.kanban-column.drag-over .column-body {
  background: #f0f9ff;
  border-radius: 8px;
}

.kanban-column.drag-over {
  box-shadow: 0 0 0 2px #3b82f6 inset;
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
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
}

.deadline-label {
  font-weight: 600;
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
</style>
