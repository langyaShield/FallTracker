<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'

interface BreadcrumbItem {
  label: string
  path?: string
}

const props = defineProps<{
  title: string
  /** 标题下方的副标题/描述，可选 */
  subtitle?: string
  /** 底部间距，默认为 24px */
  marginBottom?: string | number
  /** 是否显示返回按钮，默认 false */
  showBack?: boolean
  /** 返回路径，默认使用浏览器返回 */
  backPath?: string
  /** 面包屑导航 */
  breadcrumbs?: BreadcrumbItem[]
}>()

const router = useRouter()
const route = useRoute()

const handleBack = () => {
  if (props.backPath) {
    router.push(props.backPath)
    return
  }
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/dashboard')
  }
}
</script>

<template>
  <div class="page-header" :style="{ marginBottom: typeof marginBottom === 'number' ? `${marginBottom}px` : marginBottom }">
    <div class="page-header-left">
      <el-button
        v-if="showBack"
        text
        :icon="ArrowLeft"
        class="back-btn"
        @click="handleBack"
      >
        返回
      </el-button>
      <div class="page-header-text">
        <nav v-if="breadcrumbs && breadcrumbs.length" class="breadcrumb-nav" aria-label="breadcrumb">
          <span
            v-for="(crumb, index) in breadcrumbs"
            :key="index"
            class="breadcrumb-item"
            :class="{ 'breadcrumb-last': index === breadcrumbs.length - 1 }"
          >
            <el-link
              v-if="crumb.path && index !== breadcrumbs.length - 1"
              type="primary"
              :underline="false"
              @click="router.push(crumb.path)"
            >
              {{ crumb.label }}
            </el-link>
            <span v-else>{{ crumb.label }}</span>
            <span v-if="index < breadcrumbs.length - 1" class="breadcrumb-separator">/</span>
          </span>
        </nav>
        <h2>{{ title }}</h2>
        <p v-if="subtitle" class="page-header-subtitle">{{ subtitle }}</p>
      </div>
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
  flex-wrap: wrap;
  gap: 12px;
}

.page-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.back-btn {
  padding: 6px 10px !important;
  color: #64748b !important;
}

.back-btn:hover {
  color: #1e3a5f !important;
}

.page-header-text {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.breadcrumb-nav {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 2px;
}

.breadcrumb-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.breadcrumb-last {
  color: #64748b;
  font-weight: 500;
}

.breadcrumb-separator {
  color: #cbd5e1;
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
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .page-header {
    margin-bottom: 16px;
  }

  .page-header-left {
    gap: 8px;
  }

  .page-header h2 {
    font-size: 18px;
  }

  .back-btn {
    padding: 4px 6px !important;
  }

  .back-btn span {
    display: none;
  }
}
</style>
