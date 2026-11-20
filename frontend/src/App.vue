<template>
  <header>
    <h1>InforRadar</h1>
    <nav>
      <RouterLink to="/">每日简报</RouterLink>
      <RouterLink to="/feed">信息流</RouterLink>
      <RouterLink to="/ask">问答</RouterLink>
      <a href="#" @click.prevent="logout">退出</a>
    </nav>
  </header>
  <main><RouterView /></main>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { clearToken } from './api/client'

const router = useRouter()
const logout = () => {
  clearToken()
  router.push('/login')
}
</script>
