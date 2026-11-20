import { request } from './http'

/**
 * 近 N 天简报列表。
 * 旧后端返回纯数组：{ date, category, item_count, cost_tokens, prompt_version, generated_at, preview }，
 * 无 id 主键（§3.8 id 契约待 agent-core 后端就绪后切换）。
 */
export function digestList(days = 7) {
  return request(`/digests?days=${days}`)
}

/** 取某分类最新一篇简报全文（旧后端按 category 寻址，返回含 content_md） */
export function digestDetail(category) {
  return request(`/digests/${category}`)
}

/**
 * 手动触发一次批次生成（§3.6 契约先行，180s 超时分级）。
 * 旧后端无此端点（简报由 APScheduler 每天 08:40 定时生成），暂无前端入口。
 */
export function generateDigest() {
  return request('/digests/generate', { method: 'POST', timeoutMs: 180000 })
}
