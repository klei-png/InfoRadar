import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import CategoryBadge from '../CategoryBadge.vue'
import DeleteButton from '../DeleteButton.vue'
import EmptyState from '../EmptyState.vue'
import ErrorBanner from '../ErrorBanner.vue'
import LoadingState from '../LoadingState.vue'
import ScoreBadge from '../ScoreBadge.vue'

describe('LoadingState', () => {
  it('默认渲染 3 个骨架块', () => {
    const wrapper = mount(LoadingState)
    expect(wrapper.findAll('.skeleton')).toHaveLength(3)
  })

  it('rows 控制数量，末行渲染短块', () => {
    const wrapper = mount(LoadingState, { props: { rows: 5 } })
    const blocks = wrapper.findAll('.skeleton')
    expect(blocks).toHaveLength(5)
    expect(wrapper.findAll('.skeleton.short')).toHaveLength(1)
  })
})

describe('EmptyState', () => {
  it('默认文本', () => {
    const wrapper = mount(EmptyState)
    expect(wrapper.text()).toBe('暂无数据')
  })

  it('自定义文本', () => {
    const wrapper = mount(EmptyState, { props: { text: '还没有简报' } })
    expect(wrapper.text()).toBe('还没有简报')
  })
})

describe('ErrorBanner', () => {
  it('显示错误信息', () => {
    const wrapper = mount(ErrorBanner, { props: { message: '请求超时' } })
    expect(wrapper.text()).toContain('请求超时')
  })

  it('点击重试按钮 emit retry', async () => {
    const wrapper = mount(ErrorBanner, { props: { message: '网络错误' } })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('retryable=false 时不渲染重试按钮', () => {
    const wrapper = mount(ErrorBanner, { props: { message: '网络错误', retryable: false } })
    expect(wrapper.find('button').exists()).toBe(false)
  })
})

describe('CategoryBadge', () => {
  it('显示分类名', () => {
    const wrapper = mount(CategoryBadge, { props: { category: 'ai' } })
    expect(wrapper.text()).toBe('ai')
    expect(wrapper.classes()).toContain('badge')
  })
})

describe('ScoreBadge', () => {
  it('高分（≥7）渲染 is-high 类', () => {
    const wrapper = mount(ScoreBadge, { props: { score: 8 } })
    expect(wrapper.classes()).toContain('is-high')
    expect(wrapper.text()).toBe('评分 8')
  })

  it('低分（<7）不渲染 is-high 类', () => {
    const wrapper = mount(ScoreBadge, { props: { score: 5 } })
    expect(wrapper.classes()).not.toContain('is-high')
  })
})

describe('DeleteButton', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('初始为删除按钮，点击进入确认态且不 emit', async () => {
    const wrapper = mount(DeleteButton)
    expect(wrapper.text()).toContain('删除')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.text()).toContain('确认删除')
    expect(wrapper.text()).toContain('取消')
  })

  it('确认态点击"确认删除" emit confirm 并复原', async () => {
    const wrapper = mount(DeleteButton)
    await wrapper.find('button').trigger('click')
    await wrapper.find('.confirm-del').trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('确认删除') // 已复原回删除态
  })

  it('取消后复原回删除态', async () => {
    const wrapper = mount(DeleteButton)
    await wrapper.find('button').trigger('click')
    const buttons = wrapper.findAll('button')
    await buttons[1].trigger('click') // 取消
    expect(wrapper.emitted('confirm')).toBeUndefined()
    expect(wrapper.text()).not.toContain('确认删除')
  })

  it('确认态 3s 无操作自动复原', async () => {
    const wrapper = mount(DeleteButton)
    await wrapper.find('button').trigger('click')
    expect(wrapper.text()).toContain('确认删除')

    vi.advanceTimersByTime(2999)
    await flushPromises()
    expect(wrapper.text()).toContain('确认删除') // 3s 内不复原

    vi.advanceTimersByTime(1)
    await flushPromises()
    expect(wrapper.text()).not.toContain('确认删除') // 3s 到自动复原
  })

  it('确认后计时器清理，不会再自动复原干扰', async () => {
    const wrapper = mount(DeleteButton)
    await wrapper.find('button').trigger('click')
    await wrapper.find('.confirm-del').trigger('click')
    vi.advanceTimersByTime(10000)
    await flushPromises()
    // 已复原为删除态，遗留计时器不应产生副作用
    expect(wrapper.findAll('button')).toHaveLength(1)
  })
})
