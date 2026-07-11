<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus, Calendar } from '@element-plus/icons-vue'
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
  // 去重：按 (delivery_id, event_type, start) 去重，避免面试事件与 deadline 事件视觉重复
  const seen = new Set<string>()
  return all.filter(e => {
    const key = `${e.extendedProps.delivery_id}|${e.extendedProps.event_type}|${e.start}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const currentDate = ref(new Date())
const viewMode = ref<'month' | 'week'>('month')
const loading = ref(true)  // 初始为 true，防止空状态闪现
const dataReady = ref(false)  // 首次数据加载完成后才渲染内容
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')
const editingEvent = ref<Partial<CalendarEvent> & { id?: number; scheduled_at?: string; duration_minutes?: number; delivery_id?: number; event_type?: string; round_number?: number; location?: string; meeting_link?: string; interviewer?: string; notes?: string }>({})
const deliveries = ref<{ id: number; company: string; position: string }[]>([])

const isCurrentMonth = computed(() => {
  const now = new Date()
  return currentDate.value.getFullYear() === now.getFullYear() && currentDate.value.getMonth() === now.getMonth()
})

const weekRange = computed(() => {
  const start = new Date(currentDate.value)
  start.setDate(start.getDate() - start.getDay())
  const end = new Date(start)
  end.setDate(end.getDate() + 6)
  return { start, end }
})

const weekEvents = computed(() => {
  const { start, end } = weekRange.value
  const startTs = new Date(start.getFullYear(), start.getMonth(), start.getDate(), 0, 0, 0).getTime()
  const endTs = new Date(end.getFullYear(), end.getMonth(), end.getDate(), 23, 59, 59, 999).getTime()
  return calendarEvents.value
    .filter((e) => {
      const es = new Date(e.start).getTime()
      return es >= startTs && es <= endTs
    })
    .sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime())
})

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
  } catch (e: unknown) {
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
  } catch (e) {
    console.warn('日历投递数据加载失败', e)
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

// 预计算每天的事件，避免模板中 O(n*m) 重复过滤
const eventsByDay = computed(() => {
  const map: Record<number, CalendarEvent[]> = {}
  const year = currentDate.value.getFullYear()
  const month = currentDate.value.getMonth()
  for (const evt of calendarEvents.value) {
    const d = new Date(evt.start)
    // 仅当事件属于当前展示的月份时才加入
    if (d.getFullYear() === year && d.getMonth() === month) {
      const day = d.getDate()
      if (!map[day]) map[day] = []
      map[day].push(evt)
    }
  }
  return map
})

const getEventsForDay = (day: number | null) => {
  if (day === null) return []
  return eventsByDay.value[day] || []
}

const prevMonth = () => {
  currentDate.value = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth() - 1, 1)
}

const nextMonth = () => {
  currentDate.value = new Date(currentDate.value.getFullYear(), currentDate.value.getMonth() + 1, 1)
}

const goToToday = () => {
  currentDate.value = new Date()
}

const openAdd = (initialDate?: string) => {
  dialogMode.value = 'create'
  editingEvent.value = {
    scheduled_at: initialDate || '',
    duration_minutes: 60,
    event_type: 'interview',
  }
  dialogVisible.value = true
}

const openEdit = async (evt: CalendarEvent) => {
  if (evt.extendedProps.event_type === 'deadline') {
    // 截止日期是投递属性，跳转到投递详情编辑
    router.push(`/delivery/${evt.extendedProps.delivery_id}`)
    return
  }
  dialogMode.value = 'edit'
  try {
    const res = await api.get(`/events/${evt.id}`)
    const data = res.data || {}
    editingEvent.value = {
      id: data.id,
      delivery_id: data.delivery_id,
      event_type: data.event_type || 'interview',
      round_number: data.round_number || 1,
      scheduled_at: data.scheduled_at ? data.scheduled_at.slice(0, 16) : '',
      duration_minutes: data.duration_minutes || 60,
      location: data.location || '',
      meeting_link: data.meeting_link || '',
      interviewer: data.interviewer || '',
      notes: data.notes || '',
    }
    dialogVisible.value = true
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取事件详情失败'))
  }
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
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '导出失败'))
  }
}

const saveEvent = async () => {
  // 表单校验
  if (dialogMode.value === 'create' && !editingEvent.value.delivery_id) {
    ElMessage.warning('请选择投递')
    return
  }
  if (!editingEvent.value.scheduled_at) {
    ElMessage.warning('请选择时间')
    return
  }
  if (!editingEvent.value.event_type) {
    ElMessage.warning('请选择事件类型')
    return
  }

  try {
    const payload = {
      event_type: editingEvent.value.event_type || 'interview',
      round_number: editingEvent.value.round_number || 1,
      scheduled_at: editingEvent.value.scheduled_at,
      duration_minutes: editingEvent.value.duration_minutes || 60,
      location: editingEvent.value.location || undefined,
      meeting_link: editingEvent.value.meeting_link || undefined,
      interviewer: editingEvent.value.interviewer || undefined,
      notes: editingEvent.value.notes || undefined,
    }
    if (dialogMode.value === 'edit' && editingEvent.value.id) {
      await api.put(`/events/${editingEvent.value.id}`, payload)
      ElMessage.success('更新成功')
    } else {
      await api.post(`/deliveries/${editingEvent.value.delivery_id}/events`, payload)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    fetchEvents()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const goToDelivery = (deliveryId: number) => {
  router.push(`/delivery/${deliveryId}`)
}

onMounted(() => {
  interviewEvents.value = []
  deadlineEvents.value = []
  const startTime = Date.now()
  Promise.all([fetchEvents(), fetchDeliveries()]).finally(() => {
    // 确保加载状态至少显示 300ms，避免闪现
    const elapsed = Date.now() - startTime
    const delay = Math.max(0, 300 - elapsed)
    setTimeout(() => {
      dataReady.value = true
    }, delay)
  })
})
</script>

<template>
  <div class="calendar-page">
    <!-- 首次加载中，不渲染任何内容避免闪现 -->
    <div v-if="!dataReady" v-loading="true" style="min-height: 300px" />

    <div v-if="dataReady">
    <PageHeader title="日历视图">
      <el-button-group>
        <el-button :icon="ArrowLeft" aria-label="上一月" @click="prevMonth" />
        <el-button>{{ currentDate.getFullYear() }}年{{ currentDate.getMonth() + 1 }}月</el-button>
        <el-button :icon="ArrowRight" aria-label="下一月" @click="nextMonth" />
      </el-button-group>
      <el-button v-if="!isCurrentMonth" :icon="Calendar" @click="goToToday">今天</el-button>
      <el-button-group>
        <el-button :type="viewMode === 'month' ? 'primary' : 'default'" @click="viewMode = 'month'">月</el-button>
        <el-button :type="viewMode === 'week' ? 'primary' : 'default'" @click="viewMode = 'week'">周</el-button>
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
    <div v-if="upcomingAlerts.length > 0" class="interview-alerts">
      <el-alert
        v-for="(alert, idx) in upcomingAlerts.slice(0, 3)"
        :key="idx"
        :title="alert.title"
        :description="alert.body"
        type="warning"
        :closable="false"
        show-icon
        class="interview-alert"
      />
      <el-alert
        v-if="upcomingAlerts.length > 3"
        :title="`还有 ${upcomingAlerts.length - 3} 场面试即将开始`"
        type="info"
        :closable="false"
        show-icon
        class="interview-alert"
      />
    </div>

    <el-empty
      v-if="!loading && interviewEvents.length === 0 && deadlineEvents.length === 0"
      description="本月暂无面试或截止日期"
      :image-size="100"
    >
      <el-button type="primary" @click="openAdd">新建第一个事件</el-button>
    </el-empty>

    <div v-else-if="viewMode === 'month'" class="calendar-grid" v-loading="loading">
      <div class="weekday-header" v-for="day in ['日', '一', '二', '三', '四', '五', '六']" :key="day">{{ day }}</div>
      <div
        v-for="(day, idx) in calendarDays"
        :key="idx"
        class="calendar-day"
        :class="{ 'other-month': !day, 'is-today': day === new Date().getDate() && isCurrentMonth }"
        @click="day ? openAdd(`${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}T00:00`) : null"
      >
        <div v-if="day" class="day-number">{{ day }}</div>
        <div class="day-events">
          <div
            v-for="evt in getEventsForDay(day)"
            :key="evt.id"
            class="event-chip"
            :class="{ 'deadline-chip': evt.extendedProps.event_type === 'deadline' }"
            :style="{ backgroundColor: evt.color + '20', color: evt.color, borderColor: evt.color }"
            @click.stop="openEdit(evt)"
          >
            {{ evt.title }}
          </div>
        </div>
      </div>
    </div>

    <!-- 周视图 -->
    <div v-else class="week-view" v-loading="loading">
      <div class="week-header">
        {{ weekRange.start.getMonth() + 1 }}月{{ weekRange.start.getDate() }}日 -
        {{ weekRange.end.getMonth() + 1 }}月{{ weekRange.end.getDate() }}日
      </div>
      <el-empty v-if="weekEvents.length === 0" description="本周暂无事件" />
      <div v-for="evt in weekEvents" :key="evt.id" class="week-event-item" @click="openEdit(evt)">
        <div class="week-event-dot" :style="{ backgroundColor: evt.color }" />
        <div class="week-event-info">
          <div class="week-event-title">{{ evt.title }}</div>
          <div class="week-event-time">{{ formatDateTime(evt.start) }}</div>
        </div>
        <el-button text size="small" type="primary" @click.stop="openEdit(evt)">编辑</el-button>
      </div>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogMode === 'edit' ? '编辑事件' : '新建事件'" width="500px">
      <el-form label-width="80px" @keyup.enter="saveEvent">
        <el-form-item label="投递">
          <el-select v-model="editingEvent.delivery_id" placeholder="选择投递" :disabled="dialogMode === 'edit'" style="width: 100%">
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
        <el-form-item label="轮次">
          <el-input-number v-model="editingEvent.round_number" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker v-model="editingEvent.scheduled_at" type="datetime" placeholder="选择日期时间" style="width: 100%" value-format="YYYY-MM-DDTHH:mm" />
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
          <el-input v-model="editingEvent.notes" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>
    </div>
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

.calendar-day.is-today .day-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: #3b82f6;
  color: #fff;
  border-radius: 50%;
}

.week-view {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.week-header {
  font-size: 16px;
  font-weight: 600;
  color: #1e3a5f;
  margin-bottom: 16px;
}

.week-event-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}

.week-event-item:hover {
  background: #f8fafc;
}

.week-event-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.week-event-info {
  flex: 1;
}

.week-event-title {
  font-weight: 500;
  color: #1e3a5f;
}

.week-event-time {
  font-size: 13px;
  color: #64748b;
  margin-top: 2px;
}

.interview-alerts {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

@media (max-width: 768px) {
  .weekday-header {
    font-size: 12px;
    padding: 8px 2px;
  }

  .calendar-day {
    min-height: 60px;
    padding: 4px;
  }

  .day-number {
    font-size: 12px;
    font-weight: 500;
  }

  .event-chip {
    font-size: 10px;
    padding: 1px 3px;
    border-radius: 2px;
  }

  .calendar-legend {
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }
}
</style>
