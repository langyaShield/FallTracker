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

// === 个人信息库 ===

/** 信息库分类标签 */
export const PROFILE_CATEGORY_LABELS: Record<string, string> = {
  basic: '基本信息',
  education: '教育经历',
  work: '工作经历',
}

/** 基本信息预设字段（key → 中文标签） */
export const PROFILE_BASIC_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'name', label: '姓名' },
  { key: 'gender', label: '性别' },
  { key: 'birthday', label: '出生日期' },
  { key: 'phone', label: '手机号' },
  { key: 'email', label: '邮箱' },
  { key: 'id_card', label: '身份证号' },
  { key: 'political_status', label: '政治面貌' },
  { key: 'ethnicity', label: '民族' },
  { key: 'hometown', label: '籍贯' },
  { key: 'address', label: '现居地址' },
  { key: 'english_name', label: '英文名' },
  { key: 'personal_site', label: '个人主页' },
  { key: 'github', label: 'GitHub' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'wechat', label: '微信号' },
]

/** 教育经历预设字段 */
export const PROFILE_EDUCATION_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'school', label: '学校' },
  { key: 'major', label: '专业' },
  { key: 'degree', label: '学位' },
  { key: 'start_date', label: '入学时间' },
  { key: 'end_date', label: '毕业时间' },
  { key: 'gpa', label: 'GPA' },
  { key: 'rank', label: '排名' },
  { key: 'courses', label: '主修课程' },
  { key: 'awards', label: '获奖情况' },
]

/** 工作经历预设字段 */
export const PROFILE_WORK_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'company', label: '公司' },
  { key: 'position', label: '岗位' },
  { key: 'department', label: '部门' },
  { key: 'start_date', label: '开始时间' },
  { key: 'end_date', label: '结束时间' },
  { key: 'description', label: '工作内容' },
  { key: 'achievements', label: '主要成果' },
]

/** 所有字段的中文标签映射 */
export const PROFILE_FIELD_LABEL_MAP: Record<string, string> = {
  name: '姓名',
  gender: '性别',
  birthday: '出生日期',
  phone: '手机号',
  email: '邮箱',
  id_card: '身份证号',
  political_status: '政治面貌',
  ethnicity: '民族',
  hometown: '籍贯',
  address: '现居地址',
  english_name: '英文名',
  personal_site: '个人主页',
  github: 'GitHub',
  linkedin: 'LinkedIn',
  wechat: '微信号',
  school: '学校',
  major: '专业',
  degree: '学位',
  start_date: '开始时间',
  end_date: '结束时间',
  gpa: 'GPA',
  rank: '排名',
  courses: '主修课程',
  awards: '获奖情况',
  company: '公司',
  position: '岗位',
  department: '部门',
  description: '工作内容',
  achievements: '主要成果',
}

/** 获取字段中文标签，未知字段返回 key 本身 */
export function getProfileFieldLabel(key: string): string {
  return PROFILE_FIELD_LABEL_MAP[key] || key
}

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
