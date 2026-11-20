import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { title: '登录' } },
  { path: '/', component: () => import('../views/DigestsView.vue'), meta: { title: '每日简报' } },
  { path: '/feed', component: () => import('../views/FeedView.vue'), meta: { title: '信息流' } },
  {
    path: '/:pathMatch(.*)*',
    component: () => import('../views/NotFoundView.vue'),
    meta: { title: '页面不存在' },
  },
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

// 浏览器标签页标题跟随路由
router.afterEach((to) => {
  document.title = to.meta?.title ? `InforRadar · ${to.meta.title}` : 'InforRadar'
})
