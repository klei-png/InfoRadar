import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '../api/client'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue') },
  { path: '/', component: () => import('../views/DigestsView.vue') },
  { path: '/feed', component: () => import('../views/FeedView.vue') },
  { path: '/ask', component: () => import('../views/AskView.vue') },
]

export const router = createRouter({
  history: createWebHashHistory(), // hash 模式：后端无需配置历史回退
  routes,
})

// 登录守卫：无 token 一律踢到登录页
router.beforeEach((to) => {
  if (to.path !== '/login' && !getToken()) return '/login'
})
