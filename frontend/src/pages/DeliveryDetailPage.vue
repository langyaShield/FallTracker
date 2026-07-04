<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, ArrowRight, Plus, Edit, Delete, ChatDotRound, Document, Timer, View, CopyDocument, CirclePlus, Memo } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { STATUS_COLUMNS, EVENT_TYPE_OPTIONS, EVENT_TYPE_LABEL_MAP } from '@/lib/constants'
import { formatDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

/** 轻量级 Markdown 渲染器（XSS 安全） */
function renderMarkdown(text: string): string {
  // Step 1: escape HTML entities to prevent XSS
  const escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')

  // Step 2: apply markdown transforms on escaped text
  let html = escaped

  // Code blocks (```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    return `<pre class="md-code-block"><code>${code.trimEnd()}</code></pre>`
  })

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')

  // Headers
  html = html.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>')
  html = html.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>')
  html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>')

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')

  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')

  // Unordered lists (- or *)
  html = html.replace(/^[\-\*]\s+(.+)$/gm, '<li>$1</li>')
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>')

  // Line breaks (double newline = paragraph, single = <br>)
  html = html
    .split(/\n\n+/)
    .map(block => {
      if (block.startsWith('<h') || block.startsWith('<ul') || block.startsWith('<pre') || block.startsWith('<ol')) {
        return block
      }
      return `<p>${block.replace(/\n/g, '<br>')}</p>`
    })
    .join('\n')

  return html
}

const renderedJd = computed(() => {
  if (!delivery.value?.jd_text) return '<p style="color:#94a3b8">暂无JD描述</p>'
  return renderMarkdown(delivery.value.jd_text)
})

const route = useRoute()
const router = useRouter()

interface InterviewEvent {
  id: number
  event_type: string
  round_number: number
  scheduled_at: string
  duration_minutes: number
  location?: string
  meeting_link?: string
  interviewer?: string
  notes?: string
}

interface Delivery {
  id: number
  company: string
  position: string
  jd_text?: string
  link?: string
  status: string
  tags: string[]
  resume_id?: number | null
  deadline?: string | null
  created_at: string
  updated_at: string
}

interface Resume {
  id: number
  name: string
}

const delivery = ref<Delivery | null>(null)
const events = ref<InterviewEvent[]>([])
const resumes = ref<Resume[]>([])
const loading = ref(false)
const eventDialog = ref(false)
const rightPanelCollapsed = ref(false)
const editingEvent = ref<Partial<InterviewEvent>>({})

const statusOptions = STATUS_COLUMNS.map((s) => ({ label: s.label, value: s.key }))

// JD 默认展开预览，减少一次点击
const jdPreviewMode = ref(true)

// 状态下拉自动保存（防抖 600ms）
let statusSaveTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => delivery.value?.status,
  (newVal, oldVal) => {
    if (newVal === undefined || oldVal === undefined || newVal === oldVal) return
    if (statusSaveTimer) clearTimeout(statusSaveTimer)
    statusSaveTimer = setTimeout(() => {
      saveDelivery(false)
    }, 600)
  }
)

const copyJd = async () => {
  const text = delivery.value?.jd_text || ''
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('JD 已复制到剪贴板')
  } catch {
    // fallback
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('JD 已复制到剪贴板')
  }
}

// 时间线内联编辑
const inlineEditingEventId = ref<number | null>(null)
const inlineEventForm = ref<Partial<InterviewEvent>>({})

const startInlineEdit = (event: InterviewEvent) => {
  inlineEditingEventId.value = event.id
  inlineEventForm.value = { ...event, scheduled_at: event.scheduled_at.slice(0, 16) }
}

const cancelInlineEdit = () => {
  inlineEditingEventId.value = null
  inlineEventForm.value = {}
}

const saveInlineEvent = async () => {
  try {
    await api.put(`/events/${inlineEventForm.value.id}`, inlineEventForm.value)
    ElMessage.success('更新成功')
    inlineEditingEventId.value = null
    fetchEvents()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '更新失败'))
  }
}

// 右下角 FAB
const fabOpen = ref(false)
const fabActions = [
  { label: '添加事件', icon: CirclePlus, action: () => openEventDialog() },
  { label: '写复盘', icon: Memo, action: () => router.push('/reviews') },
  { label: '编辑投递', icon: Edit, action: () => window.scrollTo({ top: 0, behavior: 'smooth' }) },
]

const fetchDetail = async () => {
  loading.value = true
  try {
    const res = await api.get(`/deliveries/${route.params.id}`)
    delivery.value = res.data
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取详情失败'))
  } finally {
    loading.value = false
  }
}

const fetchEvents = async () => {
  try {
    const res = await api.get(`/deliveries/${route.params.id}/events`)
    events.value = res.data
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取事件失败'))
  }
}

const fetchResumes = async () => {
  try {
    const res = await api.get('/resumes')
    resumes.value = res.data?.items || []
  } catch {
    // ignore
  }
}

/** N-BUG-1 修复：从全量投递聚合出已用过的标签作为 el-select-v2 的建议项 */
const tagOptions = ref<{ value: string; label: string }[]>([])
const fetchTagSuggestions = async () => {
  try {
    const res = await api.get('/deliveries')
    const allTags = new Set<string>()
    ;(res.data || []).forEach((d: Delivery) => (d.tags || []).forEach((t) => allTags.add(t)))
    tagOptions.value = Array.from(allTags).map((t) => ({ value: t, label: t }))
  } catch {
    // ignore
  }
}

const saveDelivery = async (showToast = true) => {
  if (!delivery.value) return
  try {
    await api.put(`/deliveries/${delivery.value.id}`, delivery.value)
    if (showToast) ElMessage.success('保存成功')
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const openEventDialog = (event?: InterviewEvent) => {
  if (event) {
    editingEvent.value = { ...event, scheduled_at: event.scheduled_at.slice(0, 16) }
  } else {
    editingEvent.value = {
      event_type: 'interview',
      round_number: events.value.length + 1,
      duration_minutes: 60,
      scheduled_at: '',
    }
  }
  eventDialog.value = true
}

const saveEvent = async () => {
  try {
    if (editingEvent.value.id) {
      await api.put(`/events/${editingEvent.value.id}`, editingEvent.value)
      ElMessage.success('更新成功')
    } else {
      await api.post(`/deliveries/${route.params.id}/events`, editingEvent.value)
      ElMessage.success('添加成功')
    }
    eventDialog.value = false
    fetchEvents()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const deleteEvent = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除该事件吗？', '提示', { type: 'warning' })
    await api.delete(`/events/${id}`)
    ElMessage.success('删除成功')
    fetchEvents()
  } catch {
    // cancelled
  }
}

onMounted(() => {
  fetchDetail()
  fetchEvents()
  fetchResumes()
  fetchTagSuggestions()
})
</script>

<template>
  <div v-loading="loading" class="detail-page">
    <PageHeader
      :title="`${delivery?.company || ''} - ${delivery?.position || ''}`"
      subtitle="投递详情"
      :show-back="true"
      :breadcrumbs="[
        { label: '投递大盘', path: '/dashboard' },
        { label: `${delivery?.company || ''} - ${delivery?.position || ''}` },
      ]"
    >
      <span v-if="delivery?.created_at" class="detail-time">创建于 {{ formatDateTime(delivery.created_at) }}</span>
    </PageHeader>

    <div class="detail-body" :class="{ 'right-collapsed': rightPanelCollapsed }">
      <div class="detail-left">
        <el-card class="info-card">
          <template #header>
            <div class="card-header">
              <span>基本信息</span>
              <div class="card-header-actions">
                <el-button size="small" text @click="router.push('/profile')">打开信息库</el-button>
                <el-button type="primary" size="small" @click="saveDelivery">保存</el-button>
              </div>
            </div>
          </template>
          <el-form label-width="80px">
            <el-form-item label="公司">
              <el-input v-model="delivery!.company" />
            </el-form-item>
            <el-form-item label="岗位">
              <el-input v-model="delivery!.position" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="delivery!.status" style="width: 100%">
                <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
              <span class="auto-save-hint">切换后自动保存</span>
            </el-form-item>
            <el-form-item label="标签">
              <el-select-v2
                v-model="delivery!.tags"
                :options="tagOptions"
                allow-create
                multiple
                filterable
                placeholder="选择或输入新标签"
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="链接">
              <el-input v-model="delivery!.link" />
            </el-form-item>
            <el-form-item label="JD描述">
              <div class="jd-field">
                <div class="jd-toolbar">
                  <el-button
                    :type="jdPreviewMode ? 'default' : 'primary'"
                    size="small"
                    text
                    @click="jdPreviewMode = false"
                  >编辑</el-button>
                  <el-button
                    :type="jdPreviewMode ? 'primary' : 'default'"
                    size="small"
                    text
                    :icon="View"
                    @click="jdPreviewMode = true"
                  >预览</el-button>
                  <el-button
                    size="small"
                    text
                    :icon="CopyDocument"
                    @click="copyJd"
                  >复制 JD</el-button>
                </div>
                <el-input v-if="!jdPreviewMode" v-model="delivery!.jd_text" type="textarea" :rows="4" />
                <div v-else class="md-preview" v-html="renderedJd" />
              </div>
            </el-form-item>
            <el-form-item label="简历">
              <el-select v-model="delivery!.resume_id" placeholder="选择简历（可选）" clearable style="width: 100%">
                <el-option v-for="r in resumes" :key="r.id" :label="r.name" :value="r.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="截止日期">
              <el-date-picker
                v-model="delivery!.deadline"
                type="datetime"
                placeholder="选择截止日期（可选）"
                style="width: 100%"
                value-format="YYYY-MM-DDTHH:mm"
                clearable
              />
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <button class="panel-toggle-btn" :title="rightPanelCollapsed ? '展开时间线' : '收起时间线'" @click="rightPanelCollapsed = !rightPanelCollapsed">
        <el-icon :size="14"><component :is="rightPanelCollapsed ? ArrowLeft : ArrowRight" /></el-icon>
      </button>

      <div v-show="!rightPanelCollapsed" class="detail-right">
        <el-card class="events-card">
          <template #header>
            <div class="card-header">
              <span>事件时间线</span>
              <el-button type="primary" size="small" :icon="Plus" @click="openEventDialog()">添加事件</el-button>
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
                    <el-button type="primary" size="small" @click="saveInlineEvent">保存</el-button>
                    <el-button size="small" @click="cancelInlineEdit">取消</el-button>
                  </el-form-item>
                </el-form>
              </div>
              <div v-else class="event-item">
                <div class="event-header">
                  <span class="event-type">{{ EVENT_TYPE_LABEL_MAP[evt.event_type] || evt.event_type }}</span>
                  <span class="event-round">第{{ evt.round_number }}轮</span>
                  <el-button text size="small" :icon="Edit" @click="startInlineEdit(evt)" />
                  <el-button text size="small" type="danger" :icon="Delete" @click="deleteEvent(evt.id)" />
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
      </div>
    </div>

    <!-- 右下角 FAB -->
    <div class="fab-container">
      <el-button
        class="fab-main"
        type="primary"
        circle
        size="large"
        :icon="Plus"
        @click="fabOpen = !fabOpen"
      />
      <transition name="fab-slide">
        <div v-if="fabOpen" class="fab-menu">
          <div
            v-for="(item, index) in fabActions"
            :key="index"
            class="fab-item"
            @click="item.action(); fabOpen = false"
          >
            <span class="fab-label">{{ item.label }}</span>
            <el-button circle size="small" :icon="item.icon" />
          </div>
        </div>
      </transition>
    </div>

    <el-dialog v-model="eventDialog" :title="editingEvent.id ? '编辑事件' : '添加事件'" width="500px">
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
        <el-button @click="eventDialog = false">取消</el-button>
        <el-button type="primary" @click="saveEvent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.detail-page {
  height: 100%;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.detail-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1e3a5f;
}

.detail-time {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
}

.detail-body {
  display: grid;
  grid-template-columns: 1fr 24px 1fr;
  gap: 0;
  transition: grid-template-columns 0.3s ease;
}

.detail-body.right-collapsed {
  grid-template-columns: 1fr 24px 0fr;
}

.detail-body.right-collapsed .detail-right {
  overflow: hidden;
  min-width: 0;
  opacity: 0;
}

.detail-left,
.detail-right {
  min-width: 0;
}

.detail-right {
  transition: opacity 0.3s ease;
  opacity: 1;
}

.panel-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  background: transparent;
  border: none;
  border-left: 1px solid #e2e8f0;
  border-right: 1px solid #e2e8f0;
  cursor: pointer;
  color: #94a3b8;
  transition: color 0.2s, background 0.2s;
  padding: 0;
  flex-shrink: 0;
}

.panel-toggle-btn:hover {
  color: #3b82f6;
  background: #f1f5f9;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.card-header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
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

.auto-save-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

/* JD Markdown preview */
.jd-field {
  width: 100%;
}

.jd-toolbar {
  display: flex;
  gap: 4px;
  margin-bottom: 6px;
}

.md-preview {
  min-height: 80px;
  max-height: 320px;
  overflow-y: auto;
  padding: 12px 16px;
  background: #f8fafc;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #334155;
}

.md-preview :deep(h1),
.md-preview :deep(h2),
.md-preview :deep(h3),
.md-preview :deep(h4),
.md-preview :deep(h5),
.md-preview :deep(h6) {
  margin: 12px 0 6px;
  color: #1e3a5f;
}

.md-preview :deep(h1) { font-size: 18px; }
.md-preview :deep(h2) { font-size: 16px; }
.md-preview :deep(h3) { font-size: 15px; }

.md-preview :deep(p) {
  margin: 6px 0;
}

.md-preview :deep(ul) {
  padding-left: 20px;
  margin: 6px 0;
}

.md-preview :deep(li) {
  margin-bottom: 2px;
}

.md-preview :deep(a) {
  color: #3b82f6;
  text-decoration: none;
}

.md-preview :deep(a:hover) {
  text-decoration: underline;
}

.md-preview :deep(strong) {
  color: #1e293b;
}

.md-preview :deep(.md-code-block) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px 16px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
  margin: 8px 0;
}

.md-preview :deep(.md-inline-code) {
  background: #e2e8f0;
  color: #e11d48;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}

.fab-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 12px;
}

.fab-main {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35);
  width: 52px;
  height: 52px;
  font-size: 22px;
}

.fab-menu {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  margin-bottom: 4px;
}

.fab-item {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.fab-label {
  font-size: 13px;
  color: #475569;
  background: #fff;
  padding: 4px 10px;
  border-radius: 4px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.fab-slide-enter-active,
.fab-slide-leave-active {
  transition: all 0.2s ease;
}

.fab-slide-enter-from,
.fab-slide-leave-to {
  opacity: 0;
  transform: translateY(20px);
}

@media (max-width: 768px) {
  .detail-body {
    grid-template-columns: 1fr !important;
    gap: 12px;
  }

  .panel-toggle-btn {
    display: none;
  }

  .detail-right {
    opacity: 1 !important;
  }

  .fab-container {
    bottom: 16px;
    right: 16px;
  }
}
</style>
