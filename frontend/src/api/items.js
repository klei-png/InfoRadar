import { request } from './http'

/**
 * 已评分条目列表。
 * 旧后端支持 category/min_score/limit/offset，但返回纯数组（无 total/has_more）——
 * 此处适配为 §3.8 分页契约：满页（结果数 === limit）推断还有下一页。
 * 后端就绪返回 {data,total,has_more} 后可移除包装。
 */
export async function items({ min_score = 6, limit = 30, offset = 0, category = '', signal } = {}) {
  const params = new URLSearchParams()
  params.set('min_score', min_score)
  params.set('limit', limit)
  params.set('offset', offset)
  if (category) {
    params.set('category', category)
  }
  const rows = await request(`/items?${params}`, { signal })
  return {
    data: Array.isArray(rows) ? rows : [],
    has_more: Array.isArray(rows) && rows.length === limit,
  }
}

/**
 * 逻辑删除条目（§3.7 契约先行，204 → null）。
 * 旧后端无此端点（items 无软删除字段），暂无前端入口。
 */
export function deleteItem(id) {
  return request(`/items/${id}`, { method: 'DELETE' })
}
