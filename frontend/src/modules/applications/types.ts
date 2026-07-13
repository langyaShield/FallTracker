/**
 * applications 模块类型定义
 *
 * 对应后端 backend/app/schemas.py 中的 Pydantic 模型，
 * 涵盖投递、面试事件、活动日志、备注、标签等核心实体。
 */

// ─── 核心实体 ───

export interface Delivery {
  id: number
  user_id: number
  company: string
  position: string
  jd_text?: string | null
  link?: string | null
  status: string
  resume_id?: number | null
  tags: string[]
  deadline?: string | null
  created_at: string
  updated_at: string
}

export interface InterviewEvent {
  id: number
  delivery_id: number
  event_type: string
  round_number: number
  scheduled_at: string
  duration_minutes: number
  location?: string | null
  meeting_link?: string | null
  interviewer?: string | null
  notes?: string | null
  created_at: string
}

export interface DeliveryLog {
  id: number
  delivery_id: number
  action: string
  detail?: string | null
  created_at: string
}

export interface DeliveryNote {
  id: number
  delivery_id: number
  user_id: number
  content: string
  created_at: string
  updated_at: string
}

export interface TagCount {
  tag: string
  count: number
}

/** 简历（applications 模块仅需 id 和 name 做关联选择） */
export interface ResumeOption {
  id: number
  name: string
}

// ─── 写操作入参 ───

export interface DeliveryCreateInput {
  company: string
  position: string
  jd_text?: string
  link?: string
  status?: string
  resume_id?: number | null
  tags?: string[]
  deadline?: string | null
}

export type DeliveryUpdateInput = Partial<DeliveryCreateInput>

export interface InterviewEventCreateInput {
  event_type: string
  round_number?: number
  scheduled_at: string
  duration_minutes?: number
  location?: string
  meeting_link?: string
  interviewer?: string
  notes?: string
}

export type InterviewEventUpdateInput = Partial<InterviewEventCreateInput>

export interface DeliveryNoteCreateInput {
  content: string
}

// ─── 批量操作入参 ───

export interface BatchStatusUpdateInput {
  ids: number[]
  status: string
}

export interface BatchTagUpdateInput {
  ids: number[]
  add_tags?: string[]
  remove_tags?: string[]
}

export interface BatchDeleteInput {
  ids: number[]
}

// ─── 查询参数 ───

export interface DeliveryListParams {
  search?: string
  status?: string[]
  tag?: string
  deadline_before?: string
  deadline_after?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

// ─── CSV 导入/导出 ───

export interface ImportPreviewResponse {
  headers: string[]
  raw_headers: string[]
  rows: Record<string, string>[]
  total: number
}

export interface ImportResult {
  created: number
  skipped: number
  errors: string[]
}
