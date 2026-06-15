<script setup lang="ts">
/**
 * 统一的页面标题头组件
 *
 * 使用示例：
 *   <PageHeader title="简历管理">
 *     <el-button>上传</el-button>
 *   </PageHeader>
 *
 * 设计原则：
 * - 默认 font-size 24px、color #1e3a5f，与历史样式保持一致
 * - 通过 slot 注入右侧操作区，actions 容器自带 `header-right` flex 布局
 * - margin-bottom 24px，可通过 prop 调整
 */
defineProps<{
  title: string
  /** 标题下方的副标题/描述，可选 */
  subtitle?: string
  /** 底部间距，默认为 24px */
  marginBottom?: string | number
}>()
</script>

<template>
  <div class="page-header" :style="{ marginBottom: typeof marginBottom === 'number' ? `${marginBottom}px` : marginBottom }">
    <div class="page-header-text">
      <h2>{{ title }}</h2>
      <p v-if="subtitle" class="page-header-subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="header-right">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #1e3a5f;
}

.page-header-subtitle {
  margin: 0;
  font-size: 14px;
  color: #64748b;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
