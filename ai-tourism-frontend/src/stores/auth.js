/**
 * 全局轻量状态：登录态 + 用户信息
 * 不引入 Pinia，用 Vue 的 reactive 即可满足规模。
 */
import { reactive, computed } from 'vue'
import { authApi } from '../api/index.js'
import { tokenStore, setUnauthorizedHandler } from '../api/client.js'

const state = reactive({
  user: tokenStore.getUser(),
  loading: false
})

export const auth = {
  state,
  isLoggedIn: computed(() => !!tokenStore.get()),
  userId: computed(() => state.user?.user_id || ''),
  nickname: computed(() => state.user?.nickname || '旅行者'),
  roles: computed(() => state.user?.roles || []),

  async login(phone, password) {
    const d = await authApi.login(phone, password)
    tokenStore.set(d.token)
    tokenStore.setRefresh(d.refresh_token)
    const user = d.user || {}
    tokenStore.setUser(user)
    state.user = user

    // 登录响应里的 user 不含 roles，补一次 /auth/me 拿到角色（景点管理需 ROOT）
    try {
      const full = await authApi.me()
      tokenStore.setUser(full)
      state.user = full
    } catch {
      /* 补角色失败不影响登录本身 */
    }
    return state.user
  },

  async register(payload) {
    return authApi.register(payload)
  },

  /** 拉取最新用户信息（刷新页面后补齐） */
  async hydrate() {
    if (!tokenStore.get()) return null
    try {
      const u = await authApi.me()
      tokenStore.setUser(u)
      state.user = u
      return u
    } catch {
      return null
    }
  },

  async logout() {
    try {
      await authApi.logout()
    } catch {
      /* 后端登出失败也要清本地态 */
    }
    tokenStore.clear()
    state.user = null
  },

  /** 本地清态（会话失效时由请求层回调触发） */
  forceClear() {
    tokenStore.clear()
    state.user = null
  }
}

export const isAdmin = () => (state.user?.roles || []).includes('ROOT')

/** 注册会话失效回调，由 router 在初始化时注入跳转逻辑 */
export function bindUnauthorized(fn) {
  setUnauthorizedHandler(fn)
}
