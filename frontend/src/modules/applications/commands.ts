/**
 * applications 模块 — 写操作封装
 *
 * 所有投递相关的变更操作（创建、更新、删除、批量操作、事件 CRUD、备注 CRUD、CSV 导入）。
 * UI 组件应通过此模块提交数据，禁止直接调用 api 实例。
 */

import api from '@/lib/api'
import type {
  BatchDeleteInput,
  BatchStatusUpdateInput,
  BatchTagUpdateInput,
  Delivery,
  DeliveryCreateInput,
  DeliveryNote,
  DeliveryNoteCreateInput,
  DeliveryUpdateInput,
  ImportPreviewResponse,
  ImportResult,
  InterviewEvent,
  InterviewEventCreateInput,
  InterviewEventUpdateInput,
} from './types'

// ─── 投递 CRUD ───

/** 创建投递 */
export async function createDelivery(data: DeliveryCreateInput): Promise<Delivery> {
  const res = await api.post('/deliveries', data)
  return res.data
}

/** 更新投递（支持部分字段更新） */
export async function updateDelivery(
  deliveryId: number,
  data: DeliveryUpdateInput,
): Promise<Delivery> {
  const res = await api.put(`/deliveries/${deliveryId}`, data)
  return res.data
}

/** 更新投递状态（拖拽看板时的快捷操作） */
export async function updateDeliveryStatus(
  deliveryId: number,
  status: string,
): Promise<Delivery> {
  return updateDelivery(deliveryId, { status })
}

/** 删除投递（含级联删除关联事件、日志、备注、复盘） */
export async function deleteDelivery(deliveryId: number): Promise<void> {
  await api.delete(`/deliveries/${deliveryId}`)
}

// ─── 批量操作 ───

/** 批量更新投递状态 */
export async function batchUpdateStatus(data: BatchStatusUpdateInput): Promise<number> {
  const res = await api.put('/deliveries/batch/status', data)
  return res.data.updated
}

/** 批量添加/移除标签 */
export async function batchUpdateTags(data: BatchTagUpdateInput): Promise<number> {
  const res = await api.put('/deliveries/batch/tags', data)
  return res.data.updated
}

/** 批量删除投递 */
export async function batchDelete(data: BatchDeleteInput): Promise<number> {
  const res = await api.delete('/deliveries/batch', { data })
  return res.data.deleted
}

// ─── 面试事件 CRUD ───

/** 为指定投递创建面试事件 */
export async function createEvent(
  deliveryId: number,
  data: InterviewEventCreateInput,
): Promise<InterviewEvent> {
  const res = await api.post(`/deliveries/${deliveryId}/events`, data)
  return res.data
}

/** 更新面试事件 */
export async function updateEvent(
  eventId: number,
  data: InterviewEventUpdateInput,
): Promise<InterviewEvent> {
  const res = await api.put(`/events/${eventId}`, data)
  return res.data
}

/** 删除面试事件 */
export async function deleteEvent(eventId: number): Promise<void> {
  await api.delete(`/events/${eventId}`)
}

// ─── 备注 CRUD ───

/** 创建投递备注 */
export async function createNote(
  deliveryId: number,
  data: DeliveryNoteCreateInput,
): Promise<DeliveryNote> {
  const res = await api.post(`/deliveries/${deliveryId}/notes`, data)
  return res.data
}

/** 更新投递备注 */
export async function updateNote(
  deliveryId: number,
  noteId: number,
  content: string,
): Promise<DeliveryNote> {
  const res = await api.put(`/deliveries/${deliveryId}/notes/${noteId}`, { content })
  return res.data
}

/** 删除投递备注 */
export async function deleteNote(deliveryId: number, noteId: number): Promise<void> {
  await api.delete(`/deliveries/${deliveryId}/notes/${noteId}`)
}

// ─── CSV 导入 ───

/** 预览 CSV 文件内容（返回前 20 行及自动映射的表头） */
export async function previewCsvImport(file: File): Promise<ImportPreviewResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post('/deliveries/import/preview', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

/** 正式导入 CSV 文件（可传入自定义列映射） */
export async function importCsv(
  file: File,
  mapping?: Record<string, string>,
): Promise<ImportResult> {
  const formData = new FormData()
  formData.append('file', file)
  if (mapping) {
    formData.append('mapping', JSON.stringify(mapping))
  }
  const res = await api.post('/deliveries/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}
