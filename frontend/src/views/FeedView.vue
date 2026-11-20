<template>
  <div class="toolbar">
    <nav class="tabs">
      <button
        v-for="tab in CATEGORY_TABS"
        :key="tab.value"
        class="tab"
        :class="{ active: filters.category === tab.value }"
        type="button"
        @click="categoryValue = tab.value"
      >
        {{ tab.label }}
      </button>
    </nav>
    <select v-model.number="scoreValue" class="score-select" aria-label="评分筛选">
      <option :value="0">全部评分</option>
      <option v-for="s in [6, 7, 8]" :key="s" :value="s">≥ {{ s }} 分</option>
    </select>
  </div>

  <LoadingState v-if="loading" />
  <ErrorBanner v-else-if="error" :message="error" @retry="retry" />
  <EmptyState v-else-if="!list.length" text="暂无数据" />
  <template v-else>
    <div v-for="it in list" :key="it.id" class="card">
      <div class="meta">
        <CategoryBadge :category="it.category" />
        <ScoreBadge :score="it.model_score" />
        {{ formatTime(it.published_at) }}
      </div>
      <div class="item-title">
        <a :href="it.url" target="_blank" rel="noopener">{{ it.title }}</a>
      </div>
      <div class="snippet">
        {{ it.snippet }}
      </div>
    </div>
    <div v-if="canLoadMore" class="load-more">
      <button class="fb" type="button" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? '加载中…' : '加载更多' }}
      </button>
    </div>
  </template>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { items as fetchItems } from '../api/items'
import { usePagedList } from '../composables/usePagedList'
import { formatTime } from '../utils/format'
import CategoryBadge from '../components/ui/CategoryBadge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorBanner from '../components/ui/ErrorBanner.vue'
import LoadingState from '../components/ui/LoadingState.vue'
import ScoreBadge from '../components/ui/ScoreBadge.vue'

// 旧后端无 DELETE /items：删除入口待后端软删除就绪后恢复（DeleteButton 组件已就绪）

// 与 sources.yaml 的 category 取值对齐；后端扩展信息源时同步维护
const CATEGORY_TABS = [
  { value: '', label: '全部' },
  { value: 'ai', label: 'AI' },
  { value: 'finance', label: '金融' },
]

const {
  list,
  filters,
  loading,
  loadingMore,
  canLoadMore,
  error,
  load,
  loadMore,
  setFilters,
  retry,
} = usePagedList((params) => fetchItems(params), {
  pageSize: 30,
  initialFilters: { min_score: 6, category: '' },
})

// 筛选控件：写入即触发 setFilters（重置 offset 并取消在途请求，竞态由 composable 守卫）
const categoryValue = computed({
  get: () => filters.value.category,
  set: (v) => setFilters({ category: v }),
})
const scoreValue = computed({
  get: () => filters.value.min_score,
  set: (v) => setFilters({ min_score: v }),
})

onMounted(load) // 首屏拉第一页
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.tabs {
  display: flex;
  gap: 4px;
}

.tab {
  border: none;
  background: transparent;
  padding: 6px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--font-size-base);
  color: var(--color-text-muted);
}

.tab.active {
  background: var(--color-primary);
  color: var(--color-on-primary);
}

.score-select {
  padding: 6px 10px;
  border: 1px solid var(--color-input-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: var(--color-text);
}

.load-more {
  text-align: center;
  margin: 16px 0;
}
</style>
