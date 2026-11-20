import { request } from './http'

/** 近 N 天简报列表（§3.6：主键为 digest id） */
export function digestList(days = 7) {
  return request(`/digests?days=${days}`)
}

/** 按 id 取简报全文（旧后端按 category，S4 视图切换时对齐契约） */
export function digestDetail(id) {
  return request(`/digests/${id}`)
}

/** 手动触发一次批次生成（§3.6）：生成需 60~120s，超时单独分级为 180s */
export function generateDigest() {
  return request('/digests/generate', { method: 'POST', timeoutMs: 180000 })
}
