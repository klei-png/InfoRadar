<template>
  <header>
    <h1>InforRadar</h1>
    <nav>
      <RouterLink to="/">每日简报</RouterLink>
      <RouterLink to="/feed">信息流</RouterLink>
      <a href="#" @click.prevent="logout">退出</a>
    </nav>
  </header>
  <main><RouterView /></main>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const auth = useAuthStore()

// 登出统一走 store（§3.2）：清 token + 跳登录，页面级数据随路由销毁
const logout = () => {
  auth.clearToken()
  router.push('/login')
}
</script>
