import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/', component: () => import('../views/DigestsView.vue') },
  { path: '/feed', component: () => import('../views/FeedView.vue') },
]

export const router = createRouter({
  history: createWebHashHistory(), // hash 模式：后端无需配置历史回退
  routes,
})

// 登录守卫（读 auth store，§3.5）：
// - 未登录访问受保护页 → 跳 /login 并以 redirect 记录原目标页
// - 已登录访问 /login → 跳首页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path === '/login') {
    return auth.isLoggedIn ? '/' : true
  }
  if (!auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
})
