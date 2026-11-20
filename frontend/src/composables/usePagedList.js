import { computed, ref } from 'vue'
import { useAsyncTask } from './useAsyncTask'

function dedupeById(rows) {
  const seen = new Set()
  const out = []
  for (const row of rows) {
    if (row?.id == null || seen.has(row.id)) continue
    seen.add(row.id)
    out.push(row)
  }
  return out
}

/**
 * offset 分页列表（web-frontend-plan §3.3）。
 *
 * 约定：fetchPage({ offset, limit, signal, ...filters }) → { data, total, has_more }（§3.8）。
 *
 * - load()：拉第一页（重置 offset）；进行中再 load 会取消旧请求刷新
 * - loadMore()：追加下一页；loading 中或无更多数据时为 no-op（防重复提交）
 * - setFilters(next)：合并筛选、重置 offset 并取消在途请求（竞态由 useAsyncTask 守卫）
 * - 按 id 去重；失败保留已加载数据，retry() 就地重试
 * - removeById(id)：删除成功后本地移除卡片（§3.7）
 *
 * 已知局限（D13，接受）：offset 分页在数据持续插入时可能重复/遗漏。
 */
export function usePagedList(fetchPage, { pageSize = 30, initialFilters = {} } = {}) {
  const list = ref([])
  const total = ref(0)
  const hasMore = ref(false)
  const filters = ref({ ...initialFilters })

  const task = useAsyncTask((signal, params) => fetchPage({ ...params, signal }))

  const loading = computed(() => task.loading.value && list.value.length === 0)
  const loadingMore = computed(() => task.loading.value && list.value.length > 0)
  const canLoadMore = computed(() => hasMore.value && !task.loading.value)

  let lastOffset = 0

  async function requestPage(offset) {
    lastOffset = offset
    const result = await task.run({ offset, limit: pageSize, ...filters.value })
    if (!result) return // 已取消 / 被新任务取代 / 出错——错误态由 task 统一承载
    const rows = Array.isArray(result.data) ? result.data : []
    const merged = offset === 0 ? rows : [...list.value, ...rows]
    list.value = dedupeById(merged)
    total.value = result.total ?? list.value.length
    hasMore.value = !!result.has_more
  }

  const load = () => requestPage(0)

  function loadMore() {
    if (task.loading.value || !hasMore.value) return undefined
    return requestPage(list.value.length)
  }

  function setFilters(next) {
    filters.value = { ...filters.value, ...next }
    return requestPage(0)
  }

  function removeById(id) {
    list.value = list.value.filter((row) => row.id !== id)
  }

  // 重试必须重走 requestPage（含合并/去重逻辑），不能透传 task.retry 直写 data
  function retry() {
    return requestPage(lastOffset)
  }

  return {
    list,
    total,
    hasMore,
    filters,
    loading,
    loadingMore,
    canLoadMore,
    error: task.error,
    load,
    loadMore,
    setFilters,
    removeById,
    retry,
  }
}
