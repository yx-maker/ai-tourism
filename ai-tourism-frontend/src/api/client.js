/**
 * 统一请求层
 * - 注入 Authorization: Bearer <token>
 * - 解包后端统一响应 { code, msg, data }
 * - token 过期（code 1101 / HTTP 401）自动刷新并重放一次
 * - 同时提供原生流式入口，供 SSE 对话使用
 */

export const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

const TOKEN_KEY = 'token'
const REFRESH_KEY = 'refresh_token'
const USER_KEY = 'user'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY) || '',
  set: (t) => t && localStorage.setItem(TOKEN_KEY, t),
  getRefresh: () => localStorage.getItem(REFRESH_KEY) || '',
  setRefresh: (t) => t && localStorage.setItem(REFRESH_KEY, t),
  getUser: () => {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
    } catch {
      return null
    }
  },
  setUser: (u) => u && localStorage.setItem(USER_KEY, JSON.stringify(u)),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(USER_KEY)
  }
}

/** 业务异常，携带后端错误码 */
export class ApiError extends Error {
  constructor(message, code) {
    super(message)
    this.name = 'ApiError'
    this.code = code
  }
}

/** 会话失效时由上层注册的跳转回调 */
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function authHeader(extra = {}) {
  const t = tokenStore.get()
  return t ? { ...extra, Authorization: `Bearer ${t}` } : { ...extra }
}

/* ------------------------------------------------------------------
   token 刷新（并发去重：同时多个 401 只刷新一次）
   ------------------------------------------------------------------ */
let refreshing = null

async function refreshToken() {
  if (refreshing) return refreshing
  const rt = tokenStore.getRefresh()
  if (!rt) return Promise.reject(new ApiError('登录已过期', 1101))

  refreshing = (async () => {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt })
    })
    const body = await res.json().catch(() => null)
    if (!res.ok || !body || body.code !== 0) {
      throw new ApiError(body?.msg || '刷新登录状态失败', 1101)
    }
    const d = body.data || {}
    tokenStore.set(d.token)
    tokenStore.setRefresh(d.refresh_token)
    return d
  })()

  try {
    return await refreshing
  } finally {
    refreshing = null
  }
}

function handleExpired() {
  tokenStore.clear()
  if (onUnauthorized) onUnauthorized()
  throw new ApiError('登录已过期，请重新登录', 1101)
}

/* ------------------------------------------------------------------
   主请求方法
   ------------------------------------------------------------------ */
export async function request(path, { method = 'GET', body, params, retry = true } = {}) {
  let url = `${BASE}${path}`
  if (params && Object.keys(params).length) {
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') qs.append(k, v)
    })
    const s = qs.toString()
    if (s) url += `?${s}`
  }

  const init = {
    method,
    headers: authHeader(body !== undefined ? { 'Content-Type': 'application/json' } : {})
  }
  if (body !== undefined) init.body = JSON.stringify(body)

  let res
  try {
    res = await fetch(url, init)
  } catch (e) {
    throw new ApiError('网络异常，无法连接服务器', -1)
  }

  // 401：尝试刷新后重放一次
  if (res.status === 401 && retry) {
    try {
      await refreshToken()
    } catch {
      handleExpired()
    }
    return request(path, { method, body, params, retry: false })
  }

  const text = await res.text()
  let payload
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    throw new ApiError(`响应解析失败（HTTP ${res.status}）`, res.status)
  }

  if (!payload || typeof payload !== 'object') {
    throw new ApiError(`响应格式异常（HTTP ${res.status}）`, res.status)
  }

  // 业务层 token 失效
  if (payload.code === 1101 && retry) {
    try {
      await refreshToken()
    } catch {
      handleExpired()
    }
    return request(path, { method, body, params, retry: false })
  }

  if (payload.code !== 0) {
    if (payload.code === 1101) handleExpired()
    throw new ApiError(payload.msg || '请求失败', payload.code)
  }

  return payload.data
}

export const http = {
  get: (p, params) => request(p, { params }),
  post: (p, body) => request(p, { method: 'POST', body }),
  put: (p, body) => request(p, { method: 'PUT', body }),
  del: (p) => request(p, { method: 'DELETE' })
}

/**
 * 原生流式请求（SSE 用），返回 Response 供调用方逐块读取。
 * 不走统一解包，因为响应体是 text/event-stream。
 */
export async function stream(path, body, { retry = true } = {}) {
  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: authHeader({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
      body: JSON.stringify(body)
    })
  } catch {
    throw new ApiError('网络异常，无法连接服务器', -1)
  }

  if (res.status === 401 && retry) {
    try {
      await refreshToken()
    } catch {
      handleExpired()
    }
    return stream(path, body, { retry: false })
  }

  if (!res.ok) {
    throw new ApiError(`对话请求失败（HTTP ${res.status}）`, res.status)
  }

  // 后端在参数校验失败时会返回 application/json 而非事件流
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    const payload = await res.json().catch(() => null)
    if (payload && payload.code === 1101 && retry) {
      try {
        await refreshToken()
      } catch {
        handleExpired()
      }
      return stream(path, body, { retry: false })
    }
    throw new ApiError(payload?.msg || '对话请求被拒绝', payload?.code)
  }

  return res
}
