<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '../components/Icon.vue'
import { budgetApi, chatApi, travelPlanApi } from '../api/index.js'
import { auth } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

const route = useRoute()

/* ---------------- 输入 ---------------- */
const form = reactive({
  sessionId: '',
  text: ''
})
const analyzing = ref(false)
const result = ref(null)
const savingPlan = ref(false)
const filling = ref(false) // 选会话后自动带出行程的读取状态

const sessions = ref([])
const recent = ref([])
const recentLoading = ref(false)

const SAMPLE = `从广州出发去成都玩5天，预算3000元。
第一天：广州南站乘高铁到成都，入住春熙路附近酒店，晚上逛太古里。
第二天：都江堰一日游，返回市区。
第三天：大熊猫繁育研究基地，下午逛宽窄巷子。
第四天：乐山大佛一日游。
第五天：人民公园喝茶，下午返程。`

/* ---------------- 解析 ---------------- */
const env = computed(() => {
  const raw = result.value?.envelope_json
  if (!raw) return null
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return null
  }
})

const plan = computed(() => {
  const raw = result.value?.plan_json
  if (!raw) return null
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return null
  }
})

const status = computed(() => result.value?.budget_status || 'UNKNOWN')

const statusMeta = computed(() => {
  switch (status.value) {
    case 'WITHIN_BUDGET':
      return { text: '预算内', cls: 'ok', icon: 'check' }
    case 'OVER_BUDGET':
      return { text: '超出预算', cls: 'danger', icon: 'alert' }
    default:
      return { text: '未指定预算', cls: 'muted', icon: 'info' }
  }
})

function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function money(v) {
  return `¥${num(v).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

/** 分项明细（用真实字段换算，不做任何推测） */
const breakdown = computed(() => {
  const e = env.value
  if (!e) return []
  const nights = e.nights ?? Math.max((e.days || 1) - 1, 0)
  const days = e.days || 1
  const rows = [
    { key: 'transport', label: '往返大交通', note: e.transportMode, amount: num(e.transportCost) },
    { key: 'hotel', label: '住宿', note: `${e.hotelTier || '—'} · ¥${num(e.hotelPerNight)}/晚 × ${nights}晚`, amount: num(e.hotelPerNight) * nights },
    { key: 'food', label: '餐饮', note: `${e.foodTier || '—'} · ¥${num(e.foodPerDay)}/天 × ${days}天`, amount: num(e.foodPerDay) * days },
    { key: 'local', label: '市内交通', note: `¥${num(e.localPerDay)}/天 × ${days}天`, amount: num(e.localPerDay) * days },
    { key: 'ticket', label: '门票', note: `${e.paidPoiCount ?? 0} 个收费景点`, amount: num(e.ticketTotal) },
    { key: 'other', label: '其他', note: '购物 / 纪念品等', amount: num(e.otherTotal) }
  ]
  const total = num(e.total) || rows.reduce((s, r) => s + r.amount, 0) || 1
  return rows.map((r) => ({ ...r, pct: Math.max((r.amount / total) * 100, r.amount > 0 ? 1.2 : 0) }))
})

const TIER_HINT = {
  品质: '高档酒店 / 精品民宿 · 特色餐饮',
  舒适: '舒适型连锁酒店 · 常规餐饮',
  经济: '青旅 / 经济型连锁 · 简餐为主'
}

/**
 * 档次阶梯：严格按 BudgetEnvelopeService 的级联顺序推导（品质 → 舒适 → 经济），
 * 只标注「是否被选中 / 是否回退」，不臆造未返回的金额。
 */
const LADDER = ['品质', '舒适', '经济']

const ladder = computed(() => {
  const e = env.value
  if (!e) return []
  const picked = e.level || ''
  const idx = LADDER.indexOf(picked)
  return LADDER.map((name, i) => {
    let state = 'unknown'
    if (idx === -1) state = 'unknown'
    else if (i < idx) state = 'rejected'
    else if (i === idx) state = e.feasible === false ? 'partial' : 'chosen'
    else state = 'unreached'
    return {
      name,
      state,
      total: i === idx ? num(e.total) : null,
      remaining: i === idx ? num(e.remaining) : null,
      tier: TIER_HINT[name]
    }
  })
})

/* ---------------- 费用明细与价格来源 ---------------- */
/** 费用明细条目（detail_json.items），每项携带 source/as_of/confidence 溯源字段 */
const detailItems = computed(() => {
  const raw = result.value?.detail_json
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed?.items) ? parsed.items : []
  } catch {
    return []
  }
})

/**
 * 价格来源分级（论文「数据真实性分层」的 UI 落地）：
 *   TRAIN_API  真实票价（12306 同步的聚合 API）
 *   SNAPSHOT   快照价（景点库真实票价 / 酒店价格快照表）
 *   ITINERARY  攻略载明（行程文本中写明的价格）
 *   ESTIMATE   系统估算（未取到真实价格，按行业均价估算——明确标注，不冒充真实）
 */
const SOURCE_META = {
  TRAIN_API: { text: '真实票价', cls: 'real', tip: '来自 12306 同步的第三方聚合 API（聚合数据/极速数据）' },
  SNAPSHOT: { text: '快照价', cls: 'snap', tip: '来自景点库真实票价（t_poi）或酒店价格快照表' },
  ITINERARY: { text: '攻略载明', cls: 'itin', tip: '取自行程攻略中明确写明的价格' },
  ESTIMATE: { text: '系统估算', cls: 'est', tip: '未取到真实价格，按行业均价估算' }
}
function sourceMeta(s) {
  return SOURCE_META[s] || SOURCE_META.ESTIMATE
}
function catKey(c) {
  return { 交通: 'transport', 住宿: 'hotel', 餐饮: 'food', 门票: 'ticket', 其他: 'other' }[c] || 'other'
}

/** 保存为旅行计划（行程持久化） */
async function savePlan() {
  const sid = form.sessionId.trim()
  if (!sid) {
    toast.warn('请先选择会话')
    return
  }
  savingPlan.value = true
  try {
    const plan = await travelPlanApi.saveFromSession(sid)
    toast.success(`已保存为行程：${plan.title || plan.plan_id}`)
  } catch (e) {
    toast.error(errText(e, '保存行程失败'))
  } finally {
    savingPlan.value = false
  }
}

/* ---------------- 操作 ---------------- */
async function analyze() {
  const sid = form.sessionId.trim()
  if (!sid) {
    toast.warn('请先选择会话')
    return
  }
  if (!form.text.trim()) {
    toast.warn('请粘贴或输入行程内容')
    return
  }
  analyzing.value = true
  try {
    result.value = await budgetApi.analyze(sid, form.text)
    const s = status.value
    if (s === 'WITHIN_BUDGET') toast.success('分析完成：在预算范围内')
    else if (s === 'OVER_BUDGET') toast.warn('分析完成：当前方案超出预算')
    else toast.info('分析完成：行程中未检测到预算金额')
    await loadRecent()
  } catch (e) {
    toast.error(errText(e, '预算分析失败'))
  } finally {
    analyzing.value = false
  }
}

async function loadSessions() {
  try {
    const d = await chatApi.sessionList({ page: 1, pageSize: 30, userId: auth.userId.value })
    sessions.value = d.session_list || []
  } catch {
    sessions.value = []
  }
}

async function loadRecent() {
  recentLoading.value = true
  try {
    const d = await budgetApi.recent(8)
    recent.value = d?.list || d?.records || (Array.isArray(d) ? d : [])
  } catch {
    recent.value = []
  } finally {
    recentLoading.value = false
  }
}

async function loadBySession(sid) {
  form.sessionId = sid
  try {
    const r = await budgetApi.bySession(sid)
    if (r) {
      result.value = r
      toast.info('已载入该会话的历史分析结果')
    }
  } catch {
    /* 无历史结果属正常情况 */
  }
}

/**
 * 取某会话的「可分析文本」：最后一条 AI 行程 + 该行程之前最近一条用户需求。
 *
 * 关键：AI 行程正文通常**不会重复写出发地与预算**（那是用户原始需求里说的），
 * 只把行程文本丢给预算引擎会导致「出发地丢失 → 大交通算成一百多块」、
 * 「预算丢失 → 只能用会话表里的历史残留值」两类严重偏差。
 * 因此拼接后再送分析，让引擎能同时识别出发地、目的地、天数、预算与景点。
 *
 * @returns {{ text: string, found: boolean }} found=false 表示没取到 AI 行程
 */
async function buildItineraryText(sid) {
  let itinerary = ''
  let userNeed = ''
  let fallbackText = ''
  try {
    const d = await chatApi.history(sid)
    const list = d?.history_list || []
    // 优先取最后一条「有实质内容」的 assistant 消息
    let hitIndex = -1
    for (let i = list.length - 1; i >= 0; i--) {
      const m = list[i] || {}
      const isUser = String(m.role || '').toLowerCase() === 'user'
      const content = String(m.content || '').trim()
      if (!content) continue
      if (!isUser && content.length >= 40) {
        itinerary = content
        hitIndex = i
        break
      }
      if (!fallbackText) fallbackText = content
    }
    // 回溯该行程之前最近的一条用户消息（出发地/预算只出现在这里）
    if (hitIndex > 0) {
      for (let i = hitIndex - 1; i >= 0; i--) {
        const m = list[i] || {}
        const isUser = String(m.role || '').toLowerCase() === 'user'
        const content = String(m.content || '').trim()
        if (isUser && content) {
          userNeed = content
          break
        }
      }
    }
  } catch {
    /* 历史拉取失败按无行程处理 */
  }

  if (!itinerary) {
    return { text: fallbackText || '', found: false }
  }
  // 拼接格式与后端解析习惯保持一致：需求在前、行程在后，两段都保留原文
  return {
    text: userNeed ? `【我的需求】\n${userNeed}\n\n【AI 生成的行程】\n${itinerary}` : itinerary,
    found: true
  }
}

/** 手动选择会话：自动把该会话的行程带进文本框（不自动分析，交由用户点「开始分析」） */
async function onSessionChange() {
  const sid = form.sessionId
  if (!sid) {
    form.text = ''
    return
  }
  filling.value = true
  try {
    const { text, found } = await buildItineraryText(sid)
    form.text = text
    if (!found) toast.warn('该会话暂无 AI 生成的行程，可手动粘贴后再分析')
  } catch {
    toast.warn('读取该会话行程失败，可手动粘贴')
  } finally {
    filling.value = false
  }
}

/**
 * 从「智能规划」跳转过来时：自动取该会话最后一条 AI 行程作为输入并立即分析。
 * 取不到行程文本时降级为载入历史分析结果，不让用户面对空白表单。
 */
async function autoAnalyzeFromSession(sid) {
  form.sessionId = sid
  const { text, found } = await buildItineraryText(sid)

  if (!found) {
    form.text = text || ''
    await loadBySession(sid)
    toast.warn('未取到该会话的行程内容，已载入历史结果或请手动粘贴')
    return
  }

  form.text = text
  await analyze()
}

function reset() {
  result.value = null
  form.text = ''
}

onMounted(async () => {
  await Promise.all([loadSessions(), loadRecent()])
  const from = route.query.from
  if (from) {
    // auto=1（从智能规划「分析预算」进入）：自动带入行程并直接开始分析
    if (route.query.auto === '1') await autoAnalyzeFromSession(String(from))
    else await loadBySession(String(from))
  }
})

watch(
  () => route.query.from,
  (v) => {
    if (!v) return
    if (route.query.auto === '1') autoAnalyzeFromSession(String(v))
    else loadBySession(String(v))
  }
)
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">
            预算分析
            <span class="badge badge--brand" style="margin-left: 10px; vertical-align: 4px">论文核心模块</span>
          </h1>
          <p class="page-head__sub">
            预算硬约束：给定预算后反推消费档次，超支时按「品质 → 舒适 → 经济」逐级回退，只压不抬
          </p>
        </div>
      </header>

      <div class="layout">
        <!-- ============ 左：输入 + 结果 ============ -->
        <div class="col-main">
          <section class="card card--solid card--lit panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="edit" :size="16" /> 行程内容</h2>
              <button class="btn btn--quiet btn--sm" @click="form.text = SAMPLE">
                <Icon name="book" :size="14" /> 填入示例
              </button>
            </div>

            <div class="field" style="margin-bottom: 14px">
              <label class="field__label">
                选择会话
                <span class="t3">— 选中后自动带出该会话的行程内容</span>
              </label>
              <select v-model="form.sessionId" class="select" :disabled="filling" @change="onSessionChange">
                <option value="">— 请选择 —</option>
                <option v-for="s in sessions" :key="s.session_id" :value="s.session_id">
                  {{ s.title || '未命名会话' }}
                </option>
              </select>
            </div>

            <div class="field">
              <label class="field__label">
                行程文本
                <span v-if="filling" class="t3">— 正在读取该会话行程…</span>
                <span v-else class="t3">— 预算写在文本里即可识别，例如「预算3000元」</span>
              </label>
              <textarea
                v-model="form.text"
                class="textarea"
                rows="8"
                placeholder="粘贴 AI 生成的行程，或手写一段行程描述…"
              />
            </div>

            <div class="panel__foot">
              <span class="t3" style="font-size: 12.5px">共 {{ form.text.length }} 字</span>
              <div style="display: flex; gap: 10px">
                <button v-if="result" class="btn btn--ghost" @click="reset">清空结果</button>
                <button v-if="result" class="btn btn--ghost" :disabled="savingPlan" @click="savePlan">
                  <Icon name="route" :size="14" /> {{ savingPlan ? '保存中…' : '保存为行程' }}
                </button>
                <button class="btn btn--primary" :disabled="analyzing" @click="analyze">
                  <span v-if="analyzing" class="spinner" />
                  <Icon v-else name="sparkle" :size="15" />
                  {{ analyzing ? '分析中…' : '开始分析' }}
                </button>
              </div>
            </div>
          </section>

          <Transition name="fade">
            <section v-if="result" class="result">
              <div class="card card--solid hero-card">
                <div class="hero-card__top">
                  <div>
                    <div class="hero-card__label">预算达成状态</div>
                    <div class="hero-card__status" :class="`is-${statusMeta.cls}`">
                      <Icon :name="statusMeta.icon" :size="19" />
                      {{ statusMeta.text }}
                    </div>
                  </div>
                  <span v-if="env?.level" class="badge badge--brand" style="height: 27px; font-size: 12.5px">
                    档次：{{ env.level }}
                  </span>
                </div>

                <div class="hero-card__figures">
                  <div class="fig">
                    <div class="fig__k">用户预算</div>
                    <div class="fig__v">{{ env?.userBudget != null ? money(env.userBudget) : '未指定' }}</div>
                  </div>
                  <div class="fig__sep" />
                  <div class="fig">
                    <div class="fig__k">封套合计</div>
                    <div class="fig__v">{{ money(env?.total ?? result.total_budget) }}</div>
                  </div>
                  <div class="fig__sep" />
                  <div class="fig">
                    <div class="fig__k">结余</div>
                    <div
                      class="fig__v"
                      :class="num(env?.remaining ?? result.remaining_budget) < 0 ? 'is-neg' : 'is-pos'"
                    >
                      {{ money(env?.remaining ?? result.remaining_budget) }}
                    </div>
                  </div>
                  <div class="fig__sep" />
                  <div class="fig">
                    <div class="fig__k">行程天数</div>
                    <div class="fig__v">{{ env?.days ?? result.days }} 天</div>
                  </div>
                </div>

                <div v-if="env?.userBudget" class="gauge">
                  <div class="gauge__track">
                    <div
                      class="gauge__fill"
                      :class="{ 'is-over': num(env.total) > num(env.userBudget) }"
                      :style="{ width: Math.min((num(env.total) / num(env.userBudget)) * 100, 100) + '%' }"
                    />
                  </div>
                  <div class="gauge__legend">
                    <span>预算占用 {{ Math.round((num(env.total) / num(env.userBudget)) * 100) }}%</span>
                    <span v-if="env.minBudget">该天数最低可行预算 {{ money(env.minBudget) }}</span>
                  </div>
                </div>
              </div>

              <div class="card card--solid panel">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="layers" :size="16" /> 档次阶梯回退</h2>
                  <span class="t3" style="font-size: 12.5px">自顶向下试算，取第一个不超预算的档次</span>
                </div>

                <ol class="ladder">
                  <li v-for="(r, i) in ladder" :key="r.name" class="rung" :class="`rung--${r.state}`">
                    <div class="rung__line">
                      <span class="rung__dot" />
                      <span v-if="i < ladder.length - 1" class="rung__bar" />
                    </div>
                    <div class="rung__body">
                      <div class="rung__head">
                        <span class="rung__name">{{ r.name }}档</span>
                        <span v-if="r.state === 'chosen'" class="badge badge--ok">
                          <Icon name="check" :size="11" /> 采用
                        </span>
                        <span v-else-if="r.state === 'partial'" class="badge badge--warn">
                          <Icon name="alert" :size="11" /> 降级采用
                        </span>
                        <span v-else-if="r.state === 'rejected'" class="badge badge--danger">
                          <Icon name="close" :size="11" /> 超预算 · 回退
                        </span>
                        <span v-else-if="r.state === 'unreached'" class="badge badge--muted">未试算</span>
                        <span v-else class="badge badge--muted">未知</span>
                      </div>
                      <div class="rung__desc">{{ r.tier }}</div>
                      <div v-if="r.total !== null" class="rung__figures">
                        <span>合计 <strong>{{ money(r.total) }}</strong></span>
                        <span>结余 <strong>{{ money(r.remaining) }}</strong></span>
                      </div>
                    </div>
                  </li>
                </ol>
              </div>

              <div class="card card--solid panel">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="coins" :size="16" /> 费用封套分项</h2>
                  <span class="t3" style="font-size: 12.5px">各分项上限由所选档次决定</span>
                </div>

                <ul class="breakdown">
                  <li v-for="b in breakdown" :key="b.key" class="bd">
                    <div class="bd__row">
                      <span class="bd__label">{{ b.label }}</span>
                      <span class="bd__amount">{{ money(b.amount) }}</span>
                    </div>
                    <div class="bd__track">
                      <div class="bd__fill" :style="{ width: b.pct + '%' }" />
                    </div>
                    <div class="bd__note">{{ b.note }}</div>
                  </li>
                </ul>

                <div class="bd__total">
                  <span>封套合计</span>
                  <strong>{{ money(env?.total ?? result.total_budget) }}</strong>
                </div>
              </div>

              <!-- ============ 费用明细与价格来源（数据真实性分层） ============ -->
              <div v-if="detailItems.length" class="card card--solid panel">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="coins" :size="16" /> 费用明细与价格来源</h2>
                  <span class="t3" style="font-size: 12.5px">每项价格均可溯源，拿不到真实价格会标注「系统估算」</span>
                </div>

                <ul class="items">
                  <li v-for="(it, i) in detailItems" :key="i" class="item">
                    <span class="item__cat" :class="`item__cat--${catKey(it.category)}`">{{ it.category }}</span>
                    <div class="item__body">
                      <div class="item__name truncate">{{ it.name }}</div>
                      <div class="item__meta">
                        <span class="src" :class="`src--${sourceMeta(it.source).cls}`" :title="sourceMeta(it.source).tip">
                          {{ sourceMeta(it.source).text }}
                        </span>
                        <span v-if="it.as_of" class="item__date">{{ it.as_of }}</span>
                      </div>
                    </div>
                    <span class="item__amount">{{ money(it.amount) }}</span>
                  </li>
                </ul>

                <div class="items__total">
                  <span>明细合计</span>
                  <strong>{{ money(result.total_budget) }}</strong>
                </div>
              </div>

              <div v-if="env?.adjustments?.length" class="card card--solid panel panel--accent">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="refresh" :size="16" /> 降级与调整记录</h2>
                  <span class="badge badge--warn">{{ env.adjustments.length }} 项</span>
                </div>
                <ul class="adj">
                  <li v-for="(a, i) in env.adjustments" :key="i">
                    <Icon name="arrowLeft" :size="14" />
                    <span>{{ a }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="env?.suggestions?.length" class="card card--solid panel">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="info" :size="16" /> 规划建议</h2>
                </div>
                <ul class="sugg">
                  <li v-for="(s, i) in env.suggestions" :key="i">
                    <span class="sugg__i">{{ i + 1 }}</span>
                    <span>{{ s }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="plan" class="card card--solid panel">
                <div class="panel__head">
                  <h2 class="panel__title"><Icon name="route" :size="16" /> 预算内出行方案</h2>
                </div>
                <div class="plan">
                  <div v-for="(v, k) in plan" :key="k" class="plan__item">
                    <span class="plan__k">{{ k }}</span>
                    <span class="plan__v">{{ typeof v === 'object' ? JSON.stringify(v) : v }}</span>
                  </div>
                </div>
              </div>
            </section>
          </Transition>

          <div v-if="!result" class="card panel empty">
            <div class="empty__icon"><Icon name="wallet" :size="27" /></div>
            <div class="empty__title">还没有分析结果</div>
            <p class="empty__desc">
              选择会话并粘贴行程文本，点击「开始分析」。若行程中写明预算（如「预算3000元」），
              系统会反推消费档次，并在超支时自动逐级回退。
            </p>
          </div>
        </div>

        <!-- ============ 右：最近分析 ============ -->
        <aside class="col-side">
          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="clock" :size="16" /> 最近分析</h2>
              <button class="btn btn--quiet btn--sm" :disabled="recentLoading" @click="loadRecent">
                <Icon name="refresh" :size="14" />
              </button>
            </div>

            <div v-if="recentLoading" class="side-skel">
              <div v-for="i in 3" :key="i" class="skeleton" style="height: 46px" />
            </div>

            <div v-else-if="!recent.length" class="t3" style="font-size: 12.8px; padding: 8px 2px">
              暂无历史记录
            </div>

            <ul v-else class="recent">
              <li v-for="(r, i) in recent" :key="r.id || i" class="recent__item" @click="loadBySession(r.session_id)">
                <div class="recent__row">
                  <span class="mono truncate" style="font-size: 11.5px">{{ (r.session_id || '').slice(0, 10) }}</span>
                  <span
                    class="badge"
                    :class="r.budget_status === 'WITHIN_BUDGET' ? 'badge--ok' : r.budget_status === 'OVER_BUDGET' ? 'badge--danger' : 'badge--muted'"
                  >
                    {{ r.budget_status === 'WITHIN_BUDGET' ? '预算内' : r.budget_status === 'OVER_BUDGET' ? '超支' : '未指定' }}
                  </span>
                </div>
                <div class="recent__figs">
                  <span>预算 {{ r.user_budget != null ? money(r.user_budget) : '—' }}</span>
                  <span>合计 {{ money(r.total_budget) }}</span>
                </div>
              </li>
            </ul>
          </section>

          <section class="card card--solid panel">
            <div class="panel__head">
              <h2 class="panel__title"><Icon name="info" :size="16" /> 关于预算来源</h2>
            </div>
            <p class="tip__p">
              系统优先读取会话表已落库的预算金额；若为空，则从行程文本中正则提取
              （支持「预算3000元」「预算四千元」等写法）。
            </p>
            <p class="tip__p">
              因此行程文本里没有写明预算时，状态显示为「未指定」属于预期行为，不是故障。
            </p>
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  overflow-y: auto;
}

.page__inner {
  max-width: 1380px;
  margin: 0 auto;
  padding: 30px 32px 56px;
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
  gap: 18px;
  min-width: 0;
}

.panel { padding: 20px 22px; }

.panel--accent {
  border-color: rgba(251, 191, 36, 0.28);
  background: linear-gradient(180deg, rgba(251, 191, 36, 0.055), rgba(255, 255, 255, 0.02));
}

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
  gap: 9px;
  font-size: 14.5px;
  font-weight: 650;
}

.panel__title svg { color: var(--cyan); }

.panel__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 16px;
}

/* ---------------- 结果总览 ---------------- */
.hero-card { padding: 22px 24px; }

.hero-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.hero-card__label {
  font-size: 12.5px;
  color: var(--t3);
  margin-bottom: 6px;
}

.hero-card__status {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 25px;
  font-weight: 730;
  letter-spacing: -0.6px;
}

.hero-card__status.is-ok { color: var(--ok); }
.hero-card__status.is-danger { color: var(--danger); }
.hero-card__status.is-muted { color: var(--t2); }

.hero-card__figures {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.fig { flex: 1; min-width: 108px; }

.fig__k {
  font-size: 12px;
  color: var(--t3);
  margin-bottom: 4px;
}

.fig__v {
  font-size: 19px;
  font-weight: 680;
  letter-spacing: -0.4px;
  font-variant-numeric: tabular-nums;
}

.fig__v.is-pos { color: var(--ok); }
.fig__v.is-neg { color: var(--danger); }

.fig__sep {
  width: 1px;
  height: 34px;
  background: var(--line);
  flex: none;
}

.gauge { margin-top: 22px; }

.gauge__track {
  position: relative;
  height: 9px;
  border-radius: var(--r-full);
  background: rgba(255, 255, 255, 0.07);
  overflow: hidden;
}

.gauge__fill {
  height: 100%;
  border-radius: var(--r-full);
  background: var(--grad-brand);
  transition: width 0.7s var(--ease-out);
}

.gauge__fill.is-over {
  background: linear-gradient(90deg, #FBBF24, #F87171);
}

.gauge__legend {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--t3);
}

/* ---------------- 档次阶梯 ---------------- */
.ladder { display: flex; flex-direction: column; }

.rung { display: flex; gap: 14px; }

.rung__line {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 16px;
  flex: none;
}

.rung__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-top: 7px;
  flex: none;
  border: 2px solid var(--t4);
  background: var(--bg-base);
  z-index: 1;
}

.rung__bar {
  flex: 1;
  width: 2px;
  background: var(--line);
  margin: 3px 0 -3px;
}

.rung--chosen .rung__dot {
  border-color: var(--ok);
  background: var(--ok);
  box-shadow: 0 0 0 4px rgba(52, 211, 153, 0.18);
}

.rung--partial .rung__dot {
  border-color: var(--warn);
  background: var(--warn);
  box-shadow: 0 0 0 4px rgba(251, 191, 36, 0.18);
}

.rung--rejected .rung__dot {
  border-color: var(--danger);
  background: transparent;
}

.rung__body {
  flex: 1;
  min-width: 0;
  padding: 3px 0 18px;
}

.rung__head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.rung__name {
  font-size: 14.5px;
  font-weight: 650;
}

.rung--rejected .rung__name,
.rung--unreached .rung__name { color: var(--t3); }

.rung__desc {
  margin-top: 3px;
  font-size: 12.5px;
  color: var(--t3);
}

.rung__figures {
  display: flex;
  gap: 18px;
  margin-top: 7px;
  font-size: 13px;
  color: var(--t2);
}

.rung__figures strong { color: var(--t1); font-variant-numeric: tabular-nums; }

/* ---------------- 分项 ---------------- */
.breakdown {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.bd__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
}

.bd__label { font-size: 13.5px; font-weight: 550; }

.bd__amount {
  font-size: 14px;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}

.bd__track {
  height: 6px;
  border-radius: var(--r-full);
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.bd__fill {
  height: 100%;
  border-radius: var(--r-full);
  background: linear-gradient(90deg, rgba(34, 211, 238, 0.9), rgba(99, 102, 241, 0.9));
  transition: width 0.6s var(--ease-out);
}

.bd__note {
  margin-top: 5px;
  font-size: 11.8px;
  color: var(--t4);
}

.bd__total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
  padding-top: 15px;
  border-top: 1px solid var(--line);
  font-size: 13.5px;
  color: var(--t2);
}

.bd__total strong {
  font-size: 19px;
  font-weight: 700;
  color: var(--t1);
  font-variant-numeric: tabular-nums;
}

/* ---------------- 降级 / 建议 / 方案 ---------------- */
.adj, .sugg {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.adj li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13.3px;
  color: #FCD34D;
  line-height: 1.6;
}

.adj svg { margin-top: 3px; flex: none; }

.sugg li {
  display: flex;
  gap: 11px;
  font-size: 13.3px;
  color: var(--t2);
  line-height: 1.65;
}

.sugg__i {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  flex: none;
  margin-top: 2px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  color: #CFFAFE;
  background: rgba(34, 211, 238, 0.14);
  border: 1px solid rgba(34, 211, 238, 0.3);
}

.plan {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 10px;
}

.plan__item {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: rgba(255, 255, 255, 0.028);
  border: 1px solid var(--line);
}

.plan__k { font-size: 11.5px; color: var(--t4); }

.plan__v {
  font-size: 13px;
  color: var(--t1);
  word-break: break-word;
}

/* ---------------- 侧栏 ---------------- */
.recent {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.recent__item {
  padding: 10px 12px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.022);
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.recent__item:hover {
  border-color: var(--line-strong);
  background: var(--glass-hover);
}

.recent__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.recent__figs {
  display: flex;
  gap: 14px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--t3);
}

.side-skel { display: flex; flex-direction: column; gap: 8px; }

.tip__p {
  font-size: 12.8px;
  line-height: 1.72;
  color: var(--t3);
}

.tip__p + .tip__p { margin-top: 10px; }

.fade-enter-active { transition: opacity 0.3s var(--ease), transform 0.3s var(--ease-out); }
.fade-enter-from { opacity: 0; transform: translateY(10px); }

/* ---------------- 费用明细与价格来源 ---------------- */
.items {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 10px;
  border-radius: var(--r-sm);
  transition: background var(--dur) var(--ease);
}

.item:hover { background: var(--glass-hover); }

.item__cat {
  flex: none;
  width: 44px;
  text-align: center;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 0;
  border-radius: var(--r-xs);
  border: 1px solid var(--line);
  color: var(--t2);
  background: var(--glass);
}

.item__cat--transport { color: #A5F3FC; border-color: rgba(34, 211, 238, 0.3); background: rgba(34, 211, 238, 0.08); }
.item__cat--hotel { color: #D8B4FE; border-color: rgba(168, 85, 247, 0.3); background: rgba(168, 85, 247, 0.08); }
.item__cat--food { color: #FCD34D; border-color: rgba(251, 191, 36, 0.28); background: rgba(251, 191, 36, 0.07); }
.item__cat--ticket { color: #6EE7B7; border-color: rgba(52, 211, 153, 0.3); background: rgba(52, 211, 153, 0.07); }
.item__cat--other { color: var(--t2); }

.item__body { flex: 1; min-width: 0; }

.item__name { font-size: 13.2px; color: var(--t1); }

.item__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
}

.item__date { font-size: 11px; color: var(--t4); font-family: var(--font-mono); }

/* 价格来源徽标：真实/快照/攻略载明/估算 四级 */
.src {
  display: inline-flex;
  align-items: center;
  height: 19px;
  padding: 0 8px;
  border-radius: var(--r-full);
  font-size: 11px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: help;
}

.src--real { color: #6EE7B7; background: rgba(52, 211, 153, 0.12); border-color: rgba(52, 211, 153, 0.35); }
.src--snap { color: #A5F3FC; background: rgba(34, 211, 238, 0.12); border-color: rgba(34, 211, 238, 0.35); }
.src--itin { color: #D8B4FE; background: rgba(168, 85, 247, 0.12); border-color: rgba(168, 85, 247, 0.32); }
.src--est { color: var(--t4); background: rgba(255, 255, 255, 0.05); border-color: var(--line); }

.item__amount {
  flex: none;
  font-size: 13.6px;
  font-weight: 650;
  color: var(--t1);
  font-family: var(--font-mono);
}

.items__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-top: 10px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
  font-size: 13px;
  color: var(--t3);
}

.items__total strong {
  font-size: 16px;
  color: var(--t1);
  font-family: var(--font-mono);
}

@media (max-width: 1100px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .page__inner { padding: 22px 18px 44px; }
}
</style>
