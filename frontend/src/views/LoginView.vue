<template>
  <div class="login-box">
    <h2>InforRadar 登录</h2>
    <input v-model="username" placeholder="用户名" />
    <input v-model="pwd" type="password" placeholder="密码" @keydown.enter="doLogin" />
    <button :disabled="loading" @click="doLogin">{{ loading ? '登录中…' : '进入' }}</button>
    <div v-if="err" class="login-err">
      {{ err }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api/auth'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'

const username = ref('admin')
const pwd = ref('')
const err = ref('')
const loading = ref(false)
const router = useRouter()
const auth = useAuthStore()

async function doLogin() {
  if (loading.value) return
  err.value = ''
  loading.value = true
  try {
    const data = await login(username.value.trim(), pwd.value)
    auth.setToken(data.token)
    // 回跳登录前想访问的目标页（守卫以 redirect query 记录）
    router.push(String(router.currentRoute.value.query.redirect || '/'))
  } catch (e) {
    // login 401 经 http.js 分流后原样抛出，message 已面向用户
    err.value = e instanceof ApiError ? e.message : '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>
