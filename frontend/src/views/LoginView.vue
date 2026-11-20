<template>
  <div class="login-box">
    <h2>InforRadar 登录</h2>
    <input v-model="username" placeholder="用户名" />
    <input v-model="pwd" type="password" placeholder="密码" @keydown.enter="doLogin" />
    <button @click="doLogin">进入</button>
    <div v-if="err" class="login-err">
      {{ err }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, setToken } from '../api/client'

const username = ref('admin')
const pwd = ref('')
const err = ref('')
const router = useRouter()

async function doLogin() {
  try {
    const data = await api.login(username.value.trim(), pwd.value)
    setToken(data.token)
    router.push('/')
  } catch {
    err.value = '用户名或密码错误'
  }
}
</script>
