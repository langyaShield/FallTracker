<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import api from '@/lib/api'
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

const deleteReview = async (id: number) => {
  try {
    await ElMessageBox.confirm('确定删除这条复盘记录吗？', '提示', { type: 'warning' })
    await api.delete(`/reviews/${id}`)
    ElMessage.success('删除成功')
    fetchReviews()
  } catch {
    // cancelled
  }
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
      <el-card v-for="review in reviews" :key="review.id" class="review-card">
        <div class="review-header">
          <span class="review-delivery">{{ deliveries.find((d) => d.id === review.delivery_id)?.company || '未知公司' }}</span>
          <div class="review-actions">
            <el-button v-if="!review.structured_qa" type="primary" text size="small" :loading="generating" @click="generateStructured(review.id)">一键生成</el-button>
            <el-button text size="small" :icon="Edit" @click="openEdit(review)" />
            <el-button text size="small" type="danger" :icon="Delete" @click="deleteReview(review.id)" />
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
          <div class="section-title">规范表</div>
          <pre class="review-content structured">{{ JSON.stringify(review.structured_qa, null, 2) }}</pre>
        </div>
        <div v-if="review.reflection" class="review-section">
          <div class="section-title">反思</div>
          <div class="review-content">{{ review.reflection }}</div>
        </div>
      </el-card>
      <el-empty v-if="reviews.length === 0" description="还没有面试复盘记录">
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
}

.review-delivery {
  font-weight: 600;
  font-size: 16px;
  color: #1e3a5f;
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

@media (max-width: 768px) {
  .review-header {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
