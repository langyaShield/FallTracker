<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const funnel = ref<Record<string, number>>({})
const loading = ref(false)

const fetchStatistics = async () => {
  loading.value = true
  try {
    const res = await axios.get(`${API_BASE}/statistics/funnel`)
    funnel.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取统计失败')
  } finally {
    loading.value = false
  }
}

const stages = [
  { key: 'pending', label: '待投递', color: '#94a3b8' },
  { key: 'delivered', label: '已投递', color: '#3b82f6' },
  { key: 'written', label: '笔试中', color: '#8b5cf6' },
  { key: 'interview', label: '面试中', color: '#f59e0b' },
  { key: 'offer', label: '已Offer', color: '#10b981' },
  { key: 'rejected', label: '已终止', color: '#ef4444' },
]

const total = computed(() => {
  return Object.values(funnel.value).reduce((a, b) => a + b, 0)
})

const conversionRates = computed(() => {
  const rates = []
  for (let i = 1; i < stages.length; i++) {
    const prev = funnel.value[stages[i - 1].key] || 0
    const curr = funnel.value[stages[i].key] || 0
    if (prev > 0) {
      rates.push({
        from: stages[i - 1].label,
        to: stages[i].label,
        rate: ((curr / prev) * 100).toFixed(1),
      })
    }
  }
  return rates
})

onMounted(fetchStatistics)
</script>

<template>
  <div class="statistics-page">
    <div class="page-header">
      <h2>数据统计</h2>
    </div>

    <div v-loading="loading" class="stats-content">
      <div class="kpi-cards">
        <el-card v-for="stage in stages" :key="stage.key" class="kpi-card">
          <div class="kpi-value" :style="{ color: stage.color }">{{ funnel[stage.key] || 0 }}</div>
          <div class="kpi-label">{{ stage.label }}</div>
        </el-card>
      </div>

      <el-card class="funnel-card">
        <template #header>
          <span>转化漏斗</span>
        </template>
        <div class="funnel-visual">
          <div v-for="stage in stages" :key="stage.key" class="funnel-bar-wrapper">
            <div class="funnel-label">{{ stage.label }}</div>
            <div class="funnel-bar-bg">
              <div
                class="funnel-bar"
                :style="{
                  width: total > 0 ? `${(funnel[stage.key] || 0) / total * 100}%` : '0%',
                  backgroundColor: stage.color,
                }"
              />
            </div>
            <div class="funnel-count">{{ funnel[stage.key] || 0 }}</div>
          </div>
        </div>
      </el-card>

      <el-card class="conversion-card">
        <template #header>
          <span>阶段转化率</span>
        </template>
        <el-table :data="conversionRates" style="width: 100%">
          <el-table-column prop="from" label="从" />
          <el-table-column prop="to" label="到" />
          <el-table-column prop="rate" label="转化率">
            <template #default="{ row }">
              <el-tag :type="Number(row.rate) > 50 ? 'success' : Number(row.rate) > 20 ? 'warning' : 'danger'">{{ row.rate }}%</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.statistics-page {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #1e3a5f;
}

.stats-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.kpi-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 16px;
}

.kpi-card {
  text-align: center;
  padding: 8px;
}

.kpi-value {
  font-size: 32px;
  font-weight: 700;
  margin-bottom: 4px;
}

.kpi-label {
  font-size: 14px;
  color: #64748b;
}

.funnel-visual {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.funnel-bar-wrapper {
  display: flex;
  align-items: center;
  gap: 16px;
}

.funnel-label {
  width: 80px;
  font-size: 14px;
  color: #334155;
  font-weight: 500;
  text-align: right;
}

.funnel-bar-bg {
  flex: 1;
  height: 32px;
  background: #f1f5f9;
  border-radius: 6px;
  overflow: hidden;
}

.funnel-bar {
  height: 100%;
  border-radius: 6px;
  transition: width 0.6s ease;
}

.funnel-count {
  width: 40px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  text-align: left;
}

@media (max-width: 1200px) {
  .kpi-cards {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
