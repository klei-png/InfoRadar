<template>
  <p v-if="loading" class="empty">加载中…</p>
  <p v-else-if="!list.length" class="empty">还没有简报</p>
  <div v-for="d in list" v-else :key="d.category + d.date" class="card">
    <div class="meta">
      <span class="badge">{{ d.category }}</span>
      {{ d.date }} · {{ d.item_count }} 条信息 · {{ d.cost_tokens }} tokens
      <button class="fb" style="float: right" @click="expand(d)">
        {{ d.full ? '收起' : '查看全文' }}
      </button>
    </div>
    <pre v-if="d.full" class="md">{{ d.full }}</pre>
    <div v-else class="snippet">{{ d.preview }}…</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/client'

const list = ref([])
const loading = ref(true)

onMounted(async () => {
  list.value = await api.digests(7)
  loading.value = false
})

async function expand(d) {
  if (d.full) {
    d.full = ''
    return
  }
  const full = await api.digestFull(d.category)
  d.full = full.content_md
}
</script>
