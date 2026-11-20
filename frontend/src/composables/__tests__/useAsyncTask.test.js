/* eslint-disable vue/one-component-per-file -- 测试宿主组件属惯用法 */
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { useAsyncTask } from '../useAsyncTask'

const abortErr = () => Object.assign(new Error('aborted'), { name: 'AbortError' })

function mountTask(taskFn) {
  let api
  const Host = defineComponent({
    setup() {
      api = useAsyncTask(taskFn)
      return () => h('div')
    },
  })
  mount(Host)
  return api
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useAsyncTask', () => {
  it('run 成功：data 更新、loading 归位', async () => {
    const api = mountTask(async (_signal, n) => n * 2)
    const result = await api.run(21)
    expect(result).toBe(42)
    expect(api.data.value).toBe(42)
    expect(api.loading.value).toBe(false)
    expect(api.error.value).toBeNull()
  })

  it('竞态：旧慢请求返回不覆盖新快请求结果', async () => {
    const gates = { a: deferred(), b: deferred() }
    const api = mountTask((_signal, key) => gates[key].promise)
    const pA = api.run('a')
    const pB = api.run('b') // 触发 B 时取消 A
    gates.b.resolve('B')
    await flushPromises()
    gates.a.resolve('A') // 旧请求此时才返回
    await Promise.all([pA, pB])
    await flushPromises()
    expect(api.data.value).toBe('B')
    expect(api.error.value).toBeNull()
  })

  it('失败：error 记录 message，data 不写入', async () => {
    const api = mountTask(async () => {
      throw new Error('boom')
    })
    await api.run()
    expect(api.error.value).toBe('boom')
    expect(api.data.value).toBeNull()
  })

  it('retry 复用最近一次 run 的参数', async () => {
    const calls = []
    const api = mountTask(async (_signal, n) => {
      calls.push(n)
      if (calls.length === 1) throw new Error('fail first')
      return n + 1
    })
    await api.run(5)
    expect(api.error.value).toBe('fail first')
    await api.retry()
    expect(calls).toEqual([5, 5])
    expect(api.data.value).toBe(6)
    expect(api.error.value).toBeNull()
  })

  it('取消（AbortError）不展示为错误', async () => {
    const api = mountTask(async () => {
      throw abortErr()
    })
    await api.run()
    expect(api.error.value).toBeNull()
    expect(api.loading.value).toBe(false)
  })

  it('cancel() 立即归位，迟到的结果不写入', async () => {
    const gate = deferred()
    const api = mountTask(() => gate.promise)
    const p = api.run()
    expect(api.loading.value).toBe(true)
    api.cancel()
    expect(api.loading.value).toBe(false)
    gate.resolve('late')
    await p
    expect(api.data.value).toBeNull()
    expect(api.error.value).toBeNull()
  })

  it('组件卸载后取消在途请求，结果不写入', async () => {
    const gate = deferred()
    let api
    const Host = defineComponent({
      setup() {
        api = useAsyncTask(() => gate.promise)
        return () => h('div')
      },
    })
    const wrapper = mount(Host)
    const p = api.run()
    wrapper.unmount()
    gate.resolve('late')
    await p
    await flushPromises()
    expect(api.data.value).toBeNull()
    expect(api.error.value).toBeNull()
  })
})
