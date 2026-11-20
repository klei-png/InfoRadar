<template>
  <LoadingState v-if="loading" />
  <ErrorBanner v-else-if="error" :message="error" @retry="retry" />
  <EmptyState v-else-if="!list.length" />
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
  </template>
</template>

<script setup>
import { onMounted } from 'vue'
import { items as fetchItems } from '../api/items'
import { usePagedList } from '../composables/usePagedList'
import { formatTime } from '../utils/format'
import CategoryBadge from '../components/ui/CategoryBadge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import ErrorBanner from '../components/ui/ErrorBanner.vue'
import LoadingState from '../components/ui/LoadingState.vue'
import ScoreBadge from '../components/ui/ScoreBadge.vue'

// offset 分页 S4 接入：后端按 §3.8 契约实现 offset 后启用
const { list, loading, error, load, retry } = usePagedList(
  ({ min_score, limit }) => fetchItems(min_score, limit),
  { pageSize: 30, initialFilters: { min_score: 6 } }
)

onMounted(load)
</script>
