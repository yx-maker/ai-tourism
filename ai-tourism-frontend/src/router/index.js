import { createRouter, createWebHistory } from 'vue-router'
import { tokenStore } from '../api/client.js'

const routes = [
  { path: '/', redirect: '/chat' },

  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true, title: '登录' }
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guest: true, title: '注册' }
  },

  {
    path: '/chat',
    name: 'chat',
    component: () => import('../views/ChatView.vue'),
    meta: { auth: true, title: '智能规划' }
  },
  {
    path: '/budget',
    name: 'budget',
    component: () => import('../views/BudgetView.vue'),
    meta: { auth: true, title: '预算分析' }
  },
  {
    path: '/plans',
    name: 'plans',
    component: () => import('../views/PlansView.vue'),
    meta: { auth: true, title: '我的行程' }
  },
  {
    path: '/poi',
    name: 'poi',
    component: () => import('../views/PoiView.vue'),
    meta: { auth: true, title: '景点库' }
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('../views/FavoriteView.vue'),
    meta: { auth: true, title: '我的收藏' }
  },
  {
    path: '/preference',
    name: 'preference',
    component: () => import('../views/PreferenceView.vue'),
    meta: { auth: true, title: '偏好设置' }
  },

  { path: '/:pathMatch(.*)*', redirect: '/chat' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach((to) => {
  const logged = !!tokenStore.get()

  if (to.meta.auth && !logged) {
    return { path: '/login', query: to.fullPath !== '/chat' ? { redirect: to.fullPath } : {} }
  }
  if (to.meta.guest && logged) {
    return { path: '/chat' }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} · 旅途`
    : '旅途 · AI 智能旅游规划助手'
})

export default router
