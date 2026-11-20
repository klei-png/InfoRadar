import { useAuthStore } from '../stores/auth'

/**
 * 请求层核心（web-frontend-plan §3.1）：
 * - URL 拼装：VITE_API_BASE + path（生产同源 / 开发走 vite 代理）
 * - Token 注入：只经 auth store 读取
 * - 取消合并：内部 AbortController 按 timeoutMs 计时 abort，外部 signal 桥接到同一 controller
 * - 超时分级：默认 15s，长耗时端点（如 /digests/generate）自行传 timeoutMs=180000
 * - 401 分流：/login 的 401 原样抛出交登录页展示；其余 401 清登录态并通知跳转
 * - 403：权限不足，不清 token
 * - 非 2xx → ApiError{ status, message, url }；204/非 JSON 安全解包
 * 请求层不承担业务提示，展示统一交给页面或全局通知层。
 */

export const DEFAULT_TIMEOUT_MS = 15000

export class ApiError extends Error {
  constructor(status, message, url) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

// 401 踢出的跳转行为由外部注册（main.js 接 auth store + router），
// 请求层不直接依赖路由，避免循环依赖。
let unauthorizedHandler = null
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn
}

function buildURL(path) {
  const base = import.meta.env.VITE_API_BASE || ''
  return base + path
}

export async function request(
  path,
  { method = 'GET', body, signal, timeoutMs = DEFAULT_TIMEOUT_MS } = {}
) {
  // 取消合并：外部已 aborted 时立即取消
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)
  const onExternalAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) {
      controller.abort()
    } else {
      signal.addEventListener('abort', onExternalAbort, { once: true })
    }
  }

  // 外部已取消：立即短路，不发请求
  if (controller.signal.aborted) {
    clearTimeout(timer)
    throw new DOMException('The operation was aborted.', 'AbortError')
  }

  const auth = useAuthStore()
  const headers = { Accept: 'application/json' }
  if (auth.token) {
    headers.Authorization = `Bearer ${auth.token}`
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  let res
  try {
    res = await fetch(buildURL(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (err) {
    if (timedOut) {
      throw new ApiError(0, `请求超时（${Math.round(timeoutMs / 1000)}s），请稍后重试`, path)
    }
    // 外部取消（页面卸载等）：原样抛出 AbortError，由调用方决定是否吞掉
    throw err
  } finally {
    clearTimeout(timer)
    if (signal) {
      signal.removeEventListener('abort', onExternalAbort)
    }
  }

  // 401 分流
  if (res.status === 401) {
    const isLoginRequest = path.startsWith('/login')
    if (isLoginRequest) {
      // 密码错误：不动登录态，交给登录页展示
      throw new ApiError(401, '账号或密码错误', path)
    }
    // 登录态下 token 失效：清登录态 + 通知跳转
    auth.clearToken()
    if (unauthorizedHandler) {
      unauthorizedHandler()
    }
    throw new ApiError(401, '登录已过期，请重新登录', path)
  }

  if (res.status === 403) {
    throw new ApiError(403, '没有权限执行该操作', path)
  }

  // 204 无 body
  if (res.status === 204) {
    return null
  }

  const contentType = res.headers.get('content-type') || ''

  if (!res.ok) {
    let message = `请求失败（${res.status}）`
    if (contentType.includes('application/json')) {
      try {
        const data = await res.json()
        // 统一错误结构 { error: { code, message } }（§3.8）；兼容 FastAPI 默认 { detail }
        message = data?.error?.message || data?.detail || message
      } catch {
        // JSON 解析失败保持默认 message
      }
    }
    throw new ApiError(res.status, message, path)
  }

  // 非 JSON 响应安全解包
  if (!contentType.includes('application/json')) {
    const text = await res.text()
    return text || null
  }
  return res.json()
}
