import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { usePagedList } from '../usePagedList'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function mountPagedList(fetchPage, opts) {
  let api
  const Host = defineComponent({
    setup() {
      api = usePagedList(fetchPage, opts)
      return () => h('div')
    },
  })
  mount(Host)
  return api
}

const page = (ids, hasMore = true, total) => ({
  data: ids.map((id) => ({ id })),
  has_more: hasMore,
  total: total ?? ids.length,
})

describe('usePagedList', () => {
  it('load 首页：填充列表与分页元信息', async () => {
    const fetchPage = vi.fn(() => Promise.resolve(page([1, 2, 3], true, 30)))
    const api = mountPagedList(fetchPage, { pageSize: 3 })
    await api.load()
    expect(fetchPage).toHaveBeenCalledWith(expect.objectContaining({ offset: 0, limit: 3 }))
    expect(api.list.value.map((r) => r.id)).toEqual([1, 2, 3])
    expect(api.total.value).toBe(30)
    expect(api.hasMore.value).toBe(true)
    expect(api.canLoadMore.value).toBe(true)
    expect(api.loading.value).toBe(false)
  })

  it('loadMore 追加且按 id 去重，无更多数据时禁止加载', async () => {
    const fetchPage = vi.fn((p) =>
      Promise.resolve(p.offset === 0 ? page([1, 2], true) : page([2, 3], false))
    )
    const api = mountPagedList(fetchPage, { pageSize: 2 })
    await api.load()
    await api.loadMore()
    expect(api.list.value.map((r) => r.id)).toEqual([1, 2, 3])
    expect(api.hasMore.value).toBe(false)
    expect(api.canLoadMore.value).toBe(false)
  })

  it('loadMore 进行中重复触发不并发', async () => {
    let resolveMore
    const fetchPage = vi.fn((p) =>
      p.offset === 0
        ? Promise.resolve(page([1], true))
        : new Promise((res) => {
            resolveMore = res
          })
    )
    const api = mountPagedList(fetchPage, { pageSize: 1 })
    await api.load()
    const first = api.loadMore()
    expect(api.loadingMore.value).toBe(true)
    const second = api.loadMore() // loading 中 → no-op
    expect(second).toBeUndefined()
    resolveMore(page([2], false))
    await first
    expect(fetchPage).toHaveBeenCalledTimes(2)
    expect(api.list.value.map((r) => r.id)).toEqual([1, 2])
  })

  it('hasMore 为 false 时 loadMore 是 no-op', async () => {
    const fetchPage = vi.fn(() => Promise.resolve(page([1], false)))
    const api = mountPagedList(fetchPage, { pageSize: 1 })
    await api.load()
    const result = await api.loadMore()
    expect(result).toBeUndefined()
    expect(fetchPage).toHaveBeenCalledTimes(1)
  })

  it('筛选变化：重置 offset 并取消在途请求，旧结果不覆盖', async () => {
    const gates = { ai: { 0: deferred() }, finance: { 0: deferred() } }
    const fetchPage = vi.fn((p) => gates[p.category][p.offset].promise)
    const api = mountPagedList(fetchPage, { pageSize: 2, initialFilters: { category: 'ai' } })

    const slowRun = api.load()
    const switched = api.setFilters({ category: 'finance' }) // 取消 ai 在途请求
    gates.finance[0].resolve(page([9], false))
    gates.ai[0].resolve(page([1, 2], true)) // 旧筛选的响应此时才返回
    await Promise.all([slowRun, switched])
    await flushPromises()

    expect(api.list.value.map((r) => r.id)).toEqual([9])
    expect(api.filters.value.category).toBe('finance')
  })

  it('加载失败保留已加载数据，retry 就地重试成功', async () => {
    let fail = false
    const fetchPage = vi.fn((p) => {
      if (p.offset > 0 && fail) return Promise.reject(new Error('network down'))
      return Promise.resolve(p.offset === 0 ? page([1, 2], true) : page([3, 4], false))
    })
    const api = mountPagedList(fetchPage, { pageSize: 2 })
    await api.load()

    fail = true
    await api.loadMore()
    expect(api.error.value).toBe('network down')
    expect(api.list.value.map((r) => r.id)).toEqual([1, 2]) // 已加载数据保留

    fail = false
    await api.retry() // 复用 loadMore 的参数（offset=2）
    expect(api.error.value).toBeNull()
    expect(api.list.value.map((r) => r.id)).toEqual([1, 2, 3, 4])
  })

  it('removeById 本地移除卡片', async () => {
    const fetchPage = vi.fn(() => Promise.resolve(page([1, 2, 3], false)))
    const api = mountPagedList(fetchPage)
    await api.load()
    api.removeById(2)
    expect(api.list.value.map((r) => r.id)).toEqual([1, 3])
  })
})
