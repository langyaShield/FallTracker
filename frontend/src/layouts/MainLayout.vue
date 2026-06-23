<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { computed, markRaw, ref, onMounted, onUnmounted } from 'vue'
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
  Key,
  Fold,
  Postcard,
  CopyDocument,
} from '@element-plus/icons-vue'
import NotificationCenter from '@/components/NotificationCenter.vue'
import QuickCopyDrawer from '@/components/QuickCopyDrawer.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)

// 快捷复制抽屉
const quickCopyVisible = ref(false)

// 响应式：检测移动端
const MOBILE_BREAKPOINT = 768
const isMobile = ref(window.innerWidth <= MOBILE_BREAKPOINT)
const drawerVisible = ref(false)

const handleResize = () => {
  isMobile.value = window.innerWidth <= MOBILE_BREAKPOINT
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

// 当前页面标题
const pageTitle = computed(() => {
  const item = menuItems.value.find(m => m.path === route.path)
  return item?.title || 'FallTracker'
})

const menuItems = computed(() => {
  const items = [
    { path: '/dashboard', title: '投递大盘', icon: markRaw(Grid) },
    { path: '/calendar', title: '日历视图', icon: markRaw(Calendar) },
    { path: '/radar', title: '爬虫雷达', icon: markRaw(Aim) },
    { path: '/profile', title: '信息库', icon: markRaw(Postcard) },
    { path: '/resumes', title: '简历管理', icon: markRaw(Document) },
    { path: '/reviews', title: '面试复盘', icon: markRaw(EditPen) },
    { path: '/statistics', title: '数据统计', icon: markRaw(TrendCharts) },
    { path: '/settings', title: '设置', icon: markRaw(Setting) },
  ]
  if (authStore.user?.is_admin) {
    items.push({ path: '/admin', title: '用户管理', icon: markRaw(Key) })
  }
  return items
})

const handleLogout = () => {
  authStore.logout()
  router.push('/login')
}

// 移动端点击菜单项后关闭抽屉
const handleMenuSelect = () => {
  if (isMobile.value) {
    drawerVisible.value = false
  }
}

const openDrawer = () => {
  drawerVisible.value = true
}
</script>

<template>
  <!-- 移动端顶部导航栏 -->
  <div v-if="isMobile" class="mobile-header">
    <div class="mobile-header-left">
      <button class="hamburger-btn" @click="openDrawer" aria-label="打开菜单">
        <Fold />
      </button>
      <span class="mobile-title">{{ pageTitle }}</span>
    </div>
    <div class="mobile-header-right">
      <div class="mobile-quick-copy-btn" @click="quickCopyVisible = true" aria-label="快捷复制">
        <CopyDocument style="width: 20px; height: 20px;" />
      </div>
      <NotificationCenter />
    </div>
  </div>

  <el-container class="main-layout" :class="{ 'is-mobile': isMobile }">
    <!-- 桌面端：固定侧边栏 -->
    <el-aside v-if="!isMobile" width="220px" class="sidebar">
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
        <div class="sidebar-footer-top">
          <NotificationCenter />
          <span class="notification-label">通知</span>
          <div class="quick-copy-trigger" @click="quickCopyVisible = true" title="快捷复制">
            <el-icon :size="18"><CopyDocument /></el-icon>
          </div>
          <span class="notification-label">快捷复制</span>
        </div>
        <div class="sidebar-footer-bottom">
          <div class="user-info" @click="router.push('/change-password')" title="修改密码">
            <el-icon :size="18"><User /></el-icon>
            <span>{{ authStore.user?.username || '用户' }}</span>
          </div>
          <el-button class="logout-btn" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
            退出
          </el-button>
        </div>
      </div>
    </el-aside>

    <!-- 移动端：抽屉式侧边栏 -->
    <el-drawer
      v-if="isMobile"
      v-model="drawerVisible"
      direction="ltr"
      :size="260"
      :show-close="false"
      class="mobile-drawer"
    >
      <template #header>
        <div class="drawer-header">
          <span class="logo-icon">FT</span>
          <span class="logo-text">FallTracker</span>
        </div>
      </template>
      <el-menu
        :default-active="activeMenu"
        router
        class="drawer-menu"
        background-color="#fff"
        text-color="#334155"
        active-text-color="#1e3a5f"
        @select="handleMenuSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>
      <div class="drawer-footer">
        <div class="drawer-user" @click="router.push('/change-password'); drawerVisible = false">
          <el-icon :size="18"><User /></el-icon>
          <span>{{ authStore.user?.username || '用户' }}</span>
        </div>
        <el-button class="drawer-logout" @click="handleLogout">
          <el-icon><SwitchButton /></el-icon>
          退出登录
        </el-button>
      </div>
    </el-drawer>

    <!-- 主内容区 -->
    <el-main class="main-content" :class="{ 'mobile-content': isMobile }">
      <router-view />
    </el-main>
  </el-container>

  <!-- 快捷复制抽屉（全局可用） -->
  <QuickCopyDrawer v-model="quickCopyVisible" />
</template>

<style scoped>
/* 移动端顶部导航栏 */
.mobile-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 52px;
  background: #1e3a5f;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.mobile-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hamburger-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  color: #fff;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.2s;
}

.hamburger-btn:active {
  background: rgba(255, 255, 255, 0.15);
}

.hamburger-btn svg {
  width: 22px;
  height: 22px;
}

.mobile-title {
  font-size: 17px;
  font-weight: 600;
}

.mobile-header-right {
  display: flex;
  align-items: center;
}

/* 主布局 */
.main-layout {
  height: 100vh;
  overflow: hidden;
}

.main-layout.is-mobile {
  padding-top: 52px;
  height: 100vh;
}

/* 桌面端侧边栏 */
.sidebar {
  background: #1e3a5f;
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
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
  flex-shrink: 0;
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
  padding: 12px 16px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.sidebar-footer-top {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr;
  align-items: center;
  gap: 6px 8px;
  padding-bottom: 12px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.notification-label {
  color: #cbd5e1;
  font-size: 13px;
}

/* 桌面端快捷复制触发按钮 */
.quick-copy-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #cbd5e1;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.2s, color 0.2s;
}

.quick-copy-trigger:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f59e0b;
}

/* 移动端快捷复制按钮 */
.mobile-quick-copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #fff;
  cursor: pointer;
  border-radius: 6px;
  margin-right: 4px;
}

.mobile-quick-copy-btn:active {
  background: rgba(255, 255, 255, 0.15);
}

.sidebar-footer-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #cbd5e1;
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.user-info:hover {
  background: rgba(255, 255, 255, 0.08);
}

.logout-btn {
  color: #fca5a5 !important;
  background: transparent !important;
  border: none !important;
  padding: 4px 8px !important;
  font-size: 13px !important;
  transition: color 0.2s;
}

.logout-btn:hover {
  color: #f87171 !important;
  background: rgba(248, 113, 113, 0.1) !important;
  border-radius: 4px;
}

/* 主内容区 */
.main-content {
  background: #f1f5f9;
  padding: 24px;
  height: 100vh;
  overflow-y: auto;
}

.main-content.mobile-content {
  padding: 12px;
  height: calc(100vh - 52px);
}

/* 移动端抽屉样式 */
.drawer-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 0;
}

.drawer-header .logo-text {
  color: #1e3a5f;
}

.drawer-menu .el-menu-item.is-active {
  background: rgba(30, 58, 95, 0.08) !important;
  font-weight: 600;
}

.drawer-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 16px;
  border-top: 1px solid #e2e8f0;
  background: #fff;
}

.drawer-user {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #334155;
  font-size: 14px;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
  margin-bottom: 8px;
  transition: background 0.2s;
}

.drawer-user:active {
  background: #f1f5f9;
}

.drawer-logout {
  width: 100%;
  color: #ef4444 !important;
  background: #fef2f2 !important;
  border: none !important;
}

.drawer-logout:active {
  background: #fee2e2 !important;
}

/* dvh 支持时修复高度 */
@supports (height: 100dvh) {
  .main-layout,
  .sidebar,
  .main-content {
    height: 100dvh;
  }

  .main-layout.is-mobile {
    height: 100dvh;
  }

  .main-content.mobile-content {
    height: calc(100dvh - 52px);
  }
}
</style>
