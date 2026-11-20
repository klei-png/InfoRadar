<template>
  <p v-if="loading" class="empty">加载中…</p>
  <p v-else-if="!items.length" class="empty">暂无数据</p>
  <div v-for="it in items" v-else :key="it.id" class="card">
    <div class="meta">
      <span class="badge">{{ it.category }}</span>
      <span class="badge">评分 {{ it.model_score }}</span>
      {{ fmtTime(it.published_at) }}
    </div>
    <div class="item-title">
      <a :href="it.url" target="_blank" rel="noopener">{{ it.title }}</a>
    </div>
    <div class="snippet">
      {{ it.snippet }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { items as fetchItems } from '../api/items'

const items = ref([])
const loading = ref(true)

const fmtTime = (t) => (t ? String(t).slice(0, 16).replace('T', ' ') : '时间未知')

onMounted(async () => {
  items.value = await fetchItems(6, 30)
  loading.value = false
})
</script>
