<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, Link } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { useUndoDelete } from '@/composables/useUndoDelete'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'

interface Review {
  id: number
  delivery_id: number
  raw_notes: string
  created_at: string
}

const reviews = ref<Review[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref<Partial<Review>>({})
const deliveries = ref<{ id: number; company: string; position: string }[]>([])
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

const fetchReviews = async () => {
  loading.value = true
  try {
    const res = await api.get('/reviews', { params: { limit: pageSize.value, offset: (currentPage.value - 1) * pageSize.value } })
    reviews.value = res.data?.items || []
    total.value = res.data?.total || 0
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
  } catch (e) {
    console.warn('投递列表加载失败', e)
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
            <el-button text size="small" :icon="Edit" aria-label="编辑复盘" @click="openEdit(review)" />
            <el-button text size="small" type="danger" :icon="Delete" aria-label="删除复盘" @click="deleteReview(review)" />
          </div>
        </div>
        <div class="review-section">
          <div class="section-title">粗表记录</div>
          <pre class="review-content">{{ review.raw_notes }}</pre>
        </div>
      </el-card>
      <el-empty v-if="displayedReviews.length === 0" description="还没有面试复盘记录">
        <el-button type="primary" :icon="Plus" @click="openAdd">新建复盘</el-button>
      </el-empty>
      <el-pagination
        v-if="total > pageSize"
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        class="review-pagination"
        @current-change="fetchReviews"
      />
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

@media (max-width: 768px) {
  .review-header {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>
