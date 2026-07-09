import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PUBLIC_PATHS } from '@/lib/constants'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/pages/RegisterPage.vue'),
    meta: { title: '注册' },
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'home',
        name: 'home',
        component: () => import('@/pages/HomePage.vue'),
        meta: { title: '首页' },
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/pages/DashboardPage.vue'),
        meta: { title: '投递大盘' },
      },
      {
        path: 'delivery/:id',
        name: 'delivery-detail',
        component: () => import('@/pages/DeliveryDetailPage.vue'),
        meta: { title: '投递详情' },
      },
      {
        path: 'calendar',
        name: 'calendar',
        component: () => import('@/pages/CalendarPage.vue'),
        meta: { title: '日历视图' },
      },
      {
        path: 'radar',
        name: 'radar',
        component: () => import('@/pages/RadarPage.vue'),
        meta: { title: '爬虫雷达' },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/pages/ProfilePage.vue'),
        meta: { title: '信息库' },
      },
      {
        path: 'bookmarks',
        name: 'bookmarks',
        component: () => import('@/pages/BookmarksPage.vue'),
        meta: { title: '常用网站' },
      },
      {
        path: 'resumes',
        name: 'resumes',
        component: () => import('@/pages/ResumesPage.vue'),
        meta: { title: '简历管理' },
      },
      {
        path: 'reviews',
        name: 'reviews',
        component: () => import('@/pages/ReviewsPage.vue'),
        meta: { title: '面试复盘' },
      },
      {
        path: 'statistics',
        name: 'statistics',
        component: () => import('@/pages/StatisticsPage.vue'),
        meta: { title: '数据统计' },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/pages/SettingsPage.vue'),
        meta: { title: '设置' },
      },
      {
        path: 'change-password',
        name: 'change-password',
        component: () => import('@/pages/ChangePasswordPage.vue'),
        meta: { title: '修改密码' },
      },
      {
        path: 'admin',
        name: 'admin',
        component: () => import('@/pages/AdminPage.vue'),
        meta: { title: '用户管理', requiresAdmin: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFoundPage.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  const isPublic = (PUBLIC_PATHS as readonly string[]).includes(to.path)

  if (isPublic && authStore.token) {
    next('/dashboard')
  } else if (!isPublic && !authStore.token) {
    next('/login')
  } else {
    // 页面刷新后 token 存在但 user 为空时，自动获取用户信息
    if (!isPublic && authStore.token && !authStore.user) {
      try {
        await authStore.fetchMe()
      } catch {
        // fetchMe 失败（token 过期等），auth 拦截器会处理跳转
      }
    }

    // Security: block disabled users from accessing the app
    if (!isPublic && authStore.user?.is_disabled) {
      authStore.logout()
      next('/login')
      return
    }

    // Security: restrict admin-only routes
    if (to.meta.requiresAdmin && !authStore.user?.is_admin) {
      next('/dashboard')
      return
    }

    next()
  }
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} - FallTracker` : 'FallTracker'
})

export default router
