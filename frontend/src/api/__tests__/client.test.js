import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, clearToken, getToken, setToken } from '../client'

describe('token 存取', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('setToken 后 getToken 返回该值', () => {
    setToken('abc123')
    expect(getToken()).toBe('abc123')
  })

  it('clearToken 后 getToken 为空串', () => {
    setToken('abc123')
    clearToken()
    expect(getToken()).toBe('')
  })
})

describe('request 错误处理（经 api 公共出口）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('非 2xx 抛出含状态码的错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 500 }))
    )
    await expect(api.items()).rejects.toThrow(/500/)
  })

  it('401 清除本地 token 并跳转登录页', async () => {
    setToken('expired-token')
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve({ ok: false, status: 401 }))
    )
    await expect(api.digests()).rejects.toThrow('unauthorized')
    expect(getToken()).toBe('')
    expect(location.hash).toBe('#/login')
  })
})
