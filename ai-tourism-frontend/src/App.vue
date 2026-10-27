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
  { name: 'favorites', label: '我的收藏', icon: 'heart' },
  { name: 'preference', label: '偏好设置', icon: 'sliders' }
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

    <!-- 极简科技底噪：极淡网格 -->
    <div class="bg-decor" aria-hidden="true" />

    <!-- 未登录：登录/注册整页 -->
    <template v-if="isGuest">
      <div class="app__full">
        <router-view />
      </div>
    </template>

    <!-- 已登录：左侧图标导航 + 内容区 -->
    <template v-else>
      <nav class="rail" aria-label="主导航">
        <div class="rail__brand" title="AI 智能旅游规划助手">
          <Icon name="compass" :size="21" :stroke="1.9" />
        </div>

        <ul class="rail__nav">
          <li v-for="item in NAV" :key="item.name">
            <RouterLink
              :to="{ name: item.name }"
              class="rail__item"
              :class="{ 'is-active': route.name === item.name }"
              :aria-current="route.name === item.name ? 'page' : undefined"
              :aria-label="item.label"
            >
              <Icon :name="item.icon" :size="19" />
              <span class="rail__tip" aria-hidden="true">{{ item.label }}</span>
            </RouterLink>
          </li>
        </ul>

        <div class="rail__foot">
          <button class="rail__avatar" :title="auth.nickname.value" :aria-label="'账号：' + (auth.nickname.value || '未命名')" @click="router.push({ name: 'preference' })">
            {{ initial }}
          </button>
          <button class="rail__item rail__item--quit" title="退出登录" aria-label="退出登录" @click="onLogout">
            <Icon name="logout" :size="18" />
            <span class="rail__tip" aria-hidden="true">退出登录</span>
          </button>
        </div>
      </nav>

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

/* ---------------- 左侧图标导航 ---------------- */
.rail {
  position: relative;
  z-index: 2;
  width: var(--rail-w);
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px 0 16px;
  /* 极简：中性半透明面 + 发丝描边即可分层，不用渐变 */
  background: rgba(10, 11, 13, 0.72);
  border-right: 1px solid var(--line);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.rail__brand {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin-bottom: 12px;
  border-radius: 10px;
  /* 极简：单色实心 + 极弱光晕，不做多色渐变与流动动画 */
  background: var(--accent);
  color: #08090A;
  box-shadow: 0 0 18px -10px rgba(34, 211, 238, 0.7);
}

.rail__nav {
  display: flex;
  flex-direction: column;
  gap: 5px;
  flex: 1;
}

.rail__item {
  position: relative;
  display: grid;
  place-items: center;
  /* 触控目标 ≥ 44×44（WCAG 2.2 / 平台 HIG 最小值） */
  width: 44px;
  height: 44px;
  border-radius: var(--r-md);
  color: var(--t3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.rail__item:hover {
  color: var(--t1);
  background: var(--glass-hover);
}

.rail__item.is-active {
  color: var(--accent-text);
  background: var(--accent-dim);
  box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.22);
}

/* 激活态左侧指示条 */
.rail__item.is-active::before {
  content: "";
  position: absolute;
  left: -14px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  border-radius: 0 3px 3px 0;
  background: var(--accent);
  box-shadow: var(--glow-cyan);
}

/* 悬浮提示 */
.rail__tip {
  position: absolute;
  left: calc(100% + 12px);
  top: 50%;
  transform: translateY(-50%) translateX(-6px);
  padding: 6px 11px;
  border-radius: var(--r-xs);
  background: rgba(20, 27, 48, 0.97);
  border: 1px solid var(--line-strong);
  color: var(--t1);
  /* 正文不小于 13px，保证小屏与弱视可读性 */
  font-size: 13px;
  line-height: 1.4;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur) var(--ease), transform var(--dur) var(--ease);
  box-shadow: var(--sh-2);
  z-index: 50;
}

/* 悬浮与键盘聚焦都显示提示：不能只依赖 hover */
.rail__item:hover .rail__tip,
.rail__item:focus-visible .rail__tip {
  opacity: 1;
  transform: translateY(-50%) translateX(0);
}

.rail__foot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.rail__avatar {
  position: relative;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 700;
  color: #CFFAFE;
  background: rgba(34, 211, 238, 0.14);
  border: 1px solid rgba(34, 211, 238, 0.34);
  transition: box-shadow var(--dur) var(--ease);
}

/* 视觉 36px，点击热区扩展到 44×44（小图标不放大小圆，用伪元素扩热区） */
.rail__avatar::after {
  content: "";
  position: absolute;
  inset: -4px;
  border-radius: 50%;
}

.rail__avatar:hover { box-shadow: var(--glow-cyan); }

.rail__item--quit:hover { color: #FCA5A5; background: var(--danger-dim); }

/* ---------------- 内容区 ---------------- */
.app__main {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

/* 路由切换动效 */
.view-enter-active { transition: opacity 0.24s var(--ease), transform 0.24s var(--ease-out); }
.view-leave-active { transition: opacity 0.14s var(--ease); }
.view-enter-from { opacity: 0; transform: translateY(8px); }
.view-leave-to { opacity: 0; }

/* 小屏：收窄轨道宽度，但触控目标仍保持 ≥44px */
@media (max-width: 720px) {
  .rail { width: 60px; }
  .rail__item { width: 44px; height: 44px; }
  .rail__nav { gap: 4px; }
}
</style>
