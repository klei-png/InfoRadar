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

const digestListMock = vi.fn()
const digestDetailMock = vi.fn()
const generateDigestMock = vi.fn()
vi.mock('../../api/digests', () => ({
  digestList: (...args) => digestListMock(...args),
  digestDetail: (...args) => digestDetailMock(...args),
  generateDigest: (...args) => generateDigestMock(...args),
}))

import DigestsView from '../DigestsView.vue'
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

  it('加载更多满页时按钮消失：has_more 由"结果数 === limit"推断（旧后端适配）', async () => {
    itemsMock
      .mockResolvedValueOnce({
        data: Array.from({ length: 30 }, (_, i) => makeItem(i + 1)),
        has_more: true,
      })
      .mockResolvedValueOnce({ data: [makeItem(31)], has_more: false })
    const wrapper = mount(FeedView)
    await flushPromises()

    const loadBtn = wrapper.findAll('button').find((b) => b.text() === '加载更多')
    expect(loadBtn).toBeDefined()
    await loadBtn.trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.card')).toHaveLength(31)
    expect(wrapper.text()).not.toContain('加载更多') // 不满页 → has_more=false
  })
})

describe('DigestsView 接线', () => {
  // 旧后端返回纯数组，无 id 主键（category+date 定位）
  const sampleDigest = {
    category: 'ai',
    date: '2026-11-20',
    item_count: 5,
    cost_tokens: 1200,
    preview: '摘要预览',
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    digestListMock.mockReset()
    digestDetailMock.mockReset()
    generateDigestMock.mockReset()
  })

  it('加载成功：渲染批次卡片（元信息 + 预览）', async () => {
    digestListMock.mockResolvedValue([sampleDigest])
    const wrapper = mount(DigestsView)
    await flushPromises()

    expect(digestListMock).toHaveBeenCalledWith(7)
    const cards = wrapper.findAll('.card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('ai')
    expect(cards[0].text()).toContain('2026-11-20 · 5 条信息 · 1200 tokens')
    expect(cards[0].text()).toContain('摘要预览')
  })

  it('查看全文：按 category 请求并渲染 Markdown 内容', async () => {
    digestListMock.mockResolvedValue([{ ...sampleDigest }])
    digestDetailMock.mockResolvedValue({ content_md: '# 标题\n- 要点一' })
    const wrapper = mount(DigestsView)
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text() === '查看全文').trigger('click')
    await flushPromises()
    expect(digestDetailMock).toHaveBeenCalledWith('ai')
    expect(wrapper.find('.md-content').exists()).toBe(true)
  })

  it('加载失败：ErrorBanner 展示并可重试', async () => {
    digestListMock.mockRejectedValue(new Error('网络错误'))
    const wrapper = mount(DigestsView)
    await flushPromises()

    expect(wrapper.text()).toContain('网络错误')
    digestListMock.mockResolvedValue([sampleDigest])
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.card')).toHaveLength(1)
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
