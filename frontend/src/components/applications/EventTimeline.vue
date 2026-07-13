<script setup lang="ts">
import type { InterviewEvent } from '@/modules/applications/types'
import { EVENT_TYPE_OPTIONS, EVENT_TYPE_LABEL_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import {
  ElTimeline,
  ElTimelineItem,
  ElForm,
  ElFormItem,
  ElSelect,
  ElOption,
  ElInputNumber,
  ElDatePicker,
  ElInput,
  ElButton,
  ElEmpty,
  ElCard,
} from 'element-plus'
import { ChatDotRound, Document, Timer, Edit, Delete, Plus } from '@element-plus/icons-vue'

defineProps<{
  events: InterviewEvent[]
  inlineEditingEventId: number | null
  inlineEventForm: Partial<InterviewEvent>
}>()

defineEmits<{
  'start-inline-edit': [event: InterviewEvent]
  'cancel-inline-edit': []
  'save-inline-event': []
  'delete-event': [id: number]
  'open-event-dialog': [event?: InterviewEvent]
}>()
</script>

<template>
  <el-card class="events-card">
    <template #header>
      <div class="card-header">
        <span>事件时间线</span>
        <el-button type="primary" size="small" :icon="Plus" @click="$emit('open-event-dialog')">添加事件</el-button>
      </div>
    </template>
    <el-timeline>
      <el-timeline-item
        v-for="evt in events"
        :key="evt.id"
        :type="evt.event_type === 'interview' ? 'primary' : evt.event_type === 'written' ? 'warning' : 'info'"
        :icon="evt.event_type === 'interview' ? ChatDotRound : evt.event_type === 'written' ? Document : Timer"
      >
        <div v-if="inlineEditingEventId === evt.id" class="event-inline-form">
          <el-form label-width="70px" size="small">
            <el-form-item label="类型">
              <el-select v-model="inlineEventForm.event_type" style="width: 100%">
                <el-option v-for="o in EVENT_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="轮次">
              <el-input-number v-model="inlineEventForm.round_number" :min="1" style="width: 100%" />
            </el-form-item>
            <el-form-item label="时间">
              <el-date-picker
                v-model="inlineEventForm.scheduled_at"
                type="datetime"
                placeholder="选择日期时间"
                style="width: 100%"
                value-format="YYYY-MM-DDTHH:mm"
              />
            </el-form-item>
            <el-form-item label="时长">
              <el-input-number v-model="inlineEventForm.duration_minutes" :min="15" :step="15" style="width: 100%" />
            </el-form-item>
            <el-form-item label="地点">
              <el-input v-model="inlineEventForm.location" placeholder="面试地点" />
            </el-form-item>
            <el-form-item label="会议">
              <el-input v-model="inlineEventForm.meeting_link" placeholder="腾讯会议/Zoom链接" />
            </el-form-item>
            <el-form-item label="面试官">
              <el-input v-model="inlineEventForm.interviewer" placeholder="面试官姓名" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="inlineEventForm.notes" type="textarea" :rows="2" placeholder="备注信息" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="small" @click="$emit('save-inline-event')">保存</el-button>
              <el-button size="small" @click="$emit('cancel-inline-edit')">取消</el-button>
            </el-form-item>
          </el-form>
        </div>
        <div v-else class="event-item">
          <div class="event-header">
            <span class="event-type">{{ EVENT_TYPE_LABEL_MAP[evt.event_type] || evt.event_type }}</span>
            <span class="event-round">第{{ evt.round_number }}轮</span>
            <el-button text size="small" :icon="Edit" aria-label="编辑事件" @click="$emit('start-inline-edit', evt)" />
            <el-button text size="small" type="danger" :icon="Delete" aria-label="删除事件" @click="$emit('delete-event', evt.id)" />
          </div>
          <div class="event-time">{{ formatDateTime(evt.scheduled_at) }} · {{ evt.duration_minutes }}分钟</div>
          <div v-if="evt.interviewer" class="event-meta">面试官：{{ evt.interviewer }}</div>
          <div v-if="evt.location" class="event-meta">地点：{{ evt.location }}</div>
          <div v-if="evt.meeting_link" class="event-meta">
            会议：<a :href="evt.meeting_link" target="_blank" rel="noopener noreferrer">{{ evt.meeting_link }}</a>
          </div>
          <div v-if="evt.notes" class="event-notes">{{ evt.notes }}</div>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-if="events.length === 0" description="暂无事件" />
  </el-card>
</template>

<style scoped>
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

.event-inline-form {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  margin: 4px 0 8px;
}
</style>
