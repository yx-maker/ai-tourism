<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from './components/Icon.vue'
import ToastHost from './components/ToastHost.vue'
import { auth, bindUnauthorized } from './stores/auth.js'
import { toast } from './stores/toast.js'

const route = useRoute()
const router = useRouter()

const isGuest = computed(() => !!route.meta.guest)

const NAV = [
  { name: 'chat', label: '智能规划', icon: 'sparkle' },
  { name: 'plans', label: '我的行程', icon: 'route' },
  { name: 'budget', label: '预算分析', icon: 'wallet' },
  { name: 'poi', label: '景点库', icon: 'pin' },
  { name: 'favorites', label: '收藏', icon: 'heart' }
]

const initial = computed(() => (auth.nickname.value || '旅').slice(0, 1).toUpperCase())

async function onLogout() {
  await auth.logout()
  toast.info('已退出登录')
  router.replace('/login')
}

onMounted(() => {
  // 会话失效时统一跳登录页
  bindUnauthorized(() => {
    auth.forceClear()
    if (router.currentRoute.value.path !== '/login') {
      router.replace('/login')
    }
  })
  // 刷新页面后用本地 token 补齐用户信息
  if (auth.isLoggedIn.value && !auth.state.user) {
    auth.hydrate()
  }
})
</script>

<template>
  <div class="app">
    <!-- 键盘用户的跳转链接（无障碍） -->
    <a class="skip-link" href="#main-content">跳到主内容</a>

    <div class="bg-decor" aria-hidden="true" />

    <!-- 未登录：登录/注册整页 -->
    <template v-if="isGuest">
      <div class="app__full">
        <router-view />
      </div>
    </template>

    <!-- 已登录：顶部横向导航 + 内容区 -->
    <template v-else>
      <header class="topbar">
        <div class="topbar__inner">
          <RouterLink :to="{ name: 'chat' }" class="brand" aria-label="旅途 · AI 智能旅游规划助手">
            <span class="brand__mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
                <path d="M4 17.2 9.4 7l3.6 6.2L15.4 9l4.6 8.2" stroke="currentColor"
                      stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                <circle cx="9.4" cy="7" r="1.9" fill="currentColor" />
              </svg>
            </span>
            <span class="brand__name">旅途</span>
            <span class="brand__tag">AI</span>
          </RouterLink>

          <nav class="nav" aria-label="主导航">
            <RouterLink
              v-for="item in NAV"
              :key="item.name"
              :to="{ name: item.name }"
              class="nav__item"
              :class="{ 'is-active': route.name === item.name }"
              :aria-current="route.name === item.name ? 'page' : undefined"
            >
              <Icon :name="item.icon" :size="17" class="nav__icon" />
              <span class="nav__label">{{ item.label }}</span>
            </RouterLink>
          </nav>

          <div class="topbar__right">
            <RouterLink
              :to="{ name: 'preference' }"
              class="icon-btn"
              :class="{ 'is-active': route.name === 'preference' }"
              aria-label="偏好设置"
              title="偏好设置"
            >
              <Icon name="sliders" :size="17" />
            </RouterLink>

            <span class="topbar__divider" aria-hidden="true" />

            <button
              class="account"
              :aria-label="'账号：' + (auth.nickname.value || '未命名')"
              @click="router.push({ name: 'preference' })"
            >
              <span class="account__avatar">{{ initial }}</span>
              <span class="account__name">{{ auth.nickname.value || '我的账号' }}</span>
            </button>

            <button class="icon-btn icon-btn--quit" title="退出登录" aria-label="退出登录" @click="onLogout">
              <Icon name="logout" :size="17" />
            </button>
          </div>
        </div>
      </header>

      <main id="main-content" class="app__main" tabindex="-1">
        <router-view v-slot="{ Component }">
          <Transition name="view" mode="out-in">
            <component :is="Component" />
          </Transition>
        </router-view>
      </main>
    </template>

    <ToastHost />
  </div>
</template>

<style scoped>
.app {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.app__full {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  overflow-y: auto;
}

/* ---------------- 顶部导航 ---------------- */
.topbar {
  position: relative;
  z-index: 30;
  flex: none;
  height: var(--nav-h);
  background: rgba(250, 249, 245, 0.86);
  border-bottom: 1px solid var(--line);
  backdrop-filter: saturate(180%) blur(12px);
  -webkit-backdrop-filter: saturate(180%) blur(12px);
}

.topbar__inner {
  max-width: 1520px;
  height: 100%;
  margin: 0 auto;
  padding: 0 28px;
  display: flex;
  align-items: center;
  gap: 28px;
}

/* 品牌 */
.brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  flex: none;
  height: 40px;
  margin-left: -6px;
  padding: 0 6px;
  border-radius: var(--r-sm);
}

.brand__mark {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--accent);
  color: #F7FBF9;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22);
}

.brand__name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--ink);
}

.brand__tag {
  display: inline-grid;
  place-items: center;
  height: 17px;
  padding: 0 4px;
  border-radius: 3px;
  border: 1px solid var(--line-strong);
  font-family: var(--font-mono);
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: 0.06em;
  color: var(--ink-3);
}

/* 导航项 */
.nav {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  scrollbar-width: none;
}

.nav::-webkit-scrollbar { display: none; }

.nav__item {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--r-sm);
  font-size: 13.5px;
  font-weight: 450;
  color: var(--ink-3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.nav__item:hover {
  color: var(--ink);
  background: var(--glass-hover);
}

.nav__item.is-active {
  color: var(--ink);
  font-weight: 550;
}

/* 激活指示：一条 2px 短线，不用色块 */
.nav__item.is-active::after {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 3px;
  height: 2px;
  border-radius: 2px;
  background: var(--accent);
}

.nav__icon { display: none; }

/* 右侧账号 */
.topbar__right {
  flex: none;
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon-btn {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  color: var(--ink-3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.icon-btn:hover,
.icon-btn.is-active {
  color: var(--ink);
  background: var(--glass-hover);
}

.icon-btn--quit:hover {
  color: var(--danger);
  background: var(--danger-dim);
}

.topbar__divider {
  width: 1px;
  height: 18px;
  margin: 0 6px;
  background: var(--line);
}

.account {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 8px 0 4px;
  border-radius: var(--r-sm);
  transition: background var(--dur) var(--ease);
}

.account:hover { background: var(--glass-hover); }

.account__avatar {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-dim);
  border: 1px solid var(--accent-line);
  color: var(--accent-text);
  font-size: 12px;
  font-weight: 600;
}

.account__name {
  max-width: 108px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--ink-2);
}

/* ---------------- 内容区 ---------------- */
.app__main {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* 路由切换 */
.view-enter-active { transition: opacity 0.2s var(--ease), transform 0.2s var(--ease-out); }
.view-leave-active { transition: opacity 0.12s var(--ease); }
.view-enter-from { opacity: 0; transform: translateY(4px); }
.view-leave-to { opacity: 0; }

/* ---------------- 响应式 ---------------- */
@media (max-width: 1080px) {
  .topbar__inner { gap: 16px; padding: 0 18px; }
  .account__name { display: none; }
}

@media (max-width: 780px) {
  .app { --nav-h: 56px; }
  .topbar__inner { padding: 0 10px; gap: 6px; }
  .brand { gap: 7px; padding: 0 4px; }
  .brand__name { font-size: 14px; letter-spacing: 0.04em; }
  .brand__tag { display: none; }
  .nav { gap: 0; overflow: visible; justify-content: flex-end; }
  .nav__item { width: 40px; padding: 0; justify-content: center; }
  .nav__icon { display: block; }
  .nav__label { display: none; }
  .nav__item.is-active::after { left: 9px; right: 9px; bottom: 2px; }
  .topbar__divider { display: none; }
  .icon-btn--quit { display: none; }
  .topbar__right .icon-btn { display: none; }
  .account { padding: 0; }
}

@media (max-width: 420px) {
  .nav { justify-content: center; }
  .nav__item { width: 38px; }
}
</style>
