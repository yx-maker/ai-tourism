/**
 * 全局消息提示（toast）
 */
import { reactive } from 'vue'

let seq = 0

export const toastState = reactive({ items: [] })

const DURATION = { success: 2600, info: 3000, warn: 4200, error: 5200 }

function push(type, message, title) {
  const id = ++seq
  toastState.items.push({ id, type, message, title })
  setTimeout(() => dismiss(id), DURATION[type] || 3000)
  return id
}

export function dismiss(id) {
  const i = toastState.items.findIndex((t) => t.id === id)
  if (i !== -1) toastState.items.splice(i, 1)
}

export const toast = {
  success: (m, t) => push('success', m, t),
  error: (m, t) => push('error', m, t),
  info: (m, t) => push('info', m, t),
  warn: (m, t) => push('warn', m, t),
  dismiss
}

/** 从异常对象取可读文案 */
export function errText(e, fallback = '操作失败') {
  if (!e) return fallback
  if (typeof e === 'string') return e
  return e.message || fallback
}
