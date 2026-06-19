<script setup lang="ts">
/**
 * ECharts 轻量封装组件
 * - 统一主题配色
 * - 自动响应容器尺寸
 * - 按需引入常用图表类型
 */
import { computed } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, PieChart, BarChart, FunnelChart } from 'echarts/charts'
import {
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent,
} from 'echarts/components'

// 按需注册
use([
  CanvasRenderer, LineChart, PieChart, BarChart, FunnelChart,
  TitleComponent, TooltipComponent, LegendComponent,
  GridComponent, DatasetComponent,
])

const props = defineProps<{
  option: Record<string, any>
  height?: string
}>()

const chartStyle = computed(() => ({
  height: props.height || '320px',
  width: '100%',
}))
</script>

<template>
  <VChart :option="option" :style="chartStyle" autoresize />
</template>
