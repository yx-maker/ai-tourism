/**
 * 后端接口清单（与 SpringBoot 8290 契约保持一致）
 * 响应字段为后端 Jackson 的 snake_case 命名，此处不做转换，原样透出。
 */
import { http, stream } from './client.js'

/* ==================== 认证 /auth ==================== */
export const authApi = {
  login: (phone, password) => http.post('/auth/login', { phone, password }),
  register: (payload) => http.post('/auth/register', payload),
  me: () => http.get('/auth/me'),
  logout: () => http.post('/auth/logout')
}

/* ==================== 对话 /ai_assistant ==================== */
export const chatApi = {
  sessionList: ({ page = 1, pageSize = 20, userId }) =>
    http.post('/ai_assistant/session_list', { page, page_size: pageSize, user_id: userId }),

  history: (sessionId) => http.post('/ai_assistant/get_history', { session_id: sessionId }),

  /** opType: 2=删除 3=改标题 */
  modifySession: ({ sessionId, opType, title }) =>
    http.post('/ai_assistant/session_modify', { session_id: sessionId, op_type: opType, title }),

  /** 发起流式对话，返回原生 Response */
  chatStream: ({ sessionId, message, userId }) =>
    stream('/ai_assistant/chat-stream', { session_id: sessionId, messages: message, user_id: userId })
}

/* ==================== 预算 /budget ==================== */
export const budgetApi = {
  analyze: (sessionId, itineraryText) =>
    http.post('/budget/analyze', { session_id: sessionId, itinerary_text: itineraryText }),
  bySession: (sessionId) => http.get(`/budget/session/${sessionId}`),
  recent: (limit = 10) => http.get('/budget/recent', { limit })
}

/* ==================== 旅行计划 /travel-plan ==================== */
export const travelPlanApi = {
  /** 从会话保存为旅行计划 */
  saveFromSession: (sessionId, title) =>
    http.post('/travel-plan/save-from-session', { session_id: sessionId, title }),
  list: ({ page = 1, pageSize = 10 } = {}) =>
    http.get('/travel-plan/list', { page, pageSize }),
  detail: (planId) => http.get(`/travel-plan/detail/${planId}`),
  /** 更新计划（乐观锁 version 必填；content 变化时服务端自动重算预算） */
  update: (payload) => http.post('/travel-plan/update', payload),
  remove: (planId) => http.post('/travel-plan/delete', { plan_id: planId })
}

/* ==================== 景点 /poi ==================== */
export const poiApi = {
  page: ({ cityName, keyword, page = 1, pageSize = 12 } = {}) =>
    http.get('/poi/page', { cityName, keyword, page, pageSize }),
  cities: () => http.get('/poi/cities'),
  add: (poi) => http.post('/poi/add', poi),
  update: (poi) => http.put('/poi/update', poi),
  remove: (id) => http.del(`/poi/delete/${id}`)
}

/* ==================== 收藏 /favorite ==================== */
export const favoriteApi = {
  list: () => http.get('/favorite/list'),
  add: (poiId) => http.post('/favorite/add', { poi_id: poiId }),
  remove: (poiId) => http.post('/favorite/remove', { poi_id: poiId }),
  check: (poiId) => http.get('/favorite/check', { poiId })
}

/* ==================== 偏好 /preference ==================== */
export const preferenceApi = {
  get: () => http.get('/preference/get'),
  save: (pref) => http.post('/preference/save', pref)
}

/* ==================== Agent（独立服务 :8291，仅供调试页使用） ==================== */
const AGENT_BASE = 'http://127.0.0.1:8291'

export const agentApi = {
  tools: async () => {
    const r = await fetch(`${AGENT_BASE}/agent/tools`)
    if (!r.ok) throw new Error(`Agent 工具列表获取失败（HTTP ${r.status}）`)
    return r.json()
  },
  chat: async ({ sessionId, userId, message }) => {
    const r = await fetch(`${AGENT_BASE}/agent/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, user_id: userId, message })
    })
    const b = await r.json().catch(() => null)
    if (!r.ok) throw new Error(b?.detail || `Agent 对话失败（HTTP ${r.status}）`)
    return b
  }
}
