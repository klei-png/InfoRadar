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
      <!-- eslint-disable-next-line vue/no-v-html -- 内容经 renderMarkdown 白名单渲染，已整体转义（D5） -->
      <div v-if="d.full" class="md-content" v-html="renderMarkdown(d.full)"></div>
      <div v-else class="snippet">{{ d.preview }}…</div>
    </div>
  </template>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { digestList, digestDetail } from '../api/digests'
import { useAsyncTask } from '../composables/useAsyncTask'
import { renderMarkdown } from '../utils/markdown'
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

<style scoped>
.md-content {
  font-size: var(--font-size-md);
  line-height: 1.7;
}

.md-content :deep(p) {
  margin: 8px 0;
}

.md-content :deep(h3),
.md-content :deep(h4),
.md-content :deep(h5) {
  margin: 14px 0 8px;
  font-size: var(--font-size-base);
}

.md-content :deep(ul),
.md-content :deep(ol) {
  margin: 8px 0;
  padding-left: 22px;
}

.md-content :deep(li) {
  margin: 4px 0;
}

.md-content :deep(code) {
  background: var(--color-hover);
  border-radius: var(--radius-sm);
  padding: 1px 5px;
  font-size: var(--font-size-sm);
}

.md-content :deep(pre) {
  background: var(--color-hover);
  border-radius: var(--radius-md);
  padding: 12px;
  overflow-x: auto;
}

.md-content :deep(pre code) {
  background: transparent;
  padding: 0;
}

.md-content :deep(a) {
  color: var(--color-primary);
}
</style>
