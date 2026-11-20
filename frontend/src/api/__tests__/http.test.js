import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ApiError, DEFAULT_TIMEOUT_MS, request, setUnauthorizedHandler } from '../http'
import { useAuthStore } from '../../stores/auth'

function jsonResponse(status, body, contentType = 'application/json') {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'content-type': contentType }),
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  }
}

describe('request 基础行为', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    setUnauthorizedHandler(null)
  })

  it('默认超时为 15s', () => {
    expect(DEFAULT_TIMEOUT_MS).toBe(15000)
  })

  it('有 token 时注入 Authorization 头', async () => {
    const auth = useAuthStore()
    auth.setToken('tok-1')
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ok: true })))
    vi.stubGlobal('fetch', fetchMock)

    await request('/items')
    expect(fetchMock).toHaveBeenCalledOnce()
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.Authorization).toBe('Bearer tok-1')
  })

  it('无 token 时不注入 Authorization 头', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, {})))
    vi.stubGlobal('fetch', fetchMock)

    await request('/health')
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers.Authorization).toBeUndefined()
  })

  it('body 自动 JSON 序列化并设置 Content-Type', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, {})))
    vi.stubGlobal('fetch', fetchMock)

    await request('/login', { method: 'POST', body: { username: 'a', password: 'b' } })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ username: 'a', password: 'b' }))
  })

  it('204 返回 null', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 204,
          headers: new Headers(),
        })
      )
    )
    await expect(request('/items/1', { method: 'DELETE' })).resolves.toBeNull()
  })

  it('非 JSON 响应返回文本', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'text/plain' }),
          text: () => Promise.resolve('hello'),
        })
      )
    )
    await expect(request('/health')).resolves.toBe('hello')
  })
})

describe('request 错误处理', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    setUnauthorizedHandler(null)
  })

  it('500 + 统一错误结构 → ApiError 携带后端 message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(jsonResponse(500, { error: { code: 'X', message: '服务器开小差' } }))
      )
    )
    const err = await request('/items').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(500)
    expect(err.message).toBe('服务器开小差')
    expect(err.url).toBe('/items')
  })

  it('500 + FastAPI detail 结构 → 兼容解包', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(422, { detail: '参数不合法' })))
    )
    const err = await request('/items').catch((e) => e)
    expect(err.status).toBe(422)
    expect(err.message).toBe('参数不合法')
  })

  it('超时 → ApiError(0) 超时提示', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, init) =>
          new Promise((_resolve, reject) => {
            init.signal.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError'))
            )
          })
      )
    )
    const err = await request('/items', { timeoutMs: 10 }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.message).toContain('超时')
  })

  it('外部 signal 取消 → 原样抛出 AbortError（非 ApiError）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url, init) =>
          new Promise((_resolve, reject) => {
            init.signal.addEventListener('abort', () =>
              reject(new DOMException('aborted', 'AbortError'))
            )
          })
      )
    )
    const controller = new AbortController()
    setTimeout(() => controller.abort(), 5)
    await expect(request('/items', { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
  })

  it('外部 signal 已 aborted → 立即取消不发请求', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, {})))
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()
    controller.abort()
    await expect(request('/items', { signal: controller.signal })).rejects.toMatchObject({
      name: 'AbortError',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('401 分流', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    setUnauthorizedHandler(null)
  })

  it('非登录接口 401 → 清 token 并触发踢出回调', async () => {
    const auth = useAuthStore()
    auth.setToken('expired')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(401, {})))
    )

    const err = await request('/digests').catch((e) => e)
    expect(err.status).toBe(401)
    expect(err.message).toBe('登录已过期，请重新登录')
    expect(auth.token).toBe('')
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })

  it('/login 接口 401 → 不清 token、不触发踢出回调，message 面向登录页', async () => {
    const auth = useAuthStore()
    auth.setToken('stale-but-keep')
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(401, { detail: 'Login failed' })))
    )

    const err = await request('/login', { method: 'POST', body: {} }).catch((e) => e)
    expect(err.status).toBe(401)
    expect(err.message).toBe('账号或密码错误')
    expect(auth.token).toBe('stale-but-keep')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('403 → 抛 ApiError 但不清 token', async () => {
    const auth = useAuthStore()
    auth.setToken('valid')
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse(403, {})))
    )

    const err = await request('/admin').catch((e) => e)
    expect(err.status).toBe(403)
    expect(auth.token).toBe('valid')
  })
})
