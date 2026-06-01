<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus } from '@element-plus/icons-vue'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'
const router = useRouter()

interface CalendarEvent {
  id: string | number
  title: string
  start: string
  end: string
  color: string
  extendedProps: {
    delivery_id: number
    event_type: string
    company: string
    position: string
  }
}

const interviewEvents = ref<CalendarEvent[]>([])
const deadlineEvents = ref<CalendarEvent[]>([])
const calendarEvents = computed(() => [...interviewEvents.value, ...deadlineEvents.value])
const currentDate = ref(new Date())
const viewMode = ref<'month' | 'week'>('month')
const dialogVisible = ref(false)
const editingEvent = ref<Partial<CalendarEvent> & { scheduled_at?: string; duration_minutes?: number; delivery_id?: number; event_type?: string }>({})
const deliveries = ref<{ id: number; company: string; position: string }[]>([])

const fetchEvents = async () => {
  try {
    const res = await axios.get(`${API_BASE}/events`)
    interviewEvents.value = (res.data || []).map((evt: any) => ({
      id: evt.id,
      title: `${evt.company || ''} ${evt.event_type === 'written' ? '笔试' : evt.event_type === 'interview' ? '面试' : evt.event_type === 'hr' ? 'HR面' : '其他'}`,
      start: evt.scheduled_at,
      end: new Date(new Date(evt.scheduled_at).getTime() + evt.duration_minutes * 60000).toISOString(),
      color: evt.event_type === 'interview' ? '#3b82f6' : evt.event_type === 'written' ? '#8b5cf6' : evt.event_type === 'hr' ? '#f59e0b' : '#94a3b8',
      extendedProps: {
        delivery_id: evt.delivery_id,
        event_type: evt.event_type,
        company: evt.company,
        position: evt.position,
      }
    }))
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取事件失败')
  }
}

const fetchDeliveries = async () => {
  try {
    const res = await axios.get(`${API_BASE}/deliveries`)
    deliveries.value = (res.data || []).map((d: any) => ({ id: d.id, company: d.company, position: d.position }))
    // Build deadline events from deliveries that have a deadline
    deadlineEvents.value = (res.data || [])
      .filter((d: any) => d.deadline)
      .map((d: any) => ({
        id: `dl-${d.id}`,
        title: `[Deadline] ${d.company} - ${d.position}`,
        start: d.deadline,
        end: d.deadline,
        color: '#ef4444',
        extendedProps: {
          delivery_id: d.id,
          event_type: 'deadline',
          company: d.company,
          position: d.position,
        }
      }))
  } catch (e: any) {
    // ignore
  }
}

const daysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate()
const firstDayOfMonth = (year: number, month: number) => new Date(year, month, 1).getDay()

const calendarDays = computed(() => {
  const year = currentDate.value.getFullYear()
  const month = currentDate.value.getMonth()
  const days = daysInMonth(year, month)
  const firstDay = firstDayOfMonth(year, month)
  const result = []
  for (let i = 0; i < firstDay; i++) result.push(null)
  for (let i = 1; i <= days; i++) result.push(i)
  return result
})

const getEventsForDay = (day: number) => {
  const year = currentDate.value.getFullYear()
  const month = currentDate.value.getMonth()
  const start = new Date(year, month, day, 0, 0, 0)
  const end = new Date(year, month, day, 23, 59, 59)
  return calendarEvents.value.filter((e) => {
    const es = new Date(e.start)
    return es >= start && es <= end
  })
}

const prevMonth = () => {
  currentDate.value = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth() - 1, 1)
}

const nextMonth = () => {
  currentDate.value = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth() + 1, 1)
}

const openAdd = () => {
  editingEvent.value = { scheduled_at: '', duration_minutes: 60 }
  dialogVisible.value = true
}

const saveEvent = async () => {
  try {
    await axios.post(`${API_BASE}/deliveries/${editingEvent.value.delivery_id}/events`, {
      event_type: editingEvent.value.event_type || 'interview',
      round_number: 1,
      scheduled_at: editingEvent.value.scheduled_at,
      duration_minutes: editingEvent.value.duration_minutes || 60,
      notes: editingEvent.value.title,
    })
    ElMessage.success('添加成功')
    dialogVisible.value = false
    fetchEvents()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

const goToDelivery = (deliveryId: number) => {
  router.push(`/delivery/${deliveryId}`)
}

onMounted(() => {
  fetchEvents()
  fetchDeliveries()
})
</script>

<template>
  <div class="calendar-page">
    <div class="page-header">
      <h2>日历视图</h2>
      <div class="header-actions">
        <el-button-group>
          <el-button :icon="ArrowLeft" @click="prevMonth" />
          <el-button>{{ currentDate.getFullYear() }}年{{ currentDate.getMonth() + 1 }}月</el-button>
          <el-button :icon="ArrowRight" @click="nextMonth" />
        </el-button-group>
        <el-button type="primary" :icon="Plus" @click="openAdd">新建事件</el-button>
      </div>
    </div>

    <div class="calendar-legend">
      <span class="legend-item"><span class="legend-dot" style="background-color: #3b82f6"></span>面试</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #8b5cf6"></span>笔试</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #f59e0b"></span>HR面</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #ef4444"></span>截止日期</span>
    </div>

    <div class="calendar-grid">
      <div class="weekday-header" v-for="day in ['日', '一', '二', '三', '四', '五', '六']" :key="day">{{ day }}</div>
      <div
        v-for="(day, idx) in calendarDays"
        :key="idx"
        class="calendar-day"
        :class="{ 'other-month': !day }"
      >
        <div v-if="day" class="day-number">{{ day }}</div>
        <div class="day-events">
          <div
            v-for="evt in getEventsForDay(day || 0)"
            :key="evt.id"
            class="event-chip"
            :class="{ 'deadline-chip': evt.extendedProps.event_type === 'deadline' }"
            :style="{ backgroundColor: evt.color + '20', color: evt.color, borderColor: evt.color }"
            @click="goToDelivery(evt.extendedProps.delivery_id)"
          >
            {{ evt.title }}
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" title="新建事件" width="500px">
      <el-form label-width="80px">
        <el-form-item label="投递">
          <el-select v-model="editingEvent.delivery_id" placeholder="选择投递" style="width: 100%">
            <el-option v-for="d in deliveries" :key="d.id" :label="`${d.company} - ${d.position}`" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="editingEvent.event_type" style="width: 100%">
            <el-option label="笔试" value="written" />
            <el-option label="面试" value="interview" />
            <el-option label="HR面" value="hr" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="editingEvent.scheduled_at" type="datetime" placeholder="选择日期时间" style="width: 100%" value-format="YYYY-MM-DDTHH:mm" />
        </el-form-item>
        <el-form-item label="时长">
          <el-input-number v-model="editingEvent.duration_minutes" :min="15" :step="15" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.calendar-page {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #1e3a5f;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.calendar-legend {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #64748b;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 1px;
  background: #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
}

.weekday-header {
  background: #1e3a5f;
  color: #fff;
  text-align: center;
  padding: 12px;
  font-weight: 600;
  font-size: 14px;
}

.calendar-day {
  background: #fff;
  min-height: 120px;
  padding: 8px;
  position: relative;
}

.calendar-day.other-month {
  background: #f8fafc;
}

.day-number {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 4px;
}

.day-events {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.event-chip {
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.deadline-chip {
  font-weight: 600;
  border-style: dashed;
}
</style>
