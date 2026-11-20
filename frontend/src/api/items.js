import { request } from './http'

/**
 * 已评分条目列表（§3.8 契约：{ data, total, has_more }）。
 * 参数名与后端 query 保持一致（min_score），避免映射出错。
 */
export function items({ min_score = 6, limit = 30, offset = 0, category = '', signal } = {}) {
  const params = new URLSearchParams()
  params.set('min_score', min_score)
  params.set('limit', limit)
  params.set('offset', offset)
  if (category) {
    params.set('category', category)
  }
  return request(`/items?${params}`, { signal })
}

/** 逻辑删除条目（§3.7：后端置 deleted=1；204 → null） */
export function deleteItem(id) {
  return request(`/items/${id}`, { method: 'DELETE' })
}
