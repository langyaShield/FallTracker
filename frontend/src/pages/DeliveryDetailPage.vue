<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus, Edit, Delete, ChatDotRound, Document, Timer } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { STATUS_COLUMNS, EVENT_TYPE_OPTIONS, EVENT_TYPE_LABEL_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'

const route = useRoute()
const router = useRouter()

interface InterviewEvent {
  id: number
  event_type: string
  round_number: number
  scheduled_at: string
  duration_minutes: number
  location?: string
  meeting_link?: string
  interviewer?: string
  notes?: string
}

interface Delivery {
  id: number
  company: string
  position: string
  jd_text?: string
  link?: string
  status: string
  tags: string[]
  resume_id?: number | null
  deadline?: string | null
  created_at: string
  updated_at: string
}

interface Resume {
  id: number
  name: string
}

const delivery = ref<Delivery | null>(null)
const events = ref<InterviewEvent[]>([])
const resumes = ref<Resume[]>([])
const loading = ref(false)
const eventDialog = ref(false)
const editingEvent = ref<Partial<InterviewEvent>>({})

const statusOptions = STATUS_COLUMNS.map((s) => ({ label: s.label, value: s.key }))

const fetchDetail = async () => {
  loading.value = true
  try {
    const res = await api.get(`/deliveries/${route.params.id}`)
    delivery.value = res.data
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取详情失败'))
  } finally {
    loading.value = false
  }
}

const fetchEvents = async () => {
  try {
    const res = await api.get(`/deliveries/${route.params.id}/events`)
    events.value = res.data
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取事件失败'))
  }
}

const fetchResumes = async () => {
  try {
    const res = await api.get('/resumes')
    resumes.value = res.data?.items || []
  } catch {
    // ignore
  }
}

/** N-BUG-1 修复：从全量投递聚合出已用过的标签作为 el-select-v2 的建议项 */
const tagOptions = ref<{ value: string; label: string }[]>([])
const fetchTagSuggestions = async () => {
  try {
    const res = await api.get('/deliveries')
    const allTags = new Set<string>()
    ;(res.data || []).forEach((d: Delivery) => (d.tags || []).forEach((t) => allTags.add(t)))
    tagOptions.value = Array.from(allTags).map((t) => ({ value: t, label: t }))
  } catch {
    // ignore
  }
}

const saveDelivery = async () => {
  if (!delivery.value) return
  try {
    await api.put(`/deliveries/${delivery.value.id}`, delivery.value)
    ElMessage.success('保存成功')
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const openEventDialog = (event?: InterviewEvent) => {
  if (event) {
    editingEvent.value = { ...event, scheduled_at: event.scheduled_at.slice(0, 16) }
  } else {
    editingEvent.value = {
      event_type: 'interview',
      round_number: events.value.length + 1,
      duration_minutes: 60,
      scheduled_at: '',
    }
  }
  eventDialog.value = true
}

const saveEvent = async () => {
  try {
    if (editingEvent.value.id) {
      await api.put(`/events/${editingEvent.value.id}`, editingEvent.value)
      ElMessage.success('更新成功')
    } else {
      await api.post(`/deliveries/${route.params.id}/events`, editingEvent.value)
      ElMessage.success('添加成功')
    }
    eventDialog.value = false
    fetchEvents()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const deleteEvent = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该事件吗？', '提示', { type: 'warning' })
    await api.delete(`/events/${id}`)
    ElMessage.success('删除成功')
    fetchEvents()
  } catch {
    // cancelled
  }
}

onMounted(() => {
  fetchDetail()
  fetchEvents()
  fetchResumes()
  fetchTagSuggestions()
})
</script>

<template>
  <div v-loading="loading" class="detail-page">
    <div class="detail-header">
      <el-button text :icon="ArrowLeft" @click="router.back()">返回</el-button>
      <h2>{{ delivery?.company }} - {{ delivery?.position }}</h2>
      <span v-if="delivery?.created_at" class="detail-time">创建于 {{ formatDateTime(delivery.created_at) }}</span>
    </div>

    <div class="detail-body">
      <div class="detail-left">
        <el-card class="info-card">
          <template #header>
            <div class="card-header">
              <span>基本信息</span>
              <el-button type="primary" size="small" @click="saveDelivery">保存</el-button>
            </div>
          </template>
          <el-form label-width="80px">
            <el-form-item label="公司">
              <el-input v-model="delivery!.company" />
            </el-form-item>
            <el-form-item label="岗位">
              <el-input v-model="delivery!.position" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="delivery!.status" style="width: 100%">
                <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="标签">
              <el-select-v2
                v-model="delivery!.tags"
                :options="tagOptions"
                allow-create
                multiple
                filterable
                placeholder="选择或输入新标签"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="链接">
              <el-input v-model="delivery!.link" />
            </el-form-item>
            <el-form-item label="JD描述">
              <el-input v-model="delivery!.jd_text" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item label="简历">
              <el-select v-model="delivery!.resume_id" placeholder="选择简历（可选）" clearable style="width: 100%">
                <el-option v-for="r in resumes" :key="r.id" :label="r.name" :value="r.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="截止日期">
              <el-date-picker
                v-model="delivery!.deadline"
                type="datetime"
                placeholder="选择截止日期（可选）"
                style="width: 100%"
                value-format="YYYY-MM-DDTHH:mm"
                clearable
              />
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <div class="detail-right">
        <el-card class="events-card">
          <template #header>
            <div class="card-header">
              <span>事件时间线</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openEventDialog()">添加事件</el-button>
            </div>
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="evt in events"
              :key="evt.id"
              :type="evt.event_type === 'interview' ? 'primary' : evt.event_type === 'written' ? 'warning' : 'info'"
              :icon="evt.event_type === 'interview' ? ChatDotRound : evt.event_type === 'written' ? Document : Timer"
            >
              <div class="event-item">
                <div class="event-header">
                  <span class="event-type">{{ EVENT_TYPE_LABEL_MAP[evt.event_type] || evt.event_type }}</span>
                  <span class="event-round">第{{ evt.round_number }}轮</span>
                  <el-button text size="small" :icon="Edit" @click="openEventDialog(evt)" />
                  <el-button text size="small" type="danger" :icon="Delete" @click="deleteEvent(evt.id)" />
                </div>
                <div class="event-time">{{ formatDateTime(evt.scheduled_at) }} · {{ evt.duration_minutes }}分钟</div>
                <div v-if="evt.interviewer" class="event-meta">面试官：{{ evt.interviewer }}</div>
                <div v-if="evt.location" class="event-meta">地点：{{ evt.location }}</div>
                <div v-if="evt.meeting_link" class="event-meta">
                  会议：<a :href="evt.meeting_link" target="_blank">{{ evt.meeting_link }}</a>
                </div>
                <div v-if="evt.notes" class="event-notes">{{ evt.notes }}</div>
              </div>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-if="events.length === 0" description="暂无事件" />
        </el-card>
      </div>
    </div>

    <el-dialog v-model="eventDialog" :title="editingEvent.id ? '编辑事件' : '添加事件'" width="500px">
      <el-form label-width="80px">
        <el-form-item label="类型">
          <el-select v-model="editingEvent.event_type" style="width: 100%">
            <el-option v-for="o in EVENT_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="轮次">
          <el-input-number v-model="editingEvent.round_number" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker
            v-model="editingEvent.scheduled_at"
            type="datetime"
            placeholder="选择日期时间"
            style="width: 100%"
            value-format="YYYY-MM-DDTHH:mm"
          />
        </el-form-item>
        <el-form-item label="时长">
          <el-input-number v-model="editingEvent.duration_minutes" :min="15" :step="15" style="width: 100%" />
        </el-form-item>
        <el-form-item label="地点">
          <el-input v-model="editingEvent.location" placeholder="面试地点" />
        </el-form-item>
        <el-form-item label="会议链接">
          <el-input v-model="editingEvent.meeting_link" placeholder="腾讯会议/Zoom链接" />
        </el-form-item>
        <el-form-item label="面试官">
          <el-input v-model="editingEvent.interviewer" placeholder="面试官姓名" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editingEvent.notes" type="textarea" :rows="3" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="eventDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-page {
  height: 100%;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.detail-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1e3a5f;
}

.detail-time {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
}

.detail-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.event-item {
  padding: 8px 0;
}

.event-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 6px;
}

.event-type {
  font-weight: 600;
  color: #1e3a5f;
}

.event-round {
  font-size: 12px;
  color: #f59e0b;
  background: #fef3c7;
  padding: 2px 8px;
  border-radius: 4px;
}

.event-time {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 4px;
}

.event-meta {
  font-size: 13px;
  color: #64748b;
}

.event-notes {
  margin-top: 8px;
  padding: 8px;
  background: #f8fafc;
  border-radius: 6px;
  font-size: 13px;
  color: #475569;
}

@media (max-width: 768px) {
  .detail-body {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}
</style>
