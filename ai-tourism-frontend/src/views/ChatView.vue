<script setup>
import { ref, reactive, computed, nextTick, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import MdView from '../components/MdView.vue'
import Modal from '../components/Modal.vue'
import RouteMap from '../components/RouteMap.vue'
import { chatApi, travelPlanApi } from '../api/index.js'
import { consumeSSE } from '../utils/sse.js'
import { auth } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

const route = useRoute()
const router = useRouter()

/* ---------------- 状态 ---------------- */
const sessions = ref([])
const sessionsLoading = ref(false)
const activeId = ref('')
const messages = ref([])
const historyLoading = ref(false)
const sending = ref(false)
const keyword = ref('')
// 地图默认展开：问答与路线图同屏显示（开题报告核心模块④地图可视化）
const showMap = ref(true)
const mapPoints = ref([])

const renameTarget = ref(null)
const renameText = ref('')
const deleteTarget = ref(null)
const savingPlan = ref(false)

// v-model 只接受成员表达式，不能写 !!xxx，用可写 computed 桥接
const showRename = computed({
  get: () => !!renameTarget.value,
  set: (v) => {
    if (!v) renameTarget.value = null
  }
})
const showDelete = computed({
  get: () => !!deleteTarget.value,
  set: (v) => {
    if (!v) deleteTarget.value = null
  }
})

const scroller = ref(null)
const inputEl = ref(null)
const draft = ref('')

/* 输入框随内容长高（最高 168px，超过后内部滚动），避免长句被裁成一行 */
watch(draft, () => {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 168)}px`
})

/* ---------------- 派生 ---------------- */
const filteredSessions = computed(() => {
  const k = keyword.value.trim().toLowerCase()
  if (!k) return sessions.value
  return sessions.value.filter((s) => (s.title || '').toLowerCase().includes(k))
})

const activeSession = computed(() => sessions.value.find((s) => s.session_id === activeId.value) || null)

const QUICK = [
  { label: '成都 3 天 · 3000 元', text: '从广州出发去成都玩3天，预算3000元，帮我规划行程' },
  { label: '西安 4 天 · 4000 元', text: '从上海出发去西安玩4天，预算4000元，想看历史古迹' },
  { label: '三亚 5 天 · 6000 元', text: '从北京出发去三亚玩5天，预算6000元，想要休闲度假' }
]

/* ---------------- 工具 ---------------- */
function uuid() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

function fmtTime(t) {
  if (!t) return ''
  const s = String(t).replace('T', ' ')
  return s.length >= 16 ? s.slice(5, 16) : s
}

function nearBottom() {
  const el = scroller.value
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight < 140
}

async function scrollToBottom(force = false) {
  await nextTick()
  const el = scroller.value
  if (!el) return
  if (force || nearBottom()) el.scrollTop = el.scrollHeight
}

/* ---------------- 会话列表 ---------------- */
async function loadSessions() {
  sessionsLoading.value = true
  try {
    const d = await chatApi.sessionList({ page: 1, pageSize: 50, userId: auth.userId.value })
    sessions.value = d.session_list || []
  } catch (e) {
    toast.error(errText(e, '会话列表加载失败'))
    sessions.value = []
  } finally {
    sessionsLoading.value = false
  }
}

async function openSession(s) {
  if (sending.value) {
    toast.warn('正在生成回复，请稍候')
    return
  }
  activeId.value = s.session_id
  router.replace({ query: { s: s.session_id } })
  syncMapPoints(s)
  messages.value = []
  historyLoading.value = true
  try {
    const d = await chatApi.history(s.session_id)
    messages.value = (d.history_list || []).map((m) => ({
      id: m.msg_id || uuid(),
      role: m.role === 'user' ? 'user' : 'assistant',
      content: m.content || '',
      time: m.modify_time
    }))
    await scrollToBottom(true)
  } catch (e) {
    toast.error(errText(e, '历史记录加载失败'))
  } finally {
    historyLoading.value = false
  }
}

function newChat() {
  if (sending.value) {
    toast.warn('正在生成回复，请稍候')
    return
  }
  activeId.value = ''
  messages.value = []
  mapPoints.value = []
  draft.value = ''
  router.replace({ query: {} })
  nextTick(() => inputEl.value?.focus())
}

/* ---------------- 地图点位 ---------------- */
function syncMapPoints(session) {
  mapPoints.value = []
  if (!session?.daily_routes) return
  try {
    const parsed = typeof session.daily_routes === 'string' ? JSON.parse(session.daily_routes) : session.daily_routes
    const days = parsed?.dailyRoutes || []
    const pts = []
    days.forEach((d, di) => {
      ;(d.points || []).forEach((p) => {
        if (p.longitude && p.latitude) {
          pts.push({ name: p.keyword, city: p.city, lng: p.longitude, lat: p.latitude, day: di + 1 })
        }
      })
    })
    mapPoints.value = pts
  } catch {
    mapPoints.value = []
  }
}

/* ---------------- 发送 + 流式接收 ---------------- */
async function send(text) {
  const content = (text ?? draft.value).trim()
  if (!content) return
  if (sending.value) return

  const sid = activeId.value || uuid()
  const isNew = !activeId.value
  activeId.value = sid
  draft.value = ''
  sending.value = true

  messages.value.push({ id: uuid(), role: 'user', content, time: new Date().toISOString() })

  const reply = reactive({ id: uuid(), role: 'assistant', content: '', streaming: true, error: false })
  messages.value.push(reply)
  await scrollToBottom(true)

  try {
    const res = await chatApi.chatStream({ sessionId: sid, message: content, userId: auth.userId.value })
    await consumeStream(res, reply)
  } catch (e) {
    reply.error = true
    reply.content = `请求失败：${errText(e)}`
  } finally {
    reply.streaming = false
    sending.value = false
    if (!reply.content) {
      reply.error = true
      reply.content = '本次未收到任何内容，请重试。'
    }
    await scrollToBottom()
    // 新会话或首轮结束后刷新列表以拿到标题
    if (isNew || messages.value.length <= 2) {
      await loadSessions()
      const cur = sessions.value.find((s) => s.session_id === sid)
      if (cur) syncMapPoints(cur)
    }
    // 生成出带坐标的路线后自动展开地图，保证「问答 + 地图」同屏可见
    if (mapPoints.value.length) showMap.value = true
  }
}

/**
 * 消费 SSE 事件流（解析逻辑抽到 utils/sse.js，便于单独测试）
 */
async function consumeStream(res, reply) {
  await consumeSSE(res, (delta) => {
    if (delta.text) {
      reply.content += delta.text
      scrollToBottom()
    }
  })
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

/* ---------------- 会话操作 ---------------- */
function askRename(s) {
  renameTarget.value = s
  renameText.value = s.title || ''
}

async function doRename() {
  const title = renameText.value.trim()
  if (!title) {
    toast.warn('标题不能为空')
    return
  }
  try {
    await chatApi.modifySession({ sessionId: renameTarget.value.session_id, opType: 3, title })
    renameTarget.value.title = title
    toast.success('标题已更新')
    renameTarget.value = null
  } catch (e) {
    toast.error(errText(e, '重命名失败'))
  }
}

async function doDelete() {
  const s = deleteTarget.value
  try {
    await chatApi.modifySession({ sessionId: s.session_id, opType: 2 })
    sessions.value = sessions.value.filter((x) => x.session_id !== s.session_id)
    if (activeId.value === s.session_id) newChat()
    toast.success('会话已删除')
  } catch (e) {
    toast.error(errText(e, '删除失败'))
  } finally {
    deleteTarget.value = null
  }
}

function copyReply(m) {
  navigator.clipboard
    ?.writeText(m.content)
    .then(() => toast.success('已复制到剪贴板'))
    .catch(() => toast.error('复制失败'))
}

/** 保存当前会话为旅行计划（行程持久化） */
async function savePlan() {
  if (!activeId.value) {
    toast.warn('请先开始一个对话')
    return
  }
  savingPlan.value = true
  try {
    const plan = await travelPlanApi.saveFromSession(activeId.value)
    toast.success(`已保存为行程：${plan.title || plan.plan_id}`)
  } catch (e) {
    toast.error(errText(e, '保存行程失败'))
  } finally {
    savingPlan.value = false
  }
}

/* ---------------- 生命周期 ---------------- */
onMounted(async () => {
  await loadSessions()
  const target = route.query.s
  if (target) {
    const s = sessions.value.find((x) => x.session_id === target)
    if (s) {
      await openSession(s)
      return
    }
  }
  nextTick(() => inputEl.value?.focus())
})

watch(
  () => route.query.s,
  (v) => {
    if (!v || v === activeId.value) return
    const s = sessions.value.find((x) => x.session_id === v)
    if (s) openSession(s)
  }
)
</script>

<template>
  <div class="chat">
    <!-- ============ 会话列表 ============ -->
    <aside class="side">
      <div class="side__top">
        <button class="btn btn--primary btn--block side__new" :disabled="sending" @click="newChat">
          <Icon name="plus" :size="15" />
          <span>新建对话</span>
        </button>

        <div class="side__search">
          <Icon name="search" :size="14" />
          <input v-model="keyword" class="side__search-input" type="text" placeholder="搜索会话" />
          <button v-if="keyword" class="side__clear" aria-label="清空搜索" @click="keyword = ''">
            <Icon name="close" :size="12" />
          </button>
        </div>
      </div>

      <div class="side__list">
        <template v-if="sessionsLoading">
          <div v-for="i in 5" :key="i" class="side__skeleton">
            <div class="skeleton" style="height: 12px; width: 62%" />
            <div class="skeleton" style="height: 9px; width: 38%; margin-top: 8px" />
          </div>
        </template>

        <div v-else-if="!filteredSessions.length" class="side__empty">
          <p>{{ keyword ? '没有匹配的会话' : '还没有对话记录' }}</p>
          <span>从右侧输入框开始第一段行程</span>
        </div>

        <div
          v-for="s in filteredSessions"
          :key="s.session_id"
          class="sess"
          :class="{ 'is-active': s.session_id === activeId }"
          @click="openSession(s)"
        >
          <div class="sess__main">
            <div class="sess__title truncate">{{ s.title || '未命名会话' }}</div>
            <div class="sess__time">{{ fmtTime(s.last_time) }}</div>
          </div>
          <div class="sess__ops" @click.stop>
            <button title="重命名" aria-label="重命名会话" @click="askRename(s)"><Icon name="edit" :size="13" /></button>
            <button title="删除" aria-label="删除会话" class="danger" @click="deleteTarget = s"><Icon name="trash" :size="13" /></button>
          </div>
        </div>
      </div>

      <button
        class="side__map-toggle"
        :class="{ 'is-on': showMap }"
        @click="showMap = !showMap"
      >
        <Icon name="route" :size="14" />
        <span>{{ showMap ? '收起路线图' : '展开路线图' }}</span>
        <span v-if="mapPoints.length" class="side__map-count">{{ mapPoints.length }}</span>
      </button>
    </aside>

    <!-- ============ 对话区 ============ -->
    <section class="thread">
      <header class="thread__head">
        <div class="thread__meta">
          <h2 class="thread__title truncate">{{ activeSession?.title || '新的对话' }}</h2>
          <p class="thread__sub">
            <span v-if="activeId" class="mono">{{ activeId.slice(0, 8) }}</span>
            <span v-else>描述目的地、天数与预算，越具体越准确</span>
          </p>
        </div>
        <div class="thread__actions">
          <span v-if="sending" class="thread__status">
            <span class="spinner" style="width: 11px; height: 11px; border-width: 1.6px" />
            生成中
          </span>
          <button v-if="messages.length" class="btn btn--quiet btn--sm" @click="newChat">
            <Icon name="plus" :size="13" />
            新对话
          </button>
        </div>
      </header>

      <div ref="scroller" class="thread__body">
        <!-- 空态：一句主张 + 三个可直接发送的例子 -->
        <div v-if="!messages.length && !historyLoading" class="welcome">
          <h3 class="welcome__title">今天想去哪里？</h3>
          <p class="welcome__desc">
            说出目的地、天数、预算和出发城市，系统会生成逐日行程与费用明细。
            给出预算时，会自动匹配出行档次并在超支时逐级下调。
          </p>
          <div class="welcome__quick">
            <button v-for="q in QUICK" :key="q.label" class="chip" :disabled="sending" @click="send(q.text)">
              <span>{{ q.label }}</span>
              <Icon name="chevronRight" :size="13" />
            </button>
          </div>
        </div>

        <div v-else-if="historyLoading" class="welcome">
          <span class="spinner" style="width: 20px; height: 20px; border-width: 2.2px" />
          <p class="t3" style="margin-top: 12px; font-size: 13px">正在载入历史消息…</p>
        </div>

        <!-- 消息流 -->
        <div v-for="m in messages" :key="m.id" class="msg" :class="`msg--${m.role}`">
          <div v-if="m.role === 'assistant'" class="msg__mark" aria-hidden="true">
            <Icon name="sparkle" :size="13" :stroke="1.6" />
          </div>
          <div class="msg__col">
            <div class="msg__bubble" :class="{ 'msg__bubble--err': m.error }">
              <MdView v-if="m.role === 'assistant'" :source="m.content" :streaming="!!m.streaming" />
              <p v-else class="msg__text">{{ m.content }}</p>

              <div v-if="m.streaming && !m.content" class="msg__thinking">
                <span class="dot" /><span class="dot" /><span class="dot" />
                <span class="msg__thinking-text">正在思考…</span>
              </div>
            </div>

            <div v-if="m.role === 'assistant' && m.content && !m.streaming" class="msg__ops">
              <button class="msg__op" @click="copyReply(m)">
                <Icon name="book" :size="12" /> 复制
              </button>
              <button
                class="msg__op"
                @click="router.push({ name: 'budget', query: { from: activeId, auto: '1' } })"
                :disabled="!activeId"
              >
                <Icon name="wallet" :size="12" /> 分析预算
              </button>
              <button class="msg__op" :disabled="!activeId || savingPlan" @click="savePlan">
                <Icon name="route" :size="12" /> {{ savingPlan ? '保存中…' : '保存为行程' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <footer class="composer">
        <div class="composer__box" :class="{ 'is-busy': sending }">
          <textarea
            ref="inputEl"
            v-model="draft"
            class="composer__input"
            rows="1"
            placeholder="例如：成都 3 天，预算 3000 元"
            :disabled="sending"
            @keydown="onKeydown"
          />
          <button class="composer__send" :disabled="sending || !draft.trim()" title="发送" aria-label="发送" @click="send()">
            <Icon v-if="!sending" name="send" :size="16" />
            <span v-else class="spinner" />
          </button>
        </div>
        <div class="composer__hint">
          <span><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd> + <kbd>Enter</kbd> 换行</span>
          <span v-if="sending">生成中，请勿关闭页面</span>
        </div>
      </footer>
    </section>

    <!-- ============ 路线图 ============ -->
    <Transition name="map">
      <RouteMap v-if="showMap" :points="mapPoints" @close="showMap = false" />
    </Transition>

    <!-- ============ 重命名弹窗 ============ -->
    <Modal v-model="showRename" title="重命名会话" width="420px">
      <div class="field">
        <label class="field__label">会话标题</label>
        <input
          v-model="renameText"
          class="input"
          type="text"
          maxlength="30"
          placeholder="输入新的标题"
          @keydown.enter="doRename"
        />
      </div>
      <template #footer>
        <button class="btn btn--ghost" @click="renameTarget = null">取消</button>
        <button class="btn btn--primary" @click="doRename">保存</button>
      </template>
    </Modal>

    <!-- ============ 删除确认 ============ -->
    <Modal v-model="showDelete" title="删除会话" width="420px">
      <p class="t2" style="font-size: 13.5px; line-height: 1.75">
        确定要删除会话「<strong>{{ deleteTarget?.title || '未命名会话' }}</strong>」吗？
        该操作会同时清除对话记录，且不可恢复。
      </p>
      <template #footer>
        <button class="btn btn--ghost" @click="deleteTarget = null">取消</button>
        <button class="btn btn--danger" @click="doDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.chat {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: var(--surface);
}

/* ---------------- 左侧会话列 ---------------- */
.side {
  width: var(--side-w);
  flex: none;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--line);
  background: var(--paper);
}

.side__top {
  padding: 16px 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side__new {
  height: 36px;
  font-size: 13px;
}

.side__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0 10px;
  height: 34px;
  border-radius: var(--r-sm);
  background: var(--paper-2);
  border: 1px solid transparent;
  color: var(--ink-4);
  transition: border-color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.side__search:focus-within {
  background: var(--surface);
  border-color: var(--line-strong);
}

.side__search-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  outline: none;
  font-size: 12.5px;
  color: var(--ink);
}

.side__search-input::placeholder { color: var(--ink-4); }

.side__clear {
  color: var(--ink-4);
  display: grid;
  place-items: center;
  padding: 2px;
  border-radius: 3px;
}

.side__clear:hover { color: var(--ink); }

.side__list {
  flex: 1;
  overflow-y: auto;
  padding: 2px 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.side__skeleton {
  padding: 10px 10px;
  border-radius: var(--r-sm);
}

.side__empty {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 40px 12px;
  text-align: center;
}

.side__empty p { font-size: 13px; color: var(--ink-3); }
.side__empty span { font-size: 11.5px; color: var(--ink-4); line-height: 1.6; }

/* 会话项 */
.sess {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.sess:hover { background: var(--paper-2); }

.sess.is-active {
  background: var(--surface);
  border-color: var(--line);
}

.sess.is-active .sess__title { font-weight: 550; }

.sess__main { flex: 1; min-width: 0; }

.sess__title {
  font-size: 13px;
  font-weight: 450;
  color: var(--ink);
}

.sess__time {
  font-size: 11px;
  color: var(--ink-4);
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}

.sess__ops {
  display: flex;
  gap: 1px;
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}

.sess:hover .sess__ops, .sess.is-active .sess__ops, .sess:focus-within .sess__ops { opacity: 1; }

.sess__ops button {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: var(--r-xs);
  color: var(--ink-3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.sess__ops button:hover { color: var(--ink); background: var(--paper-3); }
.sess__ops button.danger:hover { color: var(--danger); background: var(--danger-dim); }

.side__map-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 14px 14px;
  padding: 0 11px;
  height: 34px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--ink-3);
  font-size: 12.5px;
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.side__map-toggle:hover { color: var(--ink); border-color: var(--line-strong); }

.side__map-toggle.is-on {
  color: var(--accent-text);
  border-color: var(--accent-line);
  background: var(--accent-dim);
}

.side__map-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 1px 6px;
  border-radius: var(--r-xs);
  background: var(--surface);
  border: 1px solid var(--accent-line);
  color: var(--accent-text);
}

/* ---------------- 对话主区 ---------------- */
.thread {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.thread__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 26px;
  height: 58px;
  flex: none;
  border-bottom: 1px solid var(--line-faint);
}

.thread__meta { min-width: 0; }

.thread__title {
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: -0.015em;
}

.thread__sub {
  font-size: 11.5px;
  color: var(--ink-4);
  margin-top: 1px;
  font-variant-numeric: tabular-nums;
}

.thread__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.thread__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--accent-text);
}

.thread__body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 26px 10px;
  scroll-behavior: smooth;
}

/* ---------------- 欢迎态 ---------------- */
.welcome {
  max-width: 660px;
  margin: clamp(28px, 9vh, 96px) auto 0;
  text-align: left;
  animation: fade-up 0.5s var(--ease-out) both;
}

.welcome__title {
  font-size: clamp(28px, 3.2vw, 38px);
  font-weight: 600;
  letter-spacing: -0.036em;
  line-height: 1.15;
  color: var(--ink);
}

.welcome__desc {
  margin-top: 14px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--ink-3);
  max-width: 54ch;
}

.welcome__quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 26px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px 0 13px;
  border-radius: var(--r-sm);
  font-size: 12.5px;
  color: var(--ink-2);
  background: var(--surface);
  border: 1px solid var(--line);
  transition: border-color var(--dur) var(--ease), color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.chip svg { color: var(--ink-4); transition: color var(--dur) var(--ease); }

.chip:hover:not(:disabled) {
  color: var(--ink);
  border-color: var(--line-strong);
  background: var(--paper-2);
}

.chip:hover:not(:disabled) svg { color: var(--ink-2); }

.chip:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---------------- 消息 ---------------- */
.msg {
  display: flex;
  gap: 12px;
  max-width: 780px;
  margin: 0 auto 26px;
  animation: fade-up 0.3s var(--ease-out) both;
}

.msg--user {
  justify-content: flex-end;
  margin-bottom: 22px;
}

/* 助手消息：不套气泡，直接排在纸面上，靠左侧小标记识别说话人 */
.msg__mark {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex: none;
  margin-top: 1px;
  border-radius: 6px;
  background: var(--accent-dim);
  border: 1px solid var(--accent-line);
  color: var(--accent-text);
}

.msg__col {
  min-width: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
}

.msg--user .msg__col { align-items: flex-end; max-width: 78%; }

.msg__bubble {
  min-width: 0;
}

.msg--assistant .msg__bubble {
  padding-top: 1px;
}

.msg--user .msg__bubble {
  padding: 10px 14px;
  border-radius: var(--r-lg);
  background: var(--paper-2);
  border: 1px solid var(--line-faint);
}

.msg__bubble--err {
  border-color: var(--danger-line) !important;
  background: var(--danger-dim) !important;
  color: var(--danger);
  padding: 10px 13px !important;
  border-radius: var(--r-md) !important;
  font-size: 13.5px;
}

.msg__text {
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--ink);
}

.msg__thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 0;
}

.msg__thinking-text {
  margin-left: 4px;
  font-size: 13px;
  color: var(--ink-4);
}

.dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.7;
  animation: pulse-soft 1.2s var(--ease) infinite;
}

.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }

.msg__ops {
  display: flex;
  gap: 2px;
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--line-faint);
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}

.msg:hover .msg__ops,
.msg:focus-within .msg__ops { opacity: 1; }

.msg__op {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 8px;
  border-radius: var(--r-xs);
  font-size: 11.5px;
  color: var(--ink-3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.msg__op:hover:not(:disabled) { color: var(--ink); background: var(--paper-2); }
.msg__op:disabled { opacity: 0.4; cursor: not-allowed; }

/* ---------------- 输入区 ---------------- */
.composer {
  flex: none;
  padding: 10px 26px 14px;
  background: linear-gradient(180deg, rgba(250, 249, 245, 0), var(--paper) 42%);
}

.composer__box {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  max-width: 780px;
  margin: 0 auto;
  padding: 7px 7px 7px 15px;
  border-radius: var(--r-xl);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  box-shadow: var(--sh-1);
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.composer__box:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(11, 107, 99, 0.1);
}

.composer__box.is-busy { opacity: 0.72; }

.composer__input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  outline: none;
  resize: none;
  font-size: 14px;
  line-height: 1.6;
  max-height: 168px;
  padding: 8px 0;
  color: var(--ink);
  /* 超过最大高度后内部滚动，占位文案过长也不会溢出到框外 */
  overflow-y: auto;
}

.composer__input::placeholder { color: var(--ink-4); }

.composer__send {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: none;
  border-radius: 50%;
  background: var(--ink);
  color: #FCFBF7;
  transition: background var(--dur) var(--ease), opacity var(--dur) var(--ease);
}

.composer__send:hover:not(:disabled) { background: #2B2A20; }

.composer__send:disabled {
  background: var(--paper-3);
  color: var(--ink-4);
  cursor: not-allowed;
}

.composer__hint {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  max-width: 780px;
  margin: 8px auto 0;
  font-size: 11px;
  color: var(--ink-4);
}

kbd {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  color: var(--ink-3);
}

/* 地图面板过渡 */
.map-enter-active, .map-leave-active { transition: opacity 0.24s var(--ease), transform 0.24s var(--ease); }
.map-enter-from, .map-leave-to { opacity: 0; transform: translateX(18px); }

/* ---------------- 响应式 ---------------- */
@media (max-width: 1180px) {
  .side { width: 240px; }
  .thread__head, .thread__body, .composer { padding-left: 18px; padding-right: 18px; }
}

@media (max-width: 880px) {
  .side { display: none; }
  .thread__body { padding-top: 20px; }
  .msg--user .msg__col { max-width: 88%; }
}

@media (max-width: 560px) {
  .thread__head { padding: 0 14px; height: 52px; }
  .thread__body { padding: 16px 14px 8px; }
  .composer { padding: 8px 14px 12px; }
  .composer__hint { display: none; }
  .welcome { margin-top: 24px; }
  .welcome__quick { flex-direction: column; align-items: stretch; }
  .chip { justify-content: space-between; width: 100%; }
}
</style>
