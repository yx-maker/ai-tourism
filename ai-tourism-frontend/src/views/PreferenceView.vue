<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import { preferenceApi } from '../api/index.js'
import { auth } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

const router = useRouter()

const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)

const form = reactive({
  budget_min: null,
  budget_max: null,
  travel_style: '',
  interests: '',
  pace: '',
  companion: ''
})

const STYLES = ['休闲', '深度', '打卡', '美食', '户外', '文化', '亲子', '购物']
const PACES = ['轻松', '适中', '紧凑']
const COMPANIONS = ['独自', '情侣', '朋友', '家庭', '亲子', '团队']

const PRESET_INTERESTS = ['历史古迹', '美食', '自然风光', '博物馆', '摄影', '夜生活', '演出', '温泉', '徒步', '购物']

const interestTags = computed(() =>
  (form.interests || '')
    .split(/[,，、\s]+/)
    .map((s) => s.trim())
    .filter(Boolean)
)

const budgetInvalid = computed(() => {
  const a = Number(form.budget_min)
  const b = Number(form.budget_max)
  if (!Number.isFinite(a) || !Number.isFinite(b) || a <= 0 || b <= 0) return false
  return a > b
})

function touch() {
  dirty.value = true
}

function toggleInterest(tag) {
  const has = interestTags.value.includes(tag)
  const next = has
    ? interestTags.value.filter((t) => t !== tag)
    : [...interestTags.value, tag]
  form.interests = next.join(',')
  touch()
}

async function load() {
  loading.value = true
  try {
    const d = await preferenceApi.get()
    if (d) {
      form.budget_min = d.budget_min ?? null
      form.budget_max = d.budget_max ?? null
      form.travel_style = d.travel_style || ''
      form.interests = d.interests || ''
      form.pace = d.pace || ''
      form.companion = d.companion || ''
    }
  } catch (e) {
    // 尚未设置偏好时后端可能返回空，不当作错误弹窗
    if (e?.code !== 0) console.warn('偏好读取失败:', e?.message)
  } finally {
    loading.value = false
    dirty.value = false
  }
}

async function save() {
  if (budgetInvalid.value) {
    toast.warn('预算下限不能高于上限')
    return
  }
  saving.value = true
  try {
    await preferenceApi.save({
      budget_min: form.budget_min === '' || form.budget_min === null ? null : Number(form.budget_min),
      budget_max: form.budget_max === '' || form.budget_max === null ? null : Number(form.budget_max),
      travel_style: form.travel_style || null,
      interests: form.interests || null,
      pace: form.pace || null,
      companion: form.companion || null
    })
    toast.success('偏好已保存')
    dirty.value = false
  } catch (e) {
    toast.error(errText(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">偏好设置</h1>
          <p class="page-head__sub">保存后可在规划时作为默认参考，减少重复描述</p>
        </div>
        <button class="btn btn--primary" :disabled="saving || loading" @click="save">
          <span v-if="saving" class="spinner" />
          <Icon v-else name="check" :size="15" />
          {{ saving ? '保存中…' : '保存偏好' }}
        </button>
      </header>

      <div class="layout">
        <div class="col-main">
          <!-- 账号 -->
          <section class="card card--solid card--lit panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="user" :size="16" /> 账号信息</h2>
            </div>
            <div class="account">
              <div class="account__avatar">{{ (auth.nickname.value || '旅').slice(0, 1).toUpperCase() }}</div>
              <div class="account__info">
                <div class="account__name">{{ auth.nickname.value }}</div>
                <div class="account__sub">
                  <span class="mono">{{ (auth.userId.value || "").slice(0, 8) }}</span>
                  <span v-for="r in auth.roles.value" :key="r" class="badge badge--muted">{{ r }}</span>
                </div>
              </div>
            </div>
          </section>

          <!-- 预算区间 -->
          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="wallet" :size="16" /> 预算区间</h2>
            </div>

            <div class="grid-2">
              <div class="field">
                <label class="field__label">预算下限（元）</label>
                <input
                  v-model="form.budget_min"
                  class="input"
                  type="number"
                  min="0"
                  placeholder="2000"
                  @input="touch"
                />
              </div>
              <div class="field">
                <label class="field__label">预算上限（元）</label>
                <input
                  v-model="form.budget_max"
                  class="input"
                  :class="{ 'input--err': budgetInvalid }"
                  type="number"
                  min="0"
                  placeholder="5000"
                  @input="touch"
                />
              </div>
            </div>

            <div v-if="budgetInvalid" class="alert alert--danger" style="margin-top: 12px">
              <Icon name="alert" :size="15" />
              <span>预算下限不能高于上限</span>
            </div>
          </section>

          <!-- 出行风格 -->
          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="compass" :size="16" /> 出行风格</h2>
            </div>
            <div class="chips chips--pick">
              <button
                v-for="s in STYLES"
                :key="s"
                class="chip"
                :class="{ 'is-on': form.travel_style === s }"
                @click="form.travel_style = form.travel_style === s ? '' : s; touch()"
              >
                {{ s }}
              </button>
            </div>
          </section>

          <!-- 兴趣 -->
          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="star" :size="16" /> 兴趣偏好</h2>
              <span v-if="interestTags.length" class="badge badge--brand">已选 {{ interestTags.length }}</span>
            </div>

            <div class="chips" style="margin-bottom: 14px">
              <button
                v-for="t in PRESET_INTERESTS"
                :key="t"
                class="chip"
                :class="{ 'is-on': interestTags.includes(t) }"
                @click="toggleInterest(t)"
              >
                {{ t }}
              </button>
            </div>

            <div class="field">
              <label class="field__label">自定义（逗号分隔）</label>
              <input
                v-model="form.interests"
                class="input"
                type="text"
                placeholder="如：历史古迹,美食,摄影"
                @input="touch"
              />
            </div>
          </section>
        </div>

        <!-- 右栏 -->
        <aside class="col-side">
          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="clock" :size="16" /> 行程节奏</h2>
            </div>
            <div class="seg" role="group" aria-label="行程节奏">
              <button
                v-for="p in PACES"
                :key="p"
                :class="{ 'is-on': form.pace === p }"
                :aria-pressed="form.pace === p"
                @click="form.pace = form.pace === p ? '' : p; touch()"
              >
                {{ p }}
              </button>
            </div>
          </section>

          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="user" :size="16" /> 同行人</h2>
            </div>
            <div class="tiles" role="group" aria-label="同行人">
              <button
                v-for="c in COMPANIONS"
                :key="c"
                class="tile"
                :class="{ 'is-on': form.companion === c }"
                :aria-pressed="form.companion === c"
                @click="form.companion = form.companion === c ? '' : c; touch()"
              >
                {{ c }}
              </button>
            </div>
          </section>

          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="info" :size="16" /> 当前状态</h2>
            </div>
            <ul class="state">
              <li>
                <span>保存状态</span>
                <span class="badge" :class="dirty ? 'badge--warn' : 'badge--ok'">
                  {{ dirty ? '有未保存修改' : '已同步' }}
                </span>
              </li>
              <li>
                <span>偏好记录</span>
                <span class="badge" :class="form.travel_style || form.interests ? 'badge--brand' : 'badge--muted'">
                  {{ form.travel_style || form.interests ? '已设置' : '未设置' }}
                </span>
              </li>
            </ul>
            <button class="btn btn--ghost btn--block" style="margin-top: 14px" :disabled="loading" @click="load">
              <Icon name="refresh" :size="15" /> 重新读取
            </button>
          </section>

          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="sparkle" :size="16" /> 快捷入口</h2>
            </div>
            <button class="btn btn--primary btn--block" @click="router.push('/chat')">
              <Icon name="sparkle" :size="15" /> 开始规划行程
            </button>
            <button class="btn btn--ghost btn--block" style="margin-top: 9px" @click="router.push('/budget')">
              <Icon name="wallet" :size="15" /> 预算分析
            </button>
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { height: 100%; overflow-y: auto; background: var(--paper); }

.page__inner {
  max-width: 1140px;
  margin: 0 auto;
  padding: 30px 32px 64px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 316px;
  gap: 20px;
  align-items: start;
}

.col-main, .col-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.panel { padding: 20px 22px; }

.panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 16px;
}

.panel__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: -0.012em;
}

.panel__title svg { color: var(--ink-4); }

/* 账号 */
.account {
  display: flex;
  align-items: center;
  gap: 14px;
}

.account__avatar {
  width: 46px;
  height: 46px;
  flex: none;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 18px;
  font-weight: 600;
  color: var(--accent-text);
  background: var(--accent-dim);
  border: 1px solid var(--accent-line);
}

.account__name {
  font-size: 15.5px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.account__sub {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 11px;
  color: var(--ink-4);
}

/* 选项：选中态是实心，不是发光描边。
   单选＝深墨实心（只能有一个），多选＝深青淡底（可以叠加）。 */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}

.chip {
  height: 33px;
  padding: 0 13px;
  border-radius: var(--r-sm);
  font-size: 12.5px;
  color: var(--ink-2);
  background: var(--surface);
  border: 1px solid var(--line);
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease);
}

.chip:hover { color: var(--ink); border-color: var(--line-strong); background: var(--paper); }

.chip.is-on {
  color: var(--accent-text);
  border-color: var(--accent-line);
  background: var(--accent-dim);
}

.chips--pick .chip.is-on {
  color: #FCFBF7;
  border-color: var(--ink);
  background: var(--ink);
}

/* 分段控件：单选、选项少而互斥 */
.seg {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  overflow: hidden;
  background: var(--surface);
}

.seg button {
  height: 33px;
  font-size: 12.5px;
  color: var(--ink-2);
  border-left: 1px solid var(--line);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.seg button:first-child { border-left: 0; }
.seg button:hover { color: var(--ink); background: var(--paper-2); }

.seg button.is-on {
  color: #FCFBF7;
  background: var(--ink);
}

/* 方格选择：选项多、彼此同级 */
.tiles {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.tile {
  height: 33px;
  font-size: 12.5px;
  color: var(--ink-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease);
}

.tile:hover { color: var(--ink); border-color: var(--line-strong); }

.tile.is-on {
  color: #FCFBF7;
  border-color: var(--ink);
  background: var(--ink);
}

/* 状态 */
.state {
  display: flex;
  flex-direction: column;
}

.state li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 0;
  font-size: 12.5px;
  color: var(--ink-3);
  border-bottom: 1px solid var(--line-faint);
}

.state li:last-child { border-bottom: 0; }

@media (max-width: 1000px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .page__inner { padding: 22px 18px 48px; }
}

@media (max-width: 560px) {
  .page__inner { padding: 20px 14px 40px; }
  .panel { padding: 16px; }
}
</style>
