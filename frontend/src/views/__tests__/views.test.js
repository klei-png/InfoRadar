 
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'

const itemsMock = vi.fn()
vi.mock('../../api/items', () => ({
  items: (...args) => itemsMock(...args),
}))

import FeedView from '../FeedView.vue'
import NotFoundView from '../NotFoundView.vue'
import { createRouter, createWebHashHistory } from 'vue-router'

const sampleItem = {
  id: 1,
  category: 'ai',
  model_score: 8,
  published_at: '2026-11-20T10:00:00',
  url: 'https://example.com',
  title: '新闻标题',
  snippet: '摘要内容',
}

describe('FeedView 接线', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    itemsMock.mockReset()
  })

  it('加载中渲染骨架屏', async () => {
    itemsMock.mockReturnValue(new Promise(() => {})) // 永不 resolve
    const wrapper = mount(FeedView)
    await nextTick() // onMounted 触发加载后，DOM 下一个 tick 才渲染骨架屏
    expect(wrapper.find('.skeleton').exists()).toBe(true)
  })

  it('加载成功：渲染卡片、徽标与格式化时间', async () => {
    itemsMock.mockResolvedValue({ data: [sampleItem], has_more: false, total: 1 })
    const wrapper = mount(FeedView)
    await flushPromises()

    expect(itemsMock).toHaveBeenCalledWith(6, 30) // 默认 min_score/limit
    const cards = wrapper.findAll('.card')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('新闻标题')
    expect(wrapper.find('.badge.is-high').exists()).toBe(true) // 评分 8 高亮
    expect(wrapper.text()).toContain('2026-11-20 10:00')
  })

  it('加载失败：ErrorBanner 展示信息，重试成功后渲染列表', async () => {
    itemsMock.mockRejectedValue(new Error('boom'))
    const wrapper = mount(FeedView)
    await flushPromises()

    expect(wrapper.text()).toContain('boom')
    expect(wrapper.find('button').text()).toBe('重试')

    itemsMock.mockResolvedValue({ data: [sampleItem], has_more: false, total: 1 })
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.card')).toHaveLength(1)
  })

  it('加载成功但无数据：空态', async () => {
    itemsMock.mockResolvedValue({ data: [], has_more: false, total: 0 })
    const wrapper = mount(FeedView)
    await flushPromises()
    expect(wrapper.text()).toBe('暂无数据')
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
