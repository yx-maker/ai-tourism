<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Icon from '../components/Icon.vue'
import { auth } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

const router = useRouter()
const route = useRoute()

const form = reactive({ phone: '', password: '' })
const loading = ref(false)
const error = ref('')

const HIGHLIGHTS = [
  { icon: 'sparkle', title: '大模型驱动行程生成', desc: '自然语言描述需求，直接产出逐日行程与费用明细' },
  { icon: 'wallet', title: '预算硬约束', desc: '给定预算反推档次，超支自动阶梯回退，只压不抬' },
  { icon: 'route', title: '路线与景点联动', desc: '景点库 118 条真实 POI，按城市与热度智能编排' }
]

async function submit() {
  error.value = ''
  if (!form.phone.trim()) {
    error.value = '请输入手机号'
    return
  }
  if (!form.password) {
    error.value = '请输入密码'
    return
  }
  loading.value = true
  try {
    await auth.login(form.phone.trim(), form.password)
    toast.success(`欢迎回来，${auth.nickname.value}`)
    router.replace(route.query.redirect || '/chat')
  } catch (e) {
    error.value = errText(e, '登录失败，请检查手机号与密码')
  } finally {
    loading.value = false
  }
}

function fillDemo() {
  form.phone = '13800001111'
  form.password = 'Test123456'
}
</script>

<template>
  <div class="auth">
    <!-- 左侧品牌区 -->
    <section class="auth__hero">
      <div class="hero__badge">
        <Icon name="sparkle" :size="14" />
        <span>毕业论文演示系统</span>
      </div>

      <h1 class="hero__title">
        AI 智能旅游<br /><span class="grad-text">规划助手</span>
      </h1>

      <p class="hero__desc">
        用一句话描述你的旅行需求，系统自动生成逐日行程、路线与费用明细，
        并在预算约束下自动匹配出行档次。
      </p>

      <ul class="hero__list">
        <li v-for="h in HIGHLIGHTS" :key="h.title">
          <span class="hero__icon"><Icon :name="h.icon" :size="16" /></span>
          <div>
            <div class="hero__h">{{ h.title }}</div>
            <div class="hero__p">{{ h.desc }}</div>
          </div>
        </li>
      </ul>
    </section>

    <!-- 右侧表单区 -->
    <section class="auth__panel">
      <form class="card card--lit auth__form" @submit.prevent="submit">
        <header class="auth__head">
          <h2>登录</h2>
          <p>使用手机号继续</p>
        </header>

        <div class="field">
          <label class="field__label" for="phone">手机号</label>
          <input
            id="phone"
            v-model="form.phone"
            class="input"
            type="tel"
            inputmode="numeric"
            autocomplete="username"
            placeholder="请输入手机号"
            :disabled="loading"
          />
        </div>

        <div class="field">
          <label class="field__label" for="password">密码</label>
          <input
            id="password"
            v-model="form.password"
            class="input"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="loading"
          />
        </div>

        <div v-if="error" class="alert alert--danger">
          <Icon name="alert" :size="15" />
          <span>{{ error }}</span>
        </div>

        <button class="btn btn--primary btn--block" type="submit" :disabled="loading">
          <span v-if="loading" class="spinner" />
          <span>{{ loading ? '登录中…' : '登 录' }}</span>
        </button>

        <div class="auth__foot">
          <span class="t3">还没有账号？</span>
          <RouterLink to="/register" class="auth__link">立即注册</RouterLink>
        </div>

        <button type="button" class="auth__demo" @click="fillDemo">
          <Icon name="info" :size="13" />
          填入演示账号
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: 1.08fr 0.92fr;
  min-height: 100%;
}

/* ---------------- 左侧 ---------------- */
.auth__hero {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 26px;
  padding: 64px clamp(32px, 6vw, 88px);
}

.hero__badge {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  align-self: flex-start;
  height: 29px;
  padding: 0 13px;
  border-radius: var(--r-full);
  font-size: 12.5px;
  font-weight: 550;
  color: #A5F3FC;
  background: var(--grad-brand-soft);
  border: 1px solid rgba(34, 211, 238, 0.28);
}

.hero__title {
  font-size: clamp(34px, 4.4vw, 52px);
  font-weight: 780;
  line-height: 1.16;
  letter-spacing: -1.4px;
}

.hero__desc {
  max-width: 460px;
  font-size: 14.5px;
  line-height: 1.85;
  color: var(--t2);
}

.hero__list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 470px;
  margin-top: 6px;
}

.hero__list li {
  display: flex;
  gap: 13px;
  align-items: flex-start;
}

.hero__icon {
  display: grid;
  place-items: center;
  width: 33px;
  height: 33px;
  flex: none;
  border-radius: 10px;
  color: var(--cyan);
  background: rgba(34, 211, 238, 0.1);
  border: 1px solid rgba(34, 211, 238, 0.22);
}

.hero__h {
  font-size: 13.8px;
  font-weight: 620;
  margin-bottom: 2px;
}

.hero__p {
  font-size: 12.8px;
  color: var(--t3);
  line-height: 1.6;
}

/* ---------------- 右侧 ---------------- */
.auth__panel {
  display: grid;
  place-items: center;
  padding: 40px 32px;
  border-left: 1px solid var(--line);
  background: rgba(6, 9, 16, 0.42);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.auth__form {
  width: min(392px, 100%);
  padding: 34px 30px 26px;
  display: flex;
  flex-direction: column;
  gap: 17px;
  box-shadow: var(--sh-3);
  animation: pop-in 0.42s var(--ease-out) both;
}

.auth__head h2 {
  font-size: 22px;
  font-weight: 720;
  letter-spacing: -0.4px;
}

.auth__head p {
  margin-top: 5px;
  font-size: 13px;
  color: var(--t3);
}

.auth__foot {
  display: flex;
  justify-content: center;
  gap: 6px;
  font-size: 13px;
}

.auth__link {
  color: var(--cyan);
  font-weight: 550;
}

.auth__link:hover { text-decoration: underline; }

.auth__demo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: -4px;
  font-size: 12.5px;
  color: var(--t3);
  padding: 6px;
  border-radius: var(--r-xs);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.auth__demo:hover { color: var(--cyan); background: var(--glass-hover); }

@media (max-width: 940px) {
  .auth { grid-template-columns: 1fr; }
  .auth__hero { padding: 44px 26px 10px; gap: 20px; }
  .hero__list { display: none; }
  .hero__desc { display: none; }
  .auth__panel {
    border-left: 0;
    border-top: 1px solid var(--line);
    padding: 26px 20px 44px;
    align-items: start;
  }
}
</style>
