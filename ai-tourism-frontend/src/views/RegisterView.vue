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
    <section class="auth__hero">
      <div class="hero__badge">
        <Icon name="shield" :size="14" />
        <span>创建账号</span>
      </div>
      <h1 class="hero__title">
        开始你的<br /><span class="grad-text">第一段行程</span>
      </h1>
      <p class="hero__desc">
        注册后即可保存对话、收藏景点、设置出行偏好，
        让每一次规划都更贴合你的习惯。
      </p>
      <ul class="hero__facts">
        <li><Icon name="check" :size="15" /><span>行程对话永久保存，随时回看</span></li>
        <li><Icon name="check" :size="15" /><span>收藏景点库中 118 条真实 POI</span></li>
        <li><Icon name="check" :size="15" /><span>预算区间与出行风格可复用</span></li>
      </ul>
    </section>

    <section class="auth__panel">
      <form class="card card--lit auth__form" @submit.prevent="submit">
        <header class="auth__head">
          <h2>注册</h2>
          <p>仅需手机号即可创建</p>
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

        <div v-if="error" class="alert alert--danger">
          <Icon name="alert" :size="15" />
          <span>{{ error }}</span>
        </div>

        <button class="btn btn--primary btn--block" type="submit" :disabled="loading || !canSubmit">
          <span v-if="loading" class="spinner" />
          <span>{{ loading ? '注册中…' : '创建账号' }}</span>
        </button>

        <div class="auth__foot">
          <span class="t3">已有账号？</span>
          <RouterLink to="/login" class="auth__link">返回登录</RouterLink>
        </div>
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

.auth__hero {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 24px;
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

.hero__facts {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 4px;
}

.hero__facts li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  color: var(--t2);
}

.hero__facts svg { color: var(--teal); }

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
  padding: 32px 30px 24px;
  display: flex;
  flex-direction: column;
  gap: 15px;
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

@media (max-width: 940px) {
  .auth { grid-template-columns: 1fr; }
  .auth__hero { padding: 40px 26px 8px; gap: 18px; }
  .hero__desc, .hero__facts { display: none; }
  .auth__panel {
    border-left: 0;
    border-top: 1px solid var(--line);
    padding: 24px 20px 44px;
    align-items: start;
  }
}
</style>
