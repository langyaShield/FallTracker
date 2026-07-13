<script setup lang="ts">
import type { InterviewEvent } from '@/modules/applications/types'
import { EVENT_TYPE_OPTIONS } from '@/lib/constants'
import {
  ElDialog,
  ElForm,
  ElFormItem,
  ElSelect,
  ElOption,
  ElInputNumber,
  ElDatePicker,
  ElInput,
  ElButton,
} from 'element-plus'

defineProps<{
  modelValue: boolean
  editingEvent: Partial<InterviewEvent>
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
  save: []
}>()
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="editingEvent.id ? '编辑事件' : '添加事件'"
    width="500px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
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
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="$emit('save')">保存</el-button>
    </template>
  </el-dialog>
</template>
