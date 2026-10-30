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

/* 登录页用一段「产品正在工作」的演示行程作为证明，不让抽象图形代替内容。
   数据为演示用途，页面上明确标注。 */
const DEMO_DAYS = [
  { d: 'D1', name: '镇北堡西部影城', extra: '西夏王陵 · 怀远夜市', cost: '¥ 486' },
  { d: 'D2', name: '沙湖', extra: '贺兰山岩画 · 览山公园', cost: '¥ 412' },
  { d: 'D3', name: '鼓楼', extra: '南关清真大寺 · 返程', cost: '¥ 398' }
]

const DEMO_SPLIT = [
  { label: '交通', pct: 38, tone: 'a' },
  { label: '住宿', pct: 26, tone: 'b' },
  { label: '餐饮', pct: 20, tone: 'c' },
  { label: '门票', pct: 16, tone: 'd' }
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
    <div class="auth__inner">
      <!-- 左：主张 + 产品实证 -->
      <section class="intro">
        <div class="intro__brand rise">
          <span class="intro__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
              <path d="M4 17.2 9.4 7l3.6 6.2L15.4 9l4.6 8.2" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
              <circle cx="9.4" cy="7" r="1.9" fill="currentColor" />
            </svg>
          </span>
          <span class="intro__name">旅途</span>
          <span class="intro__tag">AI 智能旅游规划</span>
        </div>

        <div class="intro__main">
          <h1 class="intro__title rise rise-2">
            把一趟旅行，<br />算清楚再出发。
          </h1>
          <p class="intro__lede rise rise-3">
            说出目的地、天数与预算，得到逐日行程、真实票价与分项预算。
            超支时会自动降档，而不是先给你一份漂亮却对不上的账单。
          </p>

          <!-- 产品实证：一段真实结构的行程预览 -->
          <article class="preview rise rise-4" aria-label="行程示例（演示数据）">
            <header class="preview__head">
              <div class="preview__where">
                <span class="preview__city">银川</span>
                <span class="preview__meta">3 天 2 晚 · 2 人 · 高铁往返</span>
              </div>
              <div class="preview__sum">
                <span class="preview__amount">2,868</span>
                <span class="preview__cap">元 · 预算 3,000</span>
              </div>
            </header>

            <ol class="days">
              <li v-for="day in DEMO_DAYS" :key="day.d" class="day">
                <span class="day__no">{{ day.d }}</span>
                <span class="day__line" aria-hidden="true" />
                <div class="day__body">
                  <span class="day__name">{{ day.name }}</span>
                  <span class="day__extra">{{ day.extra }}</span>
                </div>
                <span class="day__cost">{{ day.cost }}</span>
              </li>
            </ol>

            <div class="split">
              <div
                v-for="s in DEMO_SPLIT"
                :key="s.label"
                class="split__seg"
                :class="`split__seg--${s.tone}`"
                :style="{ width: s.pct + '%' }"
              >
                <span>{{ s.label }}</span>
              </div>
            </div>

            <p class="preview__note">演示数据 · 由系统生成，非真实订单</p>
          </article>
        </div>

        <p class="intro__foot">本科毕业设计 · 智能旅游规划助手</p>
      </section>

      <!-- 右：登录表单 -->
      <section class="entry">
        <form class="form" @submit.prevent="submit">
          <header class="form__head">
            <h2 class="form__title">登录</h2>
            <p class="form__sub">使用手机号继续</p>
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

          <div v-if="error" class="alert alert--danger" role="alert">
            <Icon name="alert" :size="15" />
            <span>{{ error }}</span>
          </div>

          <button class="btn btn--primary btn--block form__submit" type="submit" :disabled="loading">
            <span v-if="loading" class="spinner" />
            <span>{{ loading ? '正在登录…' : '登录' }}</span>
          </button>

          <div class="form__foot">
            <span class="t3">还没有账号？</span>
            <RouterLink to="/register" class="form__link">创建账号</RouterLink>
          </div>

          <button type="button" class="form__demo" @click="fillDemo">
            填入演示账号
            <span class="form__demo-id mono">13800001111</span>
          </button>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.auth {
  min-height: 100%;
  display: flex;
  justify-content: center;
  background: var(--paper);
}

.auth__inner {
  width: 100%;
  max-width: 1320px;
  min-height: 100vh;
  padding: 0 40px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 64px;
  align-items: stretch;
}

/* ---------------- 左侧 ---------------- */
.intro {
  display: flex;
  flex-direction: column;
  padding: 34px 0 30px;
  min-width: 0;
}

.intro__brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  flex: none;
}

.intro__mark {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--accent);
  color: #F7FBF9;
}

.intro__name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.06em;
}

.intro__tag {
  padding-left: 10px;
  margin-left: 2px;
  border-left: 1px solid var(--line);
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}

.intro__main {
  margin: auto 0;
  padding: 40px 0;
  max-width: 620px;
}

.intro__title {
  font-size: clamp(36px, 4vw, 56px);
  font-weight: 600;
  line-height: 1.16;
  letter-spacing: -0.028em;
  color: var(--ink);
}

.intro__lede {
  margin-top: 22px;
  max-width: 46ch;
  font-size: 15px;
  line-height: 1.75;
  color: var(--ink-2);
}

/* 行程预览：白纸 + 发丝线，靠排版而非阴影 */
.preview {
  margin-top: 42px;
  max-width: 560px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  padding: 20px 22px 16px;
}

.preview__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line-faint);
}

.preview__where {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.preview__city {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.preview__meta,
.preview__cap {
  font-size: 12px;
  color: var(--ink-3);
}

.preview__sum {
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex: none;
}

.preview__amount {
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

.days {
  padding: 6px 0 0;
}

.day {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 12px;
  padding: 9px 0;
}

.day__no {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--ink-3);
  letter-spacing: 0.04em;
}

/* 序号前的定位点：整条行程只有一个视觉标记，不再画连线 */
.day__no::before {
  content: "";
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
}

.day__line { display: none; }

.day__body {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.day__name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink);
  white-space: nowrap;
}

.day__extra {
  font-size: 12px;
  color: var(--ink-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.day__cost {
  font-size: 12.5px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

/* 预算构成：一条完整的横向条，不是四个卡片 */
.split {
  display: flex;
  height: 30px;
  margin-top: 14px;
  border-radius: var(--r-sm);
  overflow: hidden;
  border: 1px solid var(--line-faint);
}

.split__seg {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
}

.split__seg--a { background: var(--accent); color: #F4FBF9; }
.split__seg--b { background: #CFE3DE; color: #23443F; }
.split__seg--c { background: #E6E3D6; color: #4B4838; }
.split__seg--d { background: var(--paper-3); color: var(--ink-3); }

.preview__note {
  margin-top: 10px;
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.01em;
}

.intro__foot {
  font-size: 11.5px;
  color: var(--ink-4);
  letter-spacing: 0.02em;
}

/* ---------------- 右侧表单 ---------------- */
.entry {
  display: flex;
  align-items: center;
  border-left: 1px solid var(--line);
  padding: 40px 0 40px 56px;
}

.form {
  width: 100%;
  max-width: 330px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form__head { margin-bottom: 6px; }

.form__title {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.03em;
}

.form__sub {
  margin-top: 6px;
  font-size: 13px;
  color: var(--ink-3);
}

.form__submit {
  height: 44px;
  margin-top: 4px;
  font-size: 14px;
}

.form__foot {
  display: flex;
  gap: 6px;
  padding-top: 4px;
  font-size: 13px;
}

.form__link {
  color: var(--accent-text);
  font-weight: 500;
  text-decoration: underline;
  text-underline-offset: 3px;
  text-decoration-color: var(--accent-line);
}

.form__link:hover { text-decoration-color: var(--accent); }

.form__demo {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--ink-4);
  border-bottom: 1px dashed var(--line);
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.form__demo:hover {
  color: var(--accent-text);
  border-color: var(--accent-line);
}

.form__demo-id {
  font-size: 11px;
  letter-spacing: 0.04em;
}

/* ---------------- 响应式 ---------------- */
@media (max-width: 1040px) {
  .auth__inner {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    max-width: 620px;
    padding: 0 28px 48px;
  }

  .intro { padding-bottom: 0; }
  .intro__main { padding: 36px 0 32px; }
  .intro__foot { display: none; }

  .entry {
    border-left: 0;
    border-top: 1px solid var(--line);
    margin: 0;
    padding: 32px 0 0;
    display: block;
  }
}

@media (max-width: 560px) {
  .auth__inner { padding: 0 20px 40px; }
  .intro__title { font-size: 34px; }
  .intro__lede { font-size: 14px; }
  .preview { padding: 16px 16px 14px; }
  .day { grid-template-columns: 32px minmax(0, 1fr) auto; gap: 10px; }
  .day__extra { display: none; }
  .preview__meta { font-size: 11.5px; }
}
</style>
