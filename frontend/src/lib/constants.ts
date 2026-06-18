export interface StatusOption {
  key: string
  label: string
  color: string
}

export const STATUS_COLUMNS: StatusOption[] = [
  { key: 'pending', label: '待投递', color: '#94a3b8' },
  { key: 'delivered', label: '已投递', color: '#3b82f6' },
  { key: 'written', label: '笔试中', color: '#8b5cf6' },
  { key: 'interview', label: '面试中', color: '#f59e0b' },
  { key: 'offer', label: '已Offer', color: '#10b981' },
  { key: 'rejected', label: '已终止', color: '#ef4444' },
]

export const STATUS_LABEL_MAP: Record<string, string> = Object.fromEntries(
  STATUS_COLUMNS.map((s) => [s.key, s.label])
)

export const STATUS_COLOR_MAP: Record<string, string> = Object.fromEntries(
  STATUS_COLUMNS.map((s) => [s.key, s.color])
)

export const EVENT_TYPE_OPTIONS = [
  { label: '笔试', value: 'written' },
  { label: '面试', value: 'interview' },
  { label: 'HR面', value: 'hr' },
  { label: '其他', value: 'other' },
] as const

export const EVENT_TYPE_LABEL_MAP: Record<string, string> = Object.fromEntries(
  EVENT_TYPE_OPTIONS.map((o) => [o.value, o.label])
)

/** 事件类型对应的展示色（与 STATUS_COLUMNS 风格保持一致） */
export const EVENT_TYPE_COLOR_MAP: Record<string, string> = {
  written: '#8b5cf6',
  interview: '#3b82f6',
  hr: '#f59e0b',
  other: '#94a3b8',
}

/** 公共路径（无需鉴权/不触发 401 跳转）。api.ts 与 router 共享同一份真源。 */
export const PUBLIC_PATHS = ['/login', '/register'] as const
export type PublicPath = (typeof PUBLIC_PATHS)[number]

/** CSV 导入表头映射：中文 -> 英文字段名 */
export const CSV_HEADER_MAP: Record<string, string> = {
  公司: 'company',
  company: 'company',
  岗位: 'position',
  position: 'position',
  状态: 'status',
  status: 'status',
  链接: 'link',
  JD链接: 'link',
  link: 'link',
  标签: 'tags',
  tags: 'tags',
  截止日期: 'deadline',
  deadline: 'deadline',
  JD描述: 'jd_text',
  jd_text: 'jd_text',
  描述: 'jd_text',
}
