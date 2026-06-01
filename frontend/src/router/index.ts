import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/LoginPage.vue'),
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/pages/RegisterPage.vue'),
  },
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/pages/DashboardPage.vue'),
      },
      {
        path: 'delivery/:id',
        name: 'delivery-detail',
        component: () => import('@/pages/DeliveryDetailPage.vue'),
      },
      {
        path: 'calendar',
        name: 'calendar',
        component: () => import('@/pages/CalendarPage.vue'),
      },
      {
        path: 'radar',
        name: 'radar',
        component: () => import('@/pages/RadarPage.vue'),
      },
      {
        path: 'resumes',
        name: 'resumes',
        component: () => import('@/pages/ResumesPage.vue'),
      },
      {
        path: 'reviews',
        name: 'reviews',
        component: () => import('@/pages/ReviewsPage.vue'),
      },
      {
        path: 'statistics',
        name: 'statistics',
        component: () => import('@/pages/StatisticsPage.vue'),
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/pages/SettingsPage.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()
  const publicPaths = ['/login', '/register']
  if (!publicPaths.includes(to.path) && !authStore.token) {
    next('/login')
  } else if (publicPaths.includes(to.path) && authStore.token) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
