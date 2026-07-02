<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/lib/api'
import { STATUS_LABEL_MAP, STATUS_COLOR_MAP, EVENT_TYPE_LABEL_MAP, EVENT_TYPE_COLOR_MAP } from '@/lib/constants'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import EChartsWrap from '@/components/EChartsWrap.vue'

const router = useRouter()
const loading = ref(false)

// ─── 数据 ───
const overview = ref({
  total: 0, response_rate: 0, interview_rate: 0, offer_rate: 0,
  weekly_new: 0, weekly_interviews: 0, weekly_offers: 0, stale_count: 0,
})
const funnel = ref<Record<string, number>>({})
const timeline = ref({ months: [] as string[], series: {} as Record<string, number[]> })
const companyProgress = ref<any[]>([])
const interviewStats = ref({
  total_interviews: 0, by_type: {} as Record<string, number>,
  by_round: {} as Record<string, number>, upcoming_count: 0,
})

// ─── 时间范围筛选 (E3) ───
const timelineRangeOptions = [
  { label: '1个月', value: 1 },
  { label: '3个月', value: 3 },
  { label: '6个月', value: 6 },
  { label: '1年', value: 12 },
  { label: '全部', value: 24 },
]
const timelineMonths = ref(6)
const timelineLoading = ref(false)

async function fetchTimeline() {
  timelineLoading.value = true
  try {
    const res = await api.get(`/statistics/timeline?months=${timelineMonths.value}`)
    timeline.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取趋势数据失败'))
  } finally {
    timelineLoading.value = false
  }
}

watch(timelineMonths, () => {
  fetchTimeline()
})

// ─── 获取数据 ───
async function fetchAll() {
  loading.value = true
  try {
    const [overviewRes, funnelRes, timelineRes, companyRes, interviewRes] = await Promise.all([
      api.get('/statistics/overview'),
      api.get('/statistics/funnel'),
      api.get('/statistics/timeline?months=6'),
      api.get('/statistics/company-progress?limit=20'),
      api.get('/statistics/interview-stats'),
    ])
    overview.value = overviewRes.data
    funnel.value = funnelRes.data
    timeline.value = timelineRes.data
    companyProgress.value = companyRes.data || []
    interviewStats.value = interviewRes.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取统计数据失败'))
  } finally {
    loading.value = false
  }
}

// ─── 图表配置 ───

// 投递趋势折线图
const timelineOption = computed(() => {
  const months = timeline.value.months.map((m: string) => m.slice(5)) // "2025-01" -> "01"
  const showStatuses = ['delivered', 'written', 'interview', 'offer']
  return {
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0, textStyle: { fontSize: 12 } },
    grid: { left: 40, right: 16, top: 16, bottom: 40 },
    xAxis: { type: 'category', data: months, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 11 } },
    series: showStatuses.map(key => ({
      name: STATUS_LABEL_MAP[key] || key,
      type: 'line',
      smooth: true,
      data: timeline.value.series[key] || [],
      itemStyle: { color: STATUS_COLOR_MAP[key] },
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.08 },
    })),
  }
})

// 转化漏斗图
const funnelOption = computed(() => {
  const total = Object.values(funnel.value).reduce((a, b) => a + b, 0)
  if (total === 0) return {}
  const funnelStages = ['pending', 'delivered', 'written', 'interview', 'offer']
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'funnel',
      left: '10%',
      top: 10,
      bottom: 10,
      width: '80%',
      min: 0,
      max: total,
      minSize: '20%',
      maxSize: '100%',
      sort: 'descending',
      gap: 4,
      label: { show: true, position: 'inside', fontSize: 13, formatter: '{b}\n{c}' },
      itemStyle: { borderColor: '#fff', borderWidth: 1 },
      data: funnelStages.map(key => ({
        name: STATUS_LABEL_MAP[key],
        value: funnel.value[key] || 0,
        itemStyle: { color: STATUS_COLOR_MAP[key] },
      })),
    }],
  }
})

// 面试类型饼图
const interviewTypeOption = computed(() => {
  const byType = interviewStats.value.by_type
  const data = Object.entries(byType).map(([type, count]) => ({
    name: EVENT_TYPE_LABEL_MAP[type] || type,
    value: count,
    itemStyle: { color: EVENT_TYPE_COLOR_MAP[type] || '#94a3b8' },
  }))
  if (data.length === 0) {
    data.push({ name: '暂无数据', value: 1, itemStyle: { color: '#e2e8f0' } })
  }
  return {
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '50%'],
      label: { show: true, fontSize: 12 },
      data,
    }],
  }
})

// 面试轮次柱状图
const interviewRoundOption = computed(() => {
  const byRound = interviewStats.value.by_round
  const rounds = Object.keys(byRound).sort((a, b) => Number(a) - Number(b))
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 16, bottom: 24 },
    xAxis: {
      type: 'category',
      data: rounds.map(r => `第${r}轮`),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar',
      data: rounds.map(r => byRound[r]),
      itemStyle: { color: '#6366f1', borderRadius: [4, 4, 0, 0] },
      barWidth: '40%',
    }],
  }
})

// ─── 辅助函数 ───
const statusTagType = (status: string) => {
  const map: Record<string, string> = {
    pending: 'info', delivered: '', written: 'warning',
    interview: 'warning', offer: 'success', rejected: 'danger',
  }
  return map[status] || 'info'
}

const staleTagType = (days: number) => {
  if (days >= 14) return 'danger'
  if (days >= 7) return 'warning'
  return 'info'
}

onMounted(fetchAll)
</script>

<template>
  <div class="statistics-page">
    <PageHeader title="数据统计" />

    <!-- Skeleton loading state -->
    <div v-if="loading" class="stats-content">
      <div class="kpi-cards">
        <el-card v-for="n in 5" :key="n" class="kpi-card">
          <el-skeleton animated>
            <template #template>
              <el-skeleton-item variant="h1" style="width: 50%; margin: 0 auto" />
              <el-skeleton-item variant="text" style="width: 60%; margin: 8px auto 0" />
            </template>
          </el-skeleton>
        </el-card>
      </div>
      <el-card class="weekly-card">
        <el-skeleton animated :rows="1" />
      </el-card>
      <div class="charts-row">
        <el-card v-for="n in 2" :key="n" class="chart-card">
          <template #header>
            <el-skeleton :rows="0" animated>
              <template #template>
                <el-skeleton-item variant="text" style="width: 80px" />
              </template>
            </el-skeleton>
          </template>
          <el-skeleton animated :rows="6" />
        </el-card>
      </div>
      <div class="charts-row">
        <el-card v-for="n in 2" :key="n" class="chart-card">
          <template #header>
            <el-skeleton :rows="0" animated>
              <template #template>
                <el-skeleton-item variant="text" style="width: 80px" />
              </template>
            </el-skeleton>
          </template>
          <el-skeleton animated :rows="8" />
        </el-card>
      </div>
    </div>

    <!-- Actual content -->
    <div v-else class="stats-content">
      <!-- 核心KPI行 -->
      <div class="kpi-cards">
        <el-card class="kpi-card">
          <div class="kpi-value" style="color: #1e3a5f">{{ overview.total }}</div>
          <div class="kpi-label">总投递</div>
        </el-card>
        <el-card class="kpi-card">
          <div class="kpi-value" style="color: #3b82f6">{{ overview.response_rate }}%</div>
          <div class="kpi-label">回复率</div>
        </el-card>
        <el-card class="kpi-card">
          <div class="kpi-value" style="color: #f59e0b">{{ overview.interview_rate }}%</div>
          <div class="kpi-label">面试率</div>
        </el-card>
        <el-card class="kpi-card">
          <div class="kpi-value" style="color: #10b981">{{ overview.offer_rate }}%</div>
          <div class="kpi-label">Offer率</div>
        </el-card>
        <el-card class="kpi-card kpi-alert" @click="router.push('/dashboard')">
          <div class="kpi-value" style="color: #ef4444">{{ overview.stale_count }}</div>
          <div class="kpi-label">待跟进</div>
        </el-card>
      </div>

      <!-- 本周动态 -->
      <el-card class="weekly-card">
        <div class="weekly-row">
          <span class="weekly-title">本周动态</span>
          <div class="weekly-items">
            <div class="weekly-item">
              <span class="weekly-num">{{ overview.weekly_new }}</span>
              <span class="weekly-desc">新增投递</span>
            </div>
            <div class="weekly-divider" />
            <div class="weekly-item">
              <span class="weekly-num">{{ overview.weekly_interviews }}</span>
              <span class="weekly-desc">面试</span>
            </div>
            <div class="weekly-divider" />
            <div class="weekly-item">
              <span class="weekly-num">{{ overview.weekly_offers }}</span>
              <span class="weekly-desc">Offer</span>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 图表区：趋势 + 漏斗 -->
      <div class="charts-row">
        <el-card class="chart-card">
          <template #header>
            <div class="card-title-row">
              <span class="card-title">投递趋势</span>
              <el-radio-group v-model="timelineMonths" size="small">
                <el-radio-button v-for="opt in timelineRangeOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <div v-loading="timelineLoading">
            <EChartsWrap v-if="timeline.months.length" :option="timelineOption" height="300px" />
            <el-empty v-else description="暂无投递数据" :image-size="60" />
          </div>
        </el-card>
        <el-card class="chart-card">
          <template #header><span class="card-title">转化漏斗</span></template>
          <EChartsWrap v-if="Object.keys(funnelOption).length" :option="funnelOption" height="300px" />
          <el-empty v-else description="暂无投递数据" :image-size="60" />
        </el-card>
      </div>

      <!-- 图表区：面试统计 + 待跟进公司 -->
      <div class="charts-row">
        <el-card class="chart-card">
          <template #header>
            <div class="card-title-row">
              <span class="card-title">面试统计</span>
              <el-tag v-if="interviewStats.upcoming_count" type="warning" size="small">
                即将面试 {{ interviewStats.upcoming_count }} 场
              </el-tag>
            </div>
          </template>
          <div v-if="interviewStats.total_interviews > 0" class="interview-charts">
            <div class="interview-pie">
              <EChartsWrap :option="interviewTypeOption" height="220px" />
            </div>
            <div class="interview-bar">
              <div class="sub-title">轮次分布</div>
              <EChartsWrap :option="interviewRoundOption" height="180px" />
            </div>
          </div>
          <el-empty v-else description="暂无面试记录" :image-size="60" />
        </el-card>
        <el-card class="chart-card">
          <template #header>
            <div class="card-title-row">
              <span class="card-title">公司进展</span>
              <span class="card-subtitle">按待跟进优先排序</span>
            </div>
          </template>
          <el-table v-if="companyProgress.length" :data="companyProgress" size="small" max-height="320" style="width: 100%">
            <el-table-column prop="company" label="公司" min-width="100">
              <template #default="{ row }">
                <span class="company-link" @click="router.push(`/delivery/${row.id}`)">{{ row.company }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="position" label="岗位" min-width="80" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ STATUS_LABEL_MAP[row.status] || row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="停留" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.status === 'delivered' && row.days_in_status >= 7" :type="staleTagType(row.days_in_status)" size="small" effect="dark">
                  {{ row.days_in_status }}天
                </el-tag>
                <span v-else class="days-normal">{{ row.days_in_status }}天</span>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无投递记录" :image-size="60" />
        </el-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
.statistics-page { height: 100%; }

.stats-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ─── KPI 卡片 ─── */
.kpi-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
}

.kpi-card {
  text-align: center;
  padding: 4px 0;
  cursor: default;
}

.kpi-card.kpi-alert {
  cursor: pointer;
  transition: all 0.2s;
}

.kpi-card.kpi-alert:hover {
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.15);
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
}

.kpi-label {
  font-size: 13px;
  color: #64748b;
  margin-top: 4px;
}

/* ─── 本周动态 ─── */
.weekly-card {
  padding: 0;
}

.weekly-card :deep(.el-card__body) {
  padding: 14px 20px;
}

.weekly-row {
  display: flex;
  align-items: center;
  gap: 24px;
}

.weekly-title {
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
  white-space: nowrap;
}

.weekly-items {
  display: flex;
  align-items: center;
  gap: 20px;
}

.weekly-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.weekly-num {
  font-size: 20px;
  font-weight: 700;
  color: #1e3a5f;
}

.weekly-desc {
  font-size: 13px;
  color: #64748b;
}

.weekly-divider {
  width: 1px;
  height: 20px;
  background: #e2e8f0;
}

/* ─── 图表区 ─── */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.chart-card :deep(.el-card__header) {
  padding: 12px 16px;
}

.card-title {
  font-weight: 600;
  font-size: 15px;
  color: #1e293b;
}

.card-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-subtitle {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 400;
}

/* ─── 面试统计 ─── */
.interview-charts {
  display: flex;
  gap: 8px;
}

.interview-pie {
  flex: 1;
  min-width: 0;
}

.interview-bar {
  flex: 1;
  min-width: 0;
}

.sub-title {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 4px;
  text-align: center;
}

/* ─── 公司进展表格 ─── */
.company-link {
  color: #3b82f6;
  cursor: pointer;
  font-weight: 500;
}

.company-link:hover {
  text-decoration: underline;
}

.days-normal {
  font-size: 12px;
  color: #94a3b8;
}

/* ─── 响应式 ─── */
@media (max-width: 1000px) {
  .kpi-cards {
    grid-template-columns: repeat(3, 1fr);
  }
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .kpi-cards {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }

  .charts-row {
    grid-template-columns: 1fr;
    gap: 12px;
  }
}
</style>
