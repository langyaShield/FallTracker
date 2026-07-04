<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, CopyDocument, Link } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { useUndoDelete } from '@/composables/useUndoDelete'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

interface Review {
  id: number
  delivery_id: number
  raw_notes: string
  structured_qa?: any
  tags?: string[]
  reflection?: string
  created_at: string
}

const reviews = ref<Review[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref<Partial<Review>>({})
const deliveries = ref<{ id: number; company: string; position: string }[]>([])
const generating = ref(false)
const router = useRouter()

// 删除撤销
const { pendingIds: deletingReviewIds, requestDelete: requestDeleteReview } = useUndoDelete<Review>({
  getId: (r) => r.id,
  getName: (r) => `复盘 #${r.id}`,
  deleteFn: async (r) => {
    await api.delete(`/reviews/${r.id}`)
  },
  onSuccess: () => fetchReviews(),
})

const displayedReviews = computed(() => reviews.value.filter((r) => !deletingReviewIds.value.has(r.id)))

const getDelivery = (deliveryId: number) => {
  return deliveries.value.find((d) => d.id === deliveryId)
}

interface ParsedQA {
  question: string
  answer: string
  score?: string | number
}

const parseStructuredQA = (data: any): { items: ParsedQA[]; isObject: boolean; raw: any } => {
  if (!data) return { items: [], isObject: false, raw: data }

  // 数组形式
  if (Array.isArray(data)) {
    const items = data
      .map((item: any) => {
        if (typeof item === 'string') {
          return { question: item, answer: '' }
        }
        if (typeof item === 'object' && item !== null) {
          const q = item.question || item.q || item.Question || item.问题 || '未命名问题'
          const a = item.answer || item.a || item.Answer || item.答案 || item.content || ''
          const s = item.score || item.rating || item.评分 || item.score || undefined
          return { question: q, answer: a, score: s }
        }
        return { question: String(item), answer: '' }
      })
      .filter((item) => item.question || item.answer)
    return { items, isObject: false, raw: data }
  }

  // 对象形式：键值对
  if (typeof data === 'object' && data !== null) {
    const items = Object.entries(data).map(([key, value]) => ({
      question: key,
      answer: typeof value === 'string' ? value : JSON.stringify(value, null, 2),
    }))
    return { items, isObject: true, raw: data }
  }

  // 字符串形式，尝试解析
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data)
      return parseStructuredQA(parsed)
    } catch {
      return { items: [{ question: '内容', answer: data }], isObject: false, raw: data }
    }
  }

  return { items: [], isObject: false, raw: data }
}

const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('已复制到剪贴板')
  }
}

const fetchReviews = async () => {
  loading.value = true
  try {
    const res = await api.get('/reviews')
    reviews.value = res.data || []
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '获取复盘失败'))
  } finally {
    loading.value = false
  }
}

const fetchDeliveries = async () => {
  try {
    const res = await api.get('/deliveries')
    deliveries.value = (res.data || []).map((d: any) => ({ id: d.id, company: d.company, position: d.position }))
  } catch {
    // ignore
  }
}

const openAdd = () => {
  editing.value = { raw_notes: '' }
  dialogVisible.value = true
}

const openEdit = (row: Review) => {
  editing.value = { ...row }
  dialogVisible.value = true
}

const saveReview = async () => {
  if (!editing.value.delivery_id || !editing.value.raw_notes) {
    ElMessage.warning('请选择投递并填写复盘内容')
    return
  }
  try {
    if (editing.value.id) {
      await api.put(`/reviews/${editing.value.id}`, editing.value)
    } else {
      await api.post('/reviews', editing.value)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    fetchReviews()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const generateStructured = async (id: number) => {
  generating.value = true
  try {
    await api.post(`/reviews/${id}/generate`)
    ElMessage.success('生成成功')
    fetchReviews()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '生成失败'))
  } finally {
    generating.value = false
  }
}

const deleteReview = (review: Review) => {
  requestDeleteReview(review)
}

onMounted(() => {
  fetchReviews()
  fetchDeliveries()
})
</script>

<template>
  <div class="reviews-page">
    <PageHeader title="面试复盘">
      <el-button type="primary" :icon="Plus" @click="openAdd">新建复盘</el-button>
    </PageHeader>

    <div v-loading="loading" class="review-list">
      <el-card v-for="review in displayedReviews" :key="review.id" class="review-card">
        <div class="review-header">
          <div class="review-title">
            <span class="review-delivery">{{ getDelivery(review.delivery_id)?.company || '未知公司' }}</span>
            <el-tag
              v-if="getDelivery(review.delivery_id)?.position"
              size="small"
              class="review-position-tag"
              @click="router.push(`/delivery/${review.delivery_id}`)"
            >
              {{ getDelivery(review.delivery_id)?.position }}
            </el-tag>
          </div>
          <div class="review-actions">
            <el-button text size="small" :icon="Link" @click="router.push(`/delivery/${review.delivery_id}`)">投递详情</el-button>
            <el-button v-if="!review.structured_qa" type="primary" text size="small" :loading="generating" @click="generateStructured(review.id)">一键生成</el-button>
            <el-button text size="small" :icon="Edit" @click="openEdit(review)" />
            <el-button text size="small" type="danger" :icon="Delete" @click="deleteReview(review)" />
          </div>
        </div>
        <div class="review-tags" v-if="review.tags?.length">
          <el-tag v-for="tag in review.tags" :key="tag" size="small">{{ tag }}</el-tag>
        </div>
        <div class="review-section">
          <div class="section-title">粗表记录</div>
          <pre class="review-content">{{ review.raw_notes }}</pre>
        </div>
        <div v-if="review.structured_qa" class="review-section">
          <div class="section-title">
            规范表
            <el-button text size="small" :icon="CopyDocument" @click="copyToClipboard(JSON.stringify(review.structured_qa, null, 2))">复制</el-button>
          </div>
          <div class="qa-cards">
            <div
              v-for="(item, idx) in parseStructuredQA(review.structured_qa).items"
              :key="idx"
              class="qa-card"
            >
              <div class="qa-question">
                <span class="qa-index">Q{{ idx + 1 }}</span>
                {{ item.question }}
              </div>
              <div v-if="item.score !== undefined" class="qa-score">评分：{{ item.score }}</div>
              <div class="qa-answer">{{ item.answer || '（未填写答案）' }}</div>
            </div>
            <div v-if="parseStructuredQA(review.structured_qa).items.length === 0" class="review-content structured">
              {{ JSON.stringify(review.structured_qa, null, 2) }}
            </div>
          </div>
        </div>
        <div v-if="review.reflection" class="review-section">
          <div class="section-title">
            反思
            <el-button text size="small" :icon="CopyDocument" @click="copyToClipboard(review.reflection)">复制</el-button>
          </div>
          <div class="review-content">{{ review.reflection }}</div>
        </div>
      </el-card>
      <el-empty v-if="displayedReviews.length === 0" description="还没有面试复盘记录">
        <el-button type="primary" :icon="Plus" @click="openAdd">新建复盘</el-button>
      </el-empty>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing.id ? '编辑复盘' : '新建复盘'" width="600px">
      <el-form label-width="80px">
        <el-form-item label="投递">
          <el-select v-model="editing.delivery_id" placeholder="选择投递" style="width: 100%">
            <el-option v-for="d in deliveries" :key="d.id" :label="`${d.company} - ${d.position}`" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="粗表记录">
          <el-input v-model="editing.raw_notes" type="textarea" :rows="6" placeholder="面试后第一时间记录零散记忆..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveReview">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.reviews-page {
  height: 100%;
}

.review-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-card {
  transition: all 0.2s;
}

.review-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.review-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.review-delivery {
  font-weight: 600;
  font-size: 16px;
  color: #1e3a5f;
}

.review-position-tag {
  cursor: pointer;
}

.review-actions {
  display: flex;
  gap: 8px;
}

.review-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.review-section {
  margin-bottom: 12px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.review-content {
  background: #f8fafc;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  color: #334155;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.review-content.structured {
  font-family: monospace;
  font-size: 13px;
}

.qa-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.qa-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
}

.qa-question {
  font-weight: 600;
  color: #1e3a5f;
  margin-bottom: 6px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.qa-index {
  background: #1e3a5f;
  color: #fff;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.qa-score {
  font-size: 12px;
  color: #f59e0b;
  margin-bottom: 6px;
}

.qa-answer {
  font-size: 14px;
  color: #475569;
  line-height: 1.6;
  white-space: pre-wrap;
}

@media (max-width: 768px) {
  .review-header {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
