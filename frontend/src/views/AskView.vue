<template>
  <div class="card">
    <input
      v-model="question"
      placeholder="问点什么，比如：最近AI领域有什么大新闻？"
      @keydown.enter="doAsk"
    />
    <button id="askbtn" @click="doAsk">提问</button>
  </div>
  <p v-if="loading" class="empty">思考中…</p>
  <template v-if="answer">
    <div class="card">
      <pre class="md">{{ answer }}</pre>
    </div>
    <div v-if="sources.length" class="card">
      <div class="meta">来源</div>
      <div v-for="s in sources" :key="s.id">
        · <a :href="s.url" target="_blank" rel="noopener">{{ s.title }}</a>
        <span class="sim">[{{ s.id }}] 相似度 {{ s.similarity }}</span>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api/client'

const question = ref('')
const answer = ref('')
const sources = ref([])
const loading = ref(false)

async function doAsk() {
  const q = question.value.trim()
  if (!q || loading.value) return
  loading.value = true
  answer.value = ''
  sources.value = []
  try {
    const data = await api.ask(q)
    answer.value = data.answer
    sources.value = data.sources || []
  } catch (e) {
    answer.value = `请求失败：${e.message}`
  } finally {
    loading.value = false
  }
}
</script>
