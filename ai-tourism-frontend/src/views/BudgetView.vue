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

/** 后端返回的 plan 字段是驼峰英文，展示前统一转成中文（未知字段原样保留） */
const PLAN_LABELS = {
  userBudget: '用户预算',
  level: '出行档次',
  transportMode: '交通方式',
  transportDuration: '交通时长',
  transportDurationSource: '时长来源',
  transportMinutesOneWay: '单程分钟数',
  hotelTier: '住宿标准',
  foodTier: '餐饮标准',
  total: '合计',
  remaining: '结余',
  days: '行程天数',
  nights: '住宿晚数',
  feasible: '是否可行',
  minBudget: '最低可行预算',
  budgetStatus: '预算状态',
  summary: '方案摘要',
  tips: '提示'
}

function planLabel(k) {
  return PLAN_LABELS[k] || k
}

/** 后端值 → 中文展示：来源码、布尔、状态这类枚举不直接给用户看英文 */
const PLAN_VALUES = {
  transportDurationSource: { TRAIN_REAL: '12306 实爬车次历时', ESTIMATE: '速度模型估算' },
  budgetStatus: {
    WITHIN_BUDGET: '预算内',
    OVER_BUDGET: '超出预算',
    UNKNOWN: '未指定预算'
  }
}

function planValue(k, v) {
  if (typeof v === 'boolean') return v ? '是' : '否'
  const map = PLAN_VALUES[k]
  if (map && map[v] !== undefined) return map[v]
  if (v === null || v === undefined || v === '') return '—'
  return typeof v === 'object' ? JSON.stringify(v) : v
}

function num(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function money(v) {
  return `¥${num(v).toLocaleString('zh-CN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

/** 分钟 → 「7 小时 2 分」（与后端 TransportDuration.human 同口径） */
function humanMin(m) {
  const v = Math.max(Math.round(Number(m) || 0), 0)
  if (!v) return '—'
  if (v < 60) return `${v} 分钟`
  const h = Math.floor(v / 60)
  const rest = v % 60
  return rest ? `${h} 小时 ${rest} 分` : `${h} 小时`
}

/**
 * 大交通时长：与「按预算选出的交通方式」绑定展示。
 * 真实来源是 12306 实爬车次历时，估算来源是速度模型，两者必须让用户分得清。
 */
const transportDuration = computed(() => {
  const e = env.value
  if (!e) return null
  const d = e.transportDuration || {}
  const mins = Number(d.minutesOneWay || 0)
  if (!mins && !e.transportDurationText) return null
  const real = e.transportDurationSource === 'TRAIN_REAL'
  return {
    minutes: mins,
    kind: d.kind || '',
    text: e.transportDurationText || `单程约 ${humanMin(mins)} · 往返在途约 ${humanMin(mins * 2)}`,
    oneWay: d.minutesOneWay ? `单程约 ${humanMin(mins)}` : '',
    cls: real ? 'src--real' : 'src--est',
    label: real ? '12306 实爬车次历时' : '速度模型估算',
    train: d.trainCode ? `${d.trainCode} ${d.depart || ''}→${d.arrive || ''}`.trim() : ''
  }
})

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
          <h1 class="page-head__title">预算分析</h1>
          <p class="page-head__sub">
            给定预算后反推消费档次，超支时按「品质 → 舒适 → 经济」逐级回退，只压不抬。
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
              <div class="panel verdict">
                <div class="verdict__top">
                  <div class="verdict__status" :class="`is-${statusMeta.cls}`">
                    <Icon :name="statusMeta.icon" :size="16" />
                    {{ statusMeta.text }}
                  </div>
                  <span v-if="env?.level" class="verdict__level">采用 {{ env.level }} 档</span>
                </div>

                <!-- 大交通：多少钱 → 多长时间。省下的票价是用在途时间换来的，必须同时可见 -->
                <div v-if="transportDuration" class="verdict__route">
                  <span class="route__mode">{{ env?.transportMode || '—' }}</span>
                  <span class="route__dur">{{ transportDuration.text }}</span>
                  <span class="src" :class="transportDuration.cls" :title="transportDuration.label">
                    {{ transportDuration.label }}
                  </span>
                  <span v-if="transportDuration.train" class="route__train mono">
                    {{ transportDuration.train }}
                  </span>
                </div>

                <div class="verdict__figs">
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
                    <span class="plan__k">{{ planLabel(k) }}</span>
                    <span class="plan__v">{{ planValue(k, v) }}</span>
                  </div>
                </div>
              </div>
            </section>
          </Transition>

          <div v-if="!result" class="card panel empty">
            <div class="empty__icon"><Icon name="wallet" :size="22" /></div>
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
  background: var(--paper);
}

.page__inner {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 30px 32px 64px;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}

.col-main,
.col-side {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.col-side { position: sticky; top: 0; }

/* ---------------- 结论区 ----------------
   不套 hero 大数字模板：状态先行，四个数字横排，靠线和字重分层 */
.verdict__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.verdict__status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.028em;
  line-height: 1.2;
}

.verdict__status.is-ok { color: var(--ok); }
.verdict__status.is-danger { color: var(--danger); }
.verdict__status.is-muted { color: var(--ink-3); }

.verdict__level {
  font-size: 11.5px;
  color: var(--ink-3);
  padding: 3px 9px;
  border-radius: 3px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  letter-spacing: 0.02em;
}

.verdict__figs {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line-faint);
}

/* 大交通一行：方式 + 时长 + 来源，把「钱 → 时间」的取舍放在结论区最前面 */
.verdict__route {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: var(--r-sm);
  background: var(--paper-2);
  border: 1px solid var(--line-faint);
}

.route__mode {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.route__dur {
  font-size: 13px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

.route__train {
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0;
}

.fig { min-width: 0; }

.fig__k {
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.02em;
}

.fig__v {
  margin-top: 3px;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--ink);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  line-height: 1.25;
}

.fig__v.is-neg { color: var(--danger); }
.fig__v.is-pos { color: var(--ok); }

.fig__sep { display: none; }

/* 占用条 */
.gauge { margin-top: 18px; }

.gauge__track {
  height: 5px;
  border-radius: 3px;
  background: var(--paper-3);
  overflow: hidden;
}

.gauge__fill {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  transition: width 0.6s var(--ease-out);
}

.gauge__fill.is-over { background: var(--danger); }

.gauge__legend {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 11.5px;
  color: var(--ink-4);
  font-variant-numeric: tabular-nums;
}

/* ---------------- 档次阶梯：时间轴 ---------------- */
.ladder { display: flex; flex-direction: column; }

.rung {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 12px;
  padding-bottom: 18px;
}

.rung:last-child { padding-bottom: 0; }

.rung__line {
  position: relative;
  display: flex;
  justify-content: center;
  padding-top: 3px;
}

.rung__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--surface);
  border: 1.5px solid var(--line-strong);
  flex: none;
  z-index: 1;
}

.rung__bar {
  position: absolute;
  top: 16px;
  bottom: -18px;
  width: 1px;
  background: var(--line);
}

.rung__body { min-width: 0; }

.rung__head {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.rung__name {
  font-size: 13.5px;
  font-weight: 550;
  color: var(--ink);
}

.rung__desc {
  margin-top: 3px;
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.6;
}

.rung__figures {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--ink-4);
  font-variant-numeric: tabular-nums;
}

.rung__figures strong { color: var(--ink); font-weight: 550; }

.rung--chosen .rung__dot {
  background: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}

.rung--chosen .rung__name { color: var(--accent-text); }

.rung--partial .rung__dot { border-color: var(--warn); background: var(--warn); }

.rung--rejected .rung__dot { border-color: var(--line-strong); background: var(--paper-3); }
.rung--rejected .rung__name { color: var(--ink-3); }
.rung--rejected .rung__desc { color: var(--ink-4); }

.rung--unreached { opacity: 0.55; }

/* ---------------- 费用封套分项 ---------------- */
.breakdown { display: flex; flex-direction: column; gap: 16px; }

.bd__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.bd__label { font-size: 12.5px; color: var(--ink-2); }

.bd__amount {
  font-size: 13px;
  font-weight: 550;
  color: var(--ink);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.bd__track {
  height: 5px;
  border-radius: 3px;
  background: var(--paper-3);
  overflow: hidden;
}

.bd__fill {
  height: 100%;
  border-radius: 3px;
  background: var(--accent);
  opacity: 0.85;
  transition: width 0.6s var(--ease-out);
}

.bd__note {
  margin-top: 5px;
  font-size: 11px;
  color: var(--ink-4);
  line-height: 1.55;
}

.bd__total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line-faint);
  font-size: 12px;
  color: var(--ink-3);
}

.bd__total strong {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

/* ---------------- 费用明细 ---------------- */
.items { display: flex; flex-direction: column; }

.item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--line-faint);
}

.item:last-child { border-bottom: 0; }
.item:hover { background: rgba(23, 22, 15, 0.015); }

.item__cat {
  flex: none;
  width: 46px;
  text-align: center;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 0;
  border-radius: 3px;
  border: 1px solid var(--line);
  color: var(--ink-2);
  background: var(--paper-2);
}

.item__body { flex: 1; min-width: 0; }
.item__name { font-size: 13px; color: var(--ink); }

.item__meta { display: flex; align-items: center; gap: 8px; margin-top: 3px; }

.item__date {
  font-size: 10.5px;
  color: var(--ink-4);
  font-family: var(--font-mono);
}

.src {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: help;
}

.src--real { color: var(--ok); background: var(--ok-dim); border-color: var(--ok-line); }
.src--snap { color: var(--accent-text); background: var(--accent-dim); border-color: var(--accent-line); }
.src--itin { color: var(--info); background: var(--info-dim); border-color: var(--info-line); }
.src--est { color: var(--ink-3); background: var(--paper-2); border-color: var(--line); }

.item__amount {
  flex: none;
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

.items__total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line-faint);
  font-size: 12px;
  color: var(--ink-3);
}

.items__total strong {
  font-family: var(--font-mono);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

/* ---------------- 调整记录 / 建议 ---------------- */
.panel--accent {
  background: var(--paper);
}

.adj { display: flex; flex-direction: column; gap: 9px; }

.adj li {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  font-size: 12.5px;
  color: var(--ink-2);
  line-height: 1.65;
}

.adj svg { color: var(--warn); margin-top: 2px; flex: none; }

.sugg { display: flex; flex-direction: column; gap: 11px; }

.sugg li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 12.8px;
  color: var(--ink-2);
  line-height: 1.7;
}

.sugg__i {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  flex: none;
  margin-top: 2px;
  border-radius: 3px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
}

/* ---------------- 出行方案 ---------------- */
.plan { display: flex; flex-direction: column; }

.plan__item {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 14px;
  padding: 9px 0;
  border-bottom: 1px solid var(--line-faint);
  font-size: 12.5px;
}

.plan__item:last-child { border-bottom: 0; }
.plan__k { color: var(--ink-4); }
.plan__v { color: var(--ink); line-height: 1.65; }

/* ---------------- 右侧最近分析 ---------------- */
.recent { display: flex; flex-direction: column; }

.recent__item {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 11px 8px;
  border-radius: var(--r-sm);
  cursor: pointer;
  border-bottom: 1px solid var(--line-faint);
  transition: background var(--dur) var(--ease);
}

.recent__item:last-child { border-bottom: 0; }
.recent__item:hover { background: var(--paper); }

.recent__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.recent__figs {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--ink-4);
  font-variant-numeric: tabular-nums;
}

.side-skel { display: flex; flex-direction: column; gap: 8px; }

.tip__p {
  font-size: 12.3px;
  line-height: 1.75;
  color: var(--ink-3);
}

.tip__p + .tip__p { margin-top: 10px; }

/* ---------------- 响应式 ---------------- */
@media (max-width: 1080px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .col-side { position: static; }
  .page__inner { padding: 22px 18px 48px; }
}

@media (max-width: 620px) {
  .verdict__figs { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
  .fig__v { font-size: 18px; }
  .verdict__status { font-size: 18px; }
  .panel { padding: 18px 16px; }
  .plan__item { grid-template-columns: 1fr; gap: 2px; }
}
</style>
