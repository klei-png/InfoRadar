import { request } from './http'

/** 已评分条目列表（S4 接入 category/offset 分页筛选） */
export function items(minScore = 6, limit = 30) {
  return request(`/items?min_score=${minScore}&limit=${limit}`)
}

/** 逻辑删除条目（§3.7 契约，后端实现后生效；204 → null） */
export function deleteItem(id) {
  return request(`/items/${id}`, { method: 'DELETE' })
}
