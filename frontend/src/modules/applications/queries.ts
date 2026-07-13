/**
 * applications 模块 — 读操作封装
 *
 * 所有投递相关的只读 API 调用（列表、详情、事件、标签、导出等）。
 * UI 组件应通过此模块获取数据，禁止直接调用 api 实例。
 */

import api from '@/lib/api'
import type {
  Delivery,
  DeliveryListParams,
  DeliveryLog,
  DeliveryNote,
  InterviewEvent,
  ResumeOption,
  TagCount,
} from './types'

/** 获取投递列表（支持搜索、过滤、排序） */
export async function fetchDeliveries(params: DeliveryListParams = {}): Promise<Delivery[]> {
  const res = await api.get('/deliveries', { params })
  return res.data || []
}

/** 获取单个投递详情 */
export async function getDelivery(deliveryId: number): Promise<Delivery> {
  const res = await api.get(`/deliveries/${deliveryId}`)
  return res.data
}

/** 获取未来 N 天内有截止日期的投递（按紧迫度排序） */
export async function fetchUpcomingDeadlines(days = 7): Promise<Delivery[]> {
  const res = await api.get('/deliveries/upcoming-deadlines', { params: { days } })
  return res.data || []
}

/** 获取当前用户所有投递中使用过的标签及其出现次数（按次数降序） */
export async function fetchTagCounts(): Promise<TagCount[]> {
  const res = await api.get('/deliveries/tags')
  return res.data || []
}

/** 获取某投递下的所有面试事件（按时间排序） */
export async function fetchEvents(deliveryId: number): Promise<InterviewEvent[]> {
  const res = await api.get(`/deliveries/${deliveryId}/events`)
  return res.data || []
}

/** 获取某投递的活动日志（按时间倒序） */
export async function fetchDeliveryLogs(deliveryId: number): Promise<DeliveryLog[]> {
  const res = await api.get(`/deliveries/${deliveryId}/logs`)
  return res.data || []
}

/** 获取某投递的所有备注（按时间倒序） */
export async function fetchDeliveryNotes(deliveryId: number): Promise<DeliveryNote[]> {
  const res = await api.get(`/deliveries/${deliveryId}/notes`)
  return res.data || []
}

/** 获取简历列表（用于投递关联简历的选择器） */
export async function fetchResumeOptions(): Promise<ResumeOption[]> {
  const res = await api.get('/resumes')
  return res.data?.items || []
}

/** 从全量投递中聚合出已使用的标签（用于标签建议） */
export async function fetchTagSuggestionsFromDeliveries(): Promise<string[]> {
  const res = await api.get('/deliveries')
  const allTags = new Set<string>()
  ;(res.data || []).forEach((d: Delivery) => {
    ;(d.tags || []).forEach((t: string) => allTags.add(t))
  })
  return Array.from(allTags)
}

/** 导出投递数据为 CSV，返回 Blob */
export async function exportDeliveriesCsv(status?: string[]): Promise<Blob> {
  const res = await api.get('/deliveries/export', {
    responseType: 'blob',
    params: status ? { status } : undefined,
  })
  return res.data
}
