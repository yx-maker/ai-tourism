<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import { auth } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

const router = useRouter()

const form = reactive({ phone: '', nickname: '', password: '', confirm: '' })
const loading = ref(false)
const error = ref('')

const phoneOk = computed(() => /^1[3-9]\d{9}$/.test(form.phone.trim()))
const pwdOk = computed(() => form.password.length >= 6)
const matchOk = computed(() => form.password && form.password === form.confirm)
const canSubmit = computed(() => phoneOk.value && pwdOk.value && matchOk.value)

async function submit() {
  error.value = ''
  if (!phoneOk.value) {
    error.value = '请输入有效的 11 位手机号'
    return
  }
  if (!pwdOk.value) {
    error.value = '密码至少 6 位'
    return
  }
  if (!matchOk.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    await auth.register({
      phone: form.phone.trim(),
      password: form.password,
      nickname: form.nickname.trim() || undefined
    })
    toast.success('注册成功，请登录')
    router.replace({ path: '/login', query: { phone: form.phone.trim() } })
  } catch (e) {
    error.value = errText(e, '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <div class="auth__inner">
      <section class="intro">
        <RouterLink to="/login" class="intro__brand">
          <span class="intro__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none">
              <path d="M4 17.2 9.4 7l3.6 6.2L15.4 9l4.6 8.2" stroke="currentColor"
                    stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
              <circle cx="9.4" cy="7" r="1.9" fill="currentColor" />
            </svg>
          </span>
          <span class="intro__name">旅途</span>
          <span class="intro__tag">AI 智能旅游规划</span>
        </RouterLink>

        <div class="intro__main">
          <h1 class="intro__title rise">
            开一个账号，<br />让行程记得你。
          </h1>
          <p class="intro__lede rise rise-2">
            注册后对话、行程和收藏都会保留，偏好设置也会参与下一次规划。
          </p>

          <ul class="facts rise rise-3">
            <li class="fact">
              <span class="fact__k">对话</span>
              <span class="fact__v">行程对话永久保存，随时回看</span>
            </li>
            <li class="fact">
              <span class="fact__k">景点</span>
              <span class="fact__v">收藏景点库中的真实 POI 与票价</span>
            </li>
            <li class="fact">
              <span class="fact__k">偏好</span>
              <span class="fact__v">预算区间与出行风格可复用</span>
            </li>
          </ul>
        </div>

        <p class="intro__foot">账号仅用于本人演示，不采集身份信息</p>
      </section>

      <section class="entry">
        <form class="form" @submit.prevent="submit">
          <header class="form__head">
            <h2 class="form__title">创建账号</h2>
            <p class="form__sub">仅需手机号即可开始</p>
          </header>

          <div class="field">
            <label class="field__label" for="r-phone">手机号</label>
            <input
              id="r-phone"
              v-model="form.phone"
              class="input"
              :class="{ 'input--err': form.phone && !phoneOk }"
              type="tel"
              inputmode="numeric"
              placeholder="11 位手机号"
              :disabled="loading"
            />
          </div>

          <div class="field">
            <label class="field__label" for="r-nick">昵称<span class="t3">（选填）</span></label>
            <input
              id="r-nick"
              v-model="form.nickname"
              class="input"
              type="text"
              maxlength="20"
              placeholder="不填则系统自动生成"
              :disabled="loading"
            />
          </div>

          <div class="field">
            <label class="field__label" for="r-pwd">密码</label>
            <input
              id="r-pwd"
              v-model="form.password"
              class="input"
              :class="{ 'input--err': form.password && !pwdOk }"
              type="password"
              placeholder="至少 6 位"
              :disabled="loading"
            />
          </div>

          <div class="field">
            <label class="field__label" for="r-cfm">确认密码</label>
            <input
              id="r-cfm"
              v-model="form.confirm"
              class="input"
              :class="{ 'input--err': form.confirm && !matchOk }"
              type="password"
              placeholder="再次输入密码"
              :disabled="loading"
            />
          </div>

          <div v-if="error" class="alert alert--danger" role="alert">
            <Icon name="alert" :size="15" />
            <span>{{ error }}</span>
          </div>

          <button class="btn btn--primary btn--block form__submit" type="submit" :disabled="loading || !canSubmit">
            <span v-if="loading" class="spinner" />
            <span>{{ loading ? '正在创建…' : '创建账号' }}</span>
          </button>

          <div class="form__foot">
            <span class="t3">已有账号？</span>
            <RouterLink to="/login" class="form__link">返回登录</RouterLink>
          </div>
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
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 72px;
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
  align-self: flex-start;
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
  border-left: 1px solid var(--line);
  font-size: 12px;
  color: var(--ink-3);
}

.intro__main {
  margin: auto 0;
  padding: 40px 0;
  max-width: 560px;
}

.intro__title {
  font-size: clamp(36px, 4vw, 54px);
  font-weight: 600;
  line-height: 1.12;
  letter-spacing: -0.04em;
}

.intro__lede {
  margin-top: 20px;
  font-size: 15px;
  line-height: 1.75;
  color: var(--ink-2);
  max-width: 42ch;
}

/* 三条能力用细线清单，不用三个卡片 */
.facts {
  margin-top: 36px;
  border-top: 1px solid var(--line);
}

.fact {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 16px;
  align-items: baseline;
  padding: 13px 0;
  border-bottom: 1px solid var(--line-faint);
}

.fact__k {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--ink-4);
}

.fact__v {
  font-size: 13.5px;
  color: var(--ink-2);
}

.intro__foot {
  font-size: 11.5px;
  color: var(--ink-4);
}

/* ---------------- 右侧表单 ---------------- */
.entry {
  display: flex;
  align-items: center;
  border-left: 1px solid var(--line);
  padding: 40px 0 40px 48px;
}

.form {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
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
  padding-top: 2px;
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

/* ---------------- 响应式 ---------------- */
@media (max-width: 1040px) {
  .auth__inner {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
    max-width: 620px;
    padding: 0 28px 48px;
  }

  .intro { padding-bottom: 0; }
  .intro__main { padding: 34px 0 28px; }
  .intro__foot { display: none; }
  .facts { margin-top: 28px; }

  .entry {
    border-left: 0;
    border-top: 1px solid var(--line);
    padding: 30px 0 0;
    display: block;
  }
}

@media (max-width: 560px) {
  .auth__inner { padding: 0 20px 40px; }
  .intro__title { font-size: 32px; }
  .fact { grid-template-columns: 60px minmax(0, 1fr); gap: 12px; }
}
</style>
