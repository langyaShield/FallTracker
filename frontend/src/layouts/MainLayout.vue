<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { computed, markRaw } from 'vue'
import {
  Grid,
  Calendar,
  Aim,
  Document,
  EditPen,
  TrendCharts,
  Setting,
  User,
  SwitchButton,
} from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)

const menuItems = [
  { path: '/dashboard', title: '投递大盘', icon: markRaw(Grid) },
  { path: '/calendar', title: '日历视图', icon: markRaw(Calendar) },
  { path: '/radar', title: '爬虫雷达', icon: markRaw(Aim) },
  { path: '/resumes', title: '简历管理', icon: markRaw(Document) },
  { path: '/reviews', title: '面试复盘', icon: markRaw(EditPen) },
  { path: '/statistics', title: '数据统计', icon: markRaw(TrendCharts) },
  { path: '/settings', title: '设置', icon: markRaw(Setting) },
]

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="main-layout">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <span class="logo-icon">FT</span>
        <span class="logo-text">FallTracker</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="sidebar-menu"
        background-color="#1e3a5f"
        text-color="#cbd5e1"
        active-text-color="#f59e0b"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <div class="user-info">
          <el-icon><User /></el-icon>
          <span>{{ authStore.user?.username || '用户' }}</span>
        </div>
        <el-button type="danger" text size="small" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          退出
        </el-button>
      </div>
    </el-aside>
    <el-main class="main-content">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.main-layout {
  min-height: 100vh;
}

.sidebar {
  background: #1e3a5f;
  display: flex;
  flex-direction: column;
}

.logo {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-icon {
  width: 36px;
  height: 36px;
  background: linear-gradient(135deg, #f59e0b, #d97706);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  color: #fff;
  font-size: 14px;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: #fff;
}

.sidebar-menu {
  flex: 1;
  border-right: none;
}

.sidebar-menu .el-menu-item {
  height: 50px;
  line-height: 50px;
}

.sidebar-menu .el-menu-item.is-active {
  background: rgba(245, 158, 11, 0.15) !important;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: 14px;
  margin-bottom: 12px;
}

.footer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.main-content {
  background: #f1f5f9;
  padding: 24px;
}
</style>
