import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import { flushPromises, mount } from '@vue/test-utils'

const itemsMock = vi.fn()
const deleteItemMock = vi.fn()
vi.mock('../../api/items', () => ({
  items: (...args) => itemsMock(...args),
  deleteItem: (...args) => deleteItemMock(...args),
}))

import FeedView from '../FeedView.vue'
import NotFoundView from '../NotFoundView.vue'

const makeItem = (id) => ({
  id,
  category: 'ai',
  model_score: 8,
  published_at: '2026-11-20T10:00:00',
  url: 'https://example.com',
  title: `新闻标题${id}`,
  snippet: '摘要内容',
})

describe('FeedView 接线', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    itemsMock.mockReset()
    deleteItemMock.mockReset()
  })

  it('加载中渲染骨架屏', async () => {
    itemsMock.mockReturnValue(new Promise(() => {})) // 永不 resolve
    const wrapper = mount(FeedView)
    await nextTick() // onMounted 触发加载后，DOM 下一个 tick 才渲染骨架屏
    expect(wrapper.find('.skeleton').exists()).toBe(true)
  })

  it('加载成功：渲染卡片、徽标与格式化时间', async () => {
    itemsMock.mockResolvedValue({ data: [makeItem(1)], has_more: false, total: 1 })
    const wrapper = mount(FeedView)
    await flushPromises()

    expect(itemsMock).toHaveBeenCalledWith(
      expect.objectContaining({ min_score: 6, category: '', offset: 0, limit: 30 })
    )
    const cards = wrapper.findAll('.card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('新闻标题1')
    expect(wrapper.find('.badge.is-high').exists()).toBe(true) // 评分 8 高亮
    expect(wrapper.text()).toContain('2026-11-20 10:00')
  })

  it('加载失败：ErrorBanner 展示信息，重试成功后渲染列表', async () => {
    itemsMock.mockRejectedValue(new Error('boom'))
    const wrapper = mount(FeedView)
    await flushPromises()

    expect(wrapper.text()).toContain('boom')

    itemsMock.mockResolvedValue({ data: [makeItem(1)], has_more: false, total: 1 })
    await wrapper.find('button').trigger('click') // ErrorBanner 重试按钮
    await flushPromises()
    expect(wrapper.findAll('.card')).toHaveLength(1)
  })

  it('分类 Tab 切换：重置分页并带 category 请求', async () => {
    itemsMock.mockResolvedValue({ data: [makeItem(1)], has_more: false, total: 1 })
    const wrapper = mount(FeedView)
    await flushPromises()
    itemsMock.mockClear()

    const aiTab = wrapper.findAll('button').find((b) => b.text() === 'AI')
    await aiTab.trigger('click')
    await flushPromises()
    expect(itemsMock).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'ai', offset: 0 })
    )
  })

  it('评分筛选切换：带 min_score 重新请求', async () => {
    itemsMock.mockResolvedValue({ data: [makeItem(1)], has_more: false, total: 1 })
    const wrapper = mount(FeedView)
    await flushPromises()
    itemsMock.mockClear()

    await wrapper.find('select.score-select').setValue(7)
    await flushPromises()
    expect(itemsMock).toHaveBeenCalledWith(
      expect.objectContaining({ min_score: 7, offset: 0 })
    )
  })

  it('加载更多：追加数据且 offset 游标 = 已加载条数', async () => {
    // 第一页返回满页 30 条（真实场景），游标 offset=30
    itemsMock
      .mockResolvedValueOnce({
        data: Array.from({ length: 30 }, (_, i) => makeItem(i + 1)),
        has_more: true,
        total: 31,
      })
      .mockResolvedValueOnce({ data: [makeItem(31)], has_more: false, total: 31 })
    const wrapper = mount(FeedView)
    await flushPromises()

    const loadBtn = wrapper.findAll('button').find((b) => b.text() === '加载更多')
    expect(loadBtn).toBeDefined()
    await loadBtn.trigger('click')
    await flushPromises()

    expect(itemsMock).toHaveBeenNthCalledWith(2, expect.objectContaining({ offset: 30 }))
    expect(wrapper.findAll('.card')).toHaveLength(31)
    expect(wrapper.text()).not.toContain('加载更多') // has_more=false 按钮消失
  })

  it('逻辑删除成功：卡片从列表移除', async () => {
    itemsMock.mockResolvedValue({ data: [makeItem(1), makeItem(2)], has_more: false, total: 2 })
    deleteItemMock.mockResolvedValue(null)
    const wrapper = mount(FeedView)
    await flushPromises()
    expect(wrapper.findAll('.card')).toHaveLength(2)

    await wrapper.findAll('button').find((b) => b.text() === '删除').trigger('click')
    await wrapper.find('.confirm-del').trigger('click') // 两段式确认
    await flushPromises()

    expect(deleteItemMock).toHaveBeenCalledWith(1)
    expect(wrapper.findAll('.card')).toHaveLength(1)
  })

  it('逻辑删除失败：卡片保留并提示错误', async () => {
    itemsMock.mockResolvedValue({ data: [makeItem(1)], has_more: false, total: 1 })
    deleteItemMock.mockRejectedValue(new Error('删除失败'))
    const wrapper = mount(FeedView)
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text() === '删除').trigger('click')
    await wrapper.find('.confirm-del').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.card')).toHaveLength(1) // 卡片保留
    expect(wrapper.text()).toContain('删除失败')
  })
})

describe('NotFoundView', () => {
  it('渲染 404 文案与返回按钮', () => {
    const router = createRouter({
      history: createWebHashHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    const wrapper = mount(NotFoundView, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('404')
    expect(wrapper.text()).toContain('返回首页')
  })
})
