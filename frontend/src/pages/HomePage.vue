<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import api from '@/lib/api'
import { STATUS_LABEL_MAP, STATUS_COLOR_MAP, EVENT_TYPE_LABEL_MAP, EVENT_TYPE_COLOR_MAP } from '@/lib/constants'
import { formatShortDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import { TrendCharts, Calendar, Document, EditPen } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()

const stats = ref<Record<string, number>>({})
const upcomingEvents = ref<any[]>([])
const loading = ref(false)

const total = computed(() => Object.values(stats.value).reduce((a, b) => a + b, 0))
const offerCount = computed(() => stats.value.offer || 0)
const interviewCount = computed(() => stats.value.interview || 0)

const fetchStats = async () => {
  loading.value = true
  try {
    const res = await api.get('/statistics/funnel')
    stats.value = res.data
  } catch (e: unknown) {
    // N-BUG-7: 不再静默吞错，提示用户感知加载失败
    ElMessage.error(extractErrorMessage(e, '统计数据加载失败'))
  } finally {
    loading.value = false
  }
}

const fetchUpcoming = async () => {
  try {
    // 后端配合：只返回未来的 5 条事件，避免拉全量后再 filter/sort/slice
    // 对应 backend/app/routers/events.py: list_all_events(upcoming=true, limit=5)
    const res = await api.get('/events', { params: { upcoming: true, limit: 5 } })
    upcomingEvents.value = res.data || []
  } catch (e: unknown) {
    ElMessage.warning(extractErrorMessage(e, '即将面试加载失败'))
  }
}

onMounted(() => {
  fetchStats()
  fetchUpcoming()
})
</script>

<template>
  <div class="home-page" v-loading="loading">
    <div class="welcome-section">
      <h1>欢迎回来，{{ authStore.user?.username || '用户' }}</h1>
      <p>这是你的秋招进展概览</p>
    </div>

    <div class="kpi-row">
      <el-card class="kpi-card">
        <div class="kpi-value" style="color: #1e3a5f">{{ total }}</div>
        <div class="kpi-label">投递总数</div>
      </el-card>
      <el-card class="kpi-card">
        <div class="kpi-value" style="color: #f59e0b">{{ interviewCount }}</div>
        <div class="kpi-label">面试中</div>
      </el-card>
      <el-card class="kpi-card">
        <div class="kpi-value" style="color: #10b981">{{ offerCount }}</div>
        <div class="kpi-label">已Offer</div>
      </el-card>
    </div>

    <div class="content-grid">
      <el-card class="section-card">
        <template #header>
          <div class="section-header">
            <span>投递状态分布</span>
            <el-button text type="primary" @click="router.push('/statistics')">查看详情</el-button>
          </div>
        </template>
        <div class="status-bars">
          <div v-for="(_, key) in STATUS_LABEL_MAP" :key="key" class="status-row">
            <span class="status-label">{{ STATUS_LABEL_MAP[key] }}</span>
            <div class="status-bar-bg">
              <div
                class="status-bar-fill"
                :style="{
                  width: total > 0 ? `${(stats[key] || 0) / total * 100}%` : '0%',
                  backgroundColor: STATUS_COLOR_MAP[key],
                }"
              />
            </div>
            <span class="status-count">{{ stats[key] || 0 }}</span>
          </div>
        </div>
      </el-card>

      <el-card class="section-card">
        <template #header>
          <div class="section-header">
            <span>即将到来的面试</span>
            <el-button text type="primary" @click="router.push('/calendar')">查看日历</el-button>
          </div>
        </template>
        <div v-if="upcomingEvents.length === 0" class="empty-hint">暂无即将到来的面试事件</div>
        <div v-for="evt in upcomingEvents" :key="evt.id" class="event-row">
          <div class="event-dot" :style="{ backgroundColor: EVENT_TYPE_COLOR_MAP[evt.event_type] || '#94a3b8' }" />
          <div class="event-info">
            <div class="event-company">{{ evt.company || '未知公司' }} · {{ EVENT_TYPE_LABEL_MAP[evt.event_type] || evt.event_type }}</div>
            <div class="event-time">{{ formatShortDateTime(evt.scheduled_at) }} · {{ evt.duration_minutes }}分钟</div>
          </div>
        </div>
      </el-card>
    </div>

    <div class="quick-actions">
      <el-button type="primary" size="large" :icon="TrendCharts" @click="router.push('/dashboard')">投递大盘</el-button>
      <el-button size="large" :icon="Calendar" @click="router.push('/calendar')">日历视图</el-button>
      <el-button size="large" :icon="EditPen" @click="router.push('/reviews')">面试复盘</el-button>
      <el-button size="large" :icon="Document" @click="router.push('/resumes')">简历管理</el-button>
    </div>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 960px;
  margin: 0 auto;
}

.welcome-section {
  margin-bottom: 32px;
}

.welcome-section h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1e3a5f;
  margin-bottom: 8px;
}

.welcome-section p {
  font-size: 15px;
  color: #64748b;
}

.kpi-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.kpi-card {
  text-align: center;
  padding: 8px;
}

.kpi-value {
  font-size: 36px;
  font-weight: 700;
}

.kpi-label {
  font-size: 14px;
  color: #64748b;
  margin-top: 4px;
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.status-bars {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-label {
  width: 60px;
  font-size: 13px;
  color: #334155;
  text-align: right;
}

.status-bar-bg {
  flex: 1;
  height: 24px;
  background: #f1f5f9;
  border-radius: 6px;
  overflow: hidden;
}

.status-bar-fill {
  height: 100%;
  border-radius: 6px;
  transition: width 0.6s ease;
  min-width: 0;
}

.status-count {
  width: 30px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
}

.empty-hint {
  text-align: center;
  color: #94a3b8;
  padding: 24px 0;
  font-size: 14px;
}

.event-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #f1f5f9;
}

.event-row:last-child {
  border-bottom: none;
}

.event-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.event-info {
  flex: 1;
}

.event-company {
  font-size: 14px;
  font-weight: 500;
  color: #1e3a5f;
}

.event-time {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

.quick-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
</style>
