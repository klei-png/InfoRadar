<template>
  <LoadingState v-if="loading" />
  <ErrorBanner v-else-if="error" :message="error" @retry="retry" />
  <EmptyState v-else-if="!list.length" text="还没有简报" />
  <template v-else>
    <ErrorBanner v-if="expandError" :message="expandError" :retryable="false" />
    <div v-for="d in list" :key="d.category + d.date" class="card">
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
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { digestList, digestDetail } from '../api/digests'
import { useAsyncTask } from '../composables/useAsyncTask'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorBanner from '../components/ui/ErrorBanner.vue'
import LoadingState from '../components/ui/LoadingState.vue'

const { loading, error, data, run, retry } = useAsyncTask((_signal, days) => digestList(days))
const list = computed(() => data.value || [])

const expandError = ref('')

onMounted(() => run(7))

async function expand(d) {
  if (d.full) {
    d.full = ''
    return
  }
  expandError.value = ''
  try {
    const full = await digestDetail(d.category)
    d.full = full.content_md
  } catch (e) {
    expandError.value = e?.message || '加载全文失败'
  }
}
</script>
