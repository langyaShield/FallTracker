<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus, Download } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { EVENT_TYPE_LABEL_MAP, EVENT_TYPE_COLOR_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

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
const calendarEvents = computed(() => {
  const all = [...interviewEvents.value, ...deadlineEvents.value]
  // 去重：按 id 去重，避免同一条记录出现多次
  const seen = new Set<string>()
  return all.filter(e => {
    const key = String(e.id)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const currentDate = ref(new Date())
const loading = ref(false)
const dialogVisible = ref(false)
const editingEvent = ref<Partial<CalendarEvent> & { scheduled_at?: string; duration_minutes?: number; delivery_id?: number; event_type?: string }>({})
const deliveries = ref<{ id: number; company: string; position: string }[]>([])

const fetchEvents = async () => {
  loading.value = true
  try {
    const res = await api.get('/events')
    interviewEvents.value = (res.data || []).map((evt: any) => ({
      id: evt.id,
      title: `${evt.company || ''} ${EVENT_TYPE_LABEL_MAP[evt.event_type] || '其他'}`,
      start: evt.scheduled_at,
      end: new Date(new Date(evt.scheduled_at).getTime() + evt.duration_minutes * 60000).toISOString(),
      color: EVENT_TYPE_COLOR_MAP[evt.event_type] || '#94a3b8',
      extendedProps: {
        delivery_id: evt.delivery_id,
        event_type: evt.event_type,
        company: evt.company,
        position: evt.position,
      }
    }))
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取事件失败'))
  } finally {
    loading.value = false
  }
}

const fetchDeliveries = async () => {
  try {
    const res = await api.get('/deliveries')
    deliveries.value = (res.data || []).map((d: any) => ({ id: d.id, company: d.company, position: d.position }))
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
  } catch {
    // ignore
  }
}

const daysInMonth = (year: number, month: number) => new Date(year, month + 1, 0).getDate()
const firstDayOfMonth = (year: number, month: number) => new Date(year, month, 1).getDay()

// N-BUG-5: 24h 内面试提醒数据源
const upcomingAlerts = computed(() => {
  const now = Date.now()
  const horizon = now + 24 * 60 * 60 * 1000
  const upcoming: { title: string; body: string; scheduledAt: number }[] = []
  for (const evt of interviewEvents.value) {
    if (evt.extendedProps?.event_type === 'deadline') continue
    const ts = new Date(evt.start).getTime()
    if (ts >= now && ts <= horizon) {
      const hours = Math.floor((ts - now) / 3_600_000)
      const mins = Math.floor(((ts - now) % 3_600_000) / 60_000)
      const when = hours > 0 ? `${hours}小时${mins}分钟后` : `${mins}分钟后`
      upcoming.push({
        title: `📅 ${when} 即将开始: ${evt.title}`,
        body: `请提前 10 分钟进入面试环境并检查设备`,
        scheduledAt: ts,
      })
    }
  }
  return upcoming.sort((a, b) => a.scheduledAt - b.scheduledAt)
})

const hasDeadlines = computed(() => deadlineEvents.value.length > 0)

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

const getEventsForDay = (day: number | null) => {
  if (day === null) return []
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

/** T1-3: 触发 iCal 文件下载 */
const exportIcs = async () => {
  try {
    const res = await api.get('/events/export.ics', { responseType: 'blob' })
    const blob = new Blob([res.data], { type: 'text/calendar' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'falltracker-interviews.ics'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 iCal 文件，可导入 Google / Apple / Outlook 日历')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '导出失败'))
  }
}

const saveEvent = async () => {
  try {
    await api.post(`/deliveries/${editingEvent.value.delivery_id}/events`, {
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
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const goToDelivery = (deliveryId: number) => {
  router.push(`/delivery/${deliveryId}`)
}

onMounted(() => {
  interviewEvents.value = []
  deadlineEvents.value = []
  fetchEvents()
  fetchDeliveries()
})
</script>

<template>
  <div class="calendar-page">
    <PageHeader title="日历视图">
      <el-button-group>
        <el-button :icon="ArrowLeft" @click="prevMonth" />
        <el-button>{{ currentDate.getFullYear() }}年{{ currentDate.getMonth() + 1 }}月</el-button>
        <el-button :icon="ArrowRight" @click="nextMonth" />
      </el-button-group>
      <el-button type="primary" :icon="Plus" @click="openAdd">新建事件</el-button>
    </PageHeader>

    <div class="calendar-legend">
      <span class="legend-item"><span class="legend-dot" style="background-color: #3b82f6"></span>面试</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #8b5cf6"></span>笔试</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #f59e0b"></span>HR面</span>
      <span class="legend-item"><span class="legend-dot" style="background-color: #ef4444"></span>截止日期</span>
    </div>

    <!-- N-BUG-5: 24h 内面试提醒条（顶部醒目提示，避免错过面试） -->
    <el-alert
      v-if="upcomingAlerts.length > 0"
      :title="upcomingAlerts[0].title"
      :description="upcomingAlerts[0].body"
      type="warning"
      :closable="false"
      show-icon
      class="interview-alert"
    />

    <el-empty
      v-if="!loading && interviewEvents.length === 0 && deadlineEvents.length === 0"
      description="本月暂无面试或截止日期"
      :image-size="100"
    >
      <el-button type="primary" @click="openAdd">新建第一个事件</el-button>
    </el-empty>

    <div v-else class="calendar-grid">
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
            v-for="evt in getEventsForDay(day)"
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
            <el-option
              v-for="(label, value) in EVENT_TYPE_LABEL_MAP"
              :key="value"
              :label="label"
              :value="value"
            />
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
