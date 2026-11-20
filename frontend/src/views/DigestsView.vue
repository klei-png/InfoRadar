<template>
  <div class="digest-toolbar">
    <button class="fb" type="button" :disabled="generating" @click="onGenerate">
      {{ generating ? '生成中…（约 1~3 分钟）' : '采集并生成最新简报' }}
    </button>
    <span v-if="generateNotice" class="gen-notice">{{ generateNotice }}</span>
  </div>

  <!-- 生成失败（含 409 已有任务进行中）：可继续浏览已有简报 -->
  <ErrorBanner v-if="genError" :message="genError" :retryable="false" />

  <LoadingState v-if="loading" />
  <ErrorBanner v-else-if="listError" :message="listError" @retry="retry" />
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
import { digestList, digestDetail, generateDigest } from '../api/digests'
import { useAsyncTask } from '../composables/useAsyncTask'
import { renderMarkdown } from '../utils/markdown'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorBanner from '../components/ui/ErrorBanner.vue'
import LoadingState from '../components/ui/LoadingState.vue'

const listTask = useAsyncTask((_signal, days) => digestList(days))
const { loading, error: listError, data, run: loadList, retry } = listTask
const list = computed(() => data.value || [])

// 生成任务独立于列表任务：生成期间可继续浏览已有简报
const genTask = useAsyncTask(() => generateDigest())
const generating = genTask.loading
const genError = genTask.error
const generateNotice = ref('')

const expandError = ref('')

onMounted(() => loadList(7))

async function onGenerate() {
  generateNotice.value = ''
  const result = await genTask.run() // 全链路 1~3 分钟，超时分级在 api 层
  if (!result) return // 失败/被取消——错误态由 genTask 承载
  const n = result.digests
  generateNotice.value = n > 0 ? `已生成 ${n} 篇简报` : '本次没有可生成的新简报'
  loadList(7) // 成功后刷新列表
}

// 旧后端按 category 取最新一篇
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
.digest-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.gen-notice {
  color: var(--color-success);
  font-size: var(--font-size-sm);
}

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
