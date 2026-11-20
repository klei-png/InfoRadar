/** 时间显示：ISO 字符串 → 'YYYY-MM-DD HH:mm'，空值降级 */
export function formatTime(t) {
  return t ? String(t).slice(0, 16).replace('T', ' ') : '时间未知'
}
