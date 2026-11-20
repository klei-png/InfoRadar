<template>
  <div class="card notfound">
    <p class="empty">404 · 页面不存在</p>
    <button class="fb" type="button" @click="router.push('/')">返回首页</button>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<style scoped>
.notfound {
  text-align: center;
}
</style>
