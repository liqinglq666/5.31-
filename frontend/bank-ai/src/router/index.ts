import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { useUserStore } from '@/store'

NProgress.configure({ showSpinner: false })

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue'),
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/Admin.vue'),
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/components/ChatDetail.vue'),
  },
  {
    path: '/review',
    name: 'ContractReview',
    component: () => import('@/views/ContractReview.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  NProgress.start()
  const userStore = useUserStore()
  if (to.meta?.public) {
    return true
  }
  // 游客直接放行
  if (userStore.isGuest) {
    return true
  }
  // 如果 token 存在但 userInfo 丢失（如新窗口打开），自动恢复用户信息
  if (!userStore.isLoggedIn && userStore.token) {
    await userStore.fetchUserInfo()
  }
  if (!userStore.isLoggedIn) {
    return '/login'
  }
  return true
})

router.afterEach(() => {
  NProgress.done()
})

router.onError(() => {
  NProgress.done()
})

export default router
