<script setup lang="ts">
import type { Delivery } from '@/modules/applications/types'
import { formatDateTime, getDeadlineUrgency } from '@/lib/format'
import { ElCheckbox, ElButton, ElTag } from 'element-plus'

defineProps<{
  item: Delivery
  batchMode: boolean
  selected: boolean
  highlighted: boolean
}>()

const emit = defineEmits<{
  click: [item: Delivery]
  delete: [item: Delivery]
  toggleSelect: [id: number]
  dragstart: [event: DragEvent, item: Delivery]
  dragend: [event: DragEvent]
}>()

function urgencyBorderColor(urgency: string): string {
  if (urgency === 'expired') return '#991b1b'
  if (urgency === 'urgent') return '#ef4444'
  if (urgency === 'warning') return '#f97316'
  return 'transparent'
}
</script>

<template>
  <div
    class="kanban-card"
    :class="{
      'card-urgent': getDeadlineUrgency(item.deadline) === 'urgent',
      'card-warning': getDeadlineUrgency(item.deadline) === 'warning',
      'card-expired': getDeadlineUrgency(item.deadline) === 'expired',
      'card-selected': selected,
      'card-highlighted': highlighted,
    }"
    :style="{ borderLeftColor: urgencyBorderColor(getDeadlineUrgency(item.deadline)) }"
    draggable="true"
    tabindex="0"
    role="button"
    :aria-label="`${item.company} - ${item.position}`"
    @click.stop="emit('click', item)"
    @keydown.enter.prevent="emit('click', item)"
    @keydown.space.prevent="emit('click', item)"
    @dragstart="emit('dragstart', $event, item)"
    @dragend="emit('dragend', $event)"
  >
    <div class="card-top-row">
      <el-checkbox
        v-if="batchMode"
        :model-value="selected"
        @click.stop
        @change="emit('toggleSelect', item.id)"
        class="batch-checkbox"
      />
      <div class="card-header">
        <span class="company">{{ item.company }}</span>
        <el-button
          v-if="!batchMode"
          text
          size="small"
          type="danger"
          @click.stop="emit('delete', item)"
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
</template>

<style scoped>
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

@media (max-width: 768px) {
  .kanban-card {
    padding: 10px;
  }
}
</style>
