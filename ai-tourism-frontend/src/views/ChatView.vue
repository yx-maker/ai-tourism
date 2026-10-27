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
    <aside class="side" :class="{ 'side--narrow': !showMap }">
      <div class="side__head">
        <button class="btn btn--primary btn--block" :disabled="sending" @click="newChat">
          <Icon name="plus" :size="15" />
          <span>新建对话</span>
        </button>
      </div>

      <div class="side__search">
        <Icon name="search" :size="15" />
        <input v-model="keyword" class="side__search-input" type="text" placeholder="搜索会话标题" />
        <button v-if="keyword" class="side__clear" aria-label="清空" @click="keyword = ''">
          <Icon name="close" :size="13" />
        </button>
      </div>

      <div class="side__list">
        <template v-if="sessionsLoading">
          <div v-for="i in 5" :key="i" class="side__skeleton">
            <div class="skeleton" style="height: 13px; width: 62%" />
            <div class="skeleton" style="height: 10px; width: 38%; margin-top: 8px" />
          </div>
        </template>

        <div v-else-if="!filteredSessions.length" class="side__empty">
          <Icon name="chat" :size="26" />
          <p>{{ keyword ? '没有匹配的会话' : '还没有对话记录' }}</p>
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
            <button title="重命名" @click="askRename(s)"><Icon name="edit" :size="14" /></button>
            <button title="删除" class="danger" @click="deleteTarget = s"><Icon name="trash" :size="14" /></button>
          </div>
        </div>
      </div>

      <button
        class="side__map-toggle"
        :class="{ 'is-on': showMap }"
        @click="showMap = !showMap"
      >
        <Icon name="route" :size="15" />
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
            <span v-else>描述你的旅行需求，越具体越准确</span>
          </p>
        </div>
        <div class="thread__actions">
          <span v-if="sending" class="badge badge--brand">
            <span class="spinner" style="width: 11px; height: 11px; border-width: 1.6px" />
            生成中
          </span>
          <button v-if="messages.length" class="btn btn--quiet btn--sm" @click="newChat">
            <Icon name="plus" :size="14" />
            新对话
          </button>
        </div>
      </header>

      <div ref="scroller" class="thread__body">
        <!-- 空态：引导 + 快捷提问 -->
        <div v-if="!messages.length && !historyLoading" class="welcome">
          <div class="welcome__mark"><Icon name="sparkle" :size="30" :stroke="1.5" /></div>
          <h3 class="welcome__title">今天想去哪里？</h3>
          <p class="welcome__desc">
            说出目的地、天数、预算和出发城市，系统会生成逐日行程与费用明细。
            若给出预算，会自动匹配出行档次并在超支时逐级下调。
          </p>
          <div class="welcome__quick">
            <button v-for="q in QUICK" :key="q.label" class="chip" :disabled="sending" @click="send(q.text)">
              <Icon name="compass" :size="14" />
              {{ q.label }}
            </button>
          </div>
        </div>

        <div v-else-if="historyLoading" class="welcome">
          <span class="spinner" style="width: 22px; height: 22px; border-width: 2.4px" />
          <p class="t3" style="margin-top: 12px">正在载入历史消息…</p>
        </div>

        <!-- 消息流 -->
        <div v-for="m in messages" :key="m.id" class="msg" :class="`msg--${m.role}`">
          <div class="msg__avatar">
            <Icon :name="m.role === 'user' ? 'user' : 'sparkle'" :size="15" />
          </div>
          <div class="msg__col">
            <div class="msg__bubble" :class="{ 'msg__bubble--err': m.error }">
              <MdView v-if="m.role === 'assistant'" :source="m.content" :streaming="!!m.streaming" />
              <p v-else class="msg__text">{{ m.content }}</p>

              <div v-if="m.streaming && !m.content" class="msg__thinking">
                <span class="dot" /><span class="dot" /><span class="dot" />
                <span class="t3" style="margin-left: 4px">正在思考…</span>
              </div>
            </div>

            <div v-if="m.role === 'assistant' && m.content && !m.streaming" class="msg__ops">
              <button class="msg__op" @click="copyReply(m)">
                <Icon name="book" :size="13" /> 复制
              </button>
              <button
                class="msg__op"
                @click="router.push({ name: 'budget', query: { from: activeId, auto: '1' } })"
                :disabled="!activeId"
              >
                <Icon name="wallet" :size="13" /> 分析预算
              </button>
              <button class="msg__op" :disabled="!activeId || savingPlan" @click="savePlan">
                <Icon name="route" :size="13" /> {{ savingPlan ? '保存中…' : '保存为行程' }}
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
            placeholder="例如：从广州出发去成都玩3天，预算3000元"
            :disabled="sending"
            @keydown="onKeydown"
          />
          <button class="composer__send" :disabled="sending || !draft.trim()" title="发送" @click="send()">
            <Icon v-if="!sending" name="send" :size="17" />
            <span v-else class="spinner" />
          </button>
        </div>
        <div class="composer__hint">
          <span><kbd>Enter</kbd> 发送 · <kbd>Shift</kbd>+<kbd>Enter</kbd> 换行</span>
          <span v-if="sending" class="t3">生成中，请勿关闭页面</span>
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
      <p class="t2">
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
}

/* ---------------- 左侧会话列 ---------------- */
.side {
  width: var(--side-w);
  flex: none;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--line);
  background: rgba(8, 11, 20, 0.42);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  transition: width var(--dur) var(--ease);
}

.side__head { padding: 16px 14px 10px; }

.side__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 14px 10px;
  padding: 0 11px;
  height: 35px;
  border-radius: var(--r-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line);
  color: var(--t3);
}

.side__search:focus-within {
  border-color: rgba(34, 211, 238, 0.45);
  background: rgba(34, 211, 238, 0.04);
}

.side__search-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  outline: none;
  font-size: 13px;
  color: var(--t1);
}

.side__search-input::placeholder { color: var(--t4); }

.side__clear {
  color: var(--t4);
  display: grid;
  place-items: center;
  padding: 2px;
  border-radius: 4px;
}

.side__clear:hover { color: var(--t1); background: var(--glass-hover); }

.side__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.side__skeleton {
  padding: 11px 10px;
  border-radius: var(--r-sm);
  background: var(--glass);
}

.side__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  padding: 46px 12px;
  color: var(--t4);
  text-align: center;
  font-size: 13px;
}

/* 会话项 */
.sess {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 10px;
  border-radius: var(--r-sm);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--dur) var(--ease), border-color var(--dur) var(--ease);
}

.sess:hover { background: var(--glass-hover); }

.sess.is-active {
  background: var(--grad-brand-soft);
  border-color: rgba(34, 211, 238, 0.3);
}

.sess__main { flex: 1; min-width: 0; }

.sess__title {
  font-size: 13.4px;
  font-weight: 550;
  color: var(--t1);
}

.sess__time {
  font-size: 11.5px;
  color: var(--t4);
  margin-top: 3px;
}

.sess__ops {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}

.sess:hover .sess__ops, .sess.is-active .sess__ops { opacity: 1; }

.sess__ops button {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: var(--r-xs);
  color: var(--t3);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.sess__ops button:hover { color: var(--t1); background: var(--glass-active); }
.sess__ops button.danger:hover { color: var(--danger); background: var(--danger-dim); }

.side__map-toggle {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 14px 14px;
  padding: 0 13px;
  height: 37px;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--glass);
  color: var(--t2);
  font-size: 13px;
  transition: all var(--dur) var(--ease);
}

.side__map-toggle:hover { border-color: var(--line-strong); color: var(--t1); }

.side__map-toggle.is-on {
  color: #A5F3FC;
  border-color: rgba(34, 211, 238, 0.35);
  background: var(--grad-brand-soft);
}

.side__map-count {
  margin-left: auto;
  font-size: 11.5px;
  padding: 1px 7px;
  border-radius: var(--r-full);
  background: rgba(34, 211, 238, 0.16);
  color: #A5F3FC;
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
  padding: 15px 26px;
  border-bottom: 1px solid var(--line);
  background: rgba(8, 11, 20, 0.5);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.thread__meta { min-width: 0; }

.thread__title {
  font-size: 15.5px;
  font-weight: 650;
  letter-spacing: -0.2px;
}

.thread__sub {
  font-size: 12px;
  color: var(--t4);
  margin-top: 2px;
}

.thread__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: none;
}

.thread__body {
  flex: 1;
  overflow-y: auto;
  padding: 26px 26px 8px;
  scroll-behavior: smooth;
}

/* ---------------- 欢迎态 ---------------- */
.welcome {
  max-width: 660px;
  margin: 6vh auto 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  animation: fade-up 0.5s var(--ease-out) both;
}

.welcome__mark {
  display: grid;
  place-items: center;
  width: 68px;
  height: 68px;
  border-radius: 21px;
  background: var(--grad-brand-soft);
  border: 1px solid rgba(34, 211, 238, 0.28);
  color: var(--cyan);
  box-shadow: var(--glow-cyan);
  margin-bottom: 20px;
}

.welcome__title {
  font-size: 25px;
  font-weight: 720;
  letter-spacing: -0.5px;
}

.welcome__desc {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.8;
  color: var(--t3);
  max-width: 500px;
}

.welcome__quick {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 9px;
  margin-top: 24px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 35px;
  padding: 0 14px;
  border-radius: var(--r-full);
  font-size: 13px;
  color: var(--t2);
  background: var(--glass);
  border: 1px solid var(--line);
  transition: all var(--dur) var(--ease);
}

.chip:hover:not(:disabled) {
  color: #CFFAFE;
  border-color: rgba(34, 211, 238, 0.4);
  background: var(--grad-brand-soft);
  transform: translateY(-1px);
}

.chip:disabled { opacity: 0.5; cursor: not-allowed; }

/* ---------------- 消息 ---------------- */
.msg {
  display: flex;
  gap: 13px;
  max-width: 880px;
  margin: 0 auto 22px;
  animation: fade-up 0.34s var(--ease-out) both;
}

.msg--user { flex-direction: row-reverse; }

.msg__avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: none;
  border-radius: 10px;
  margin-top: 2px;
}

.msg--assistant .msg__avatar {
  background: var(--grad-brand-soft);
  border: 1px solid rgba(34, 211, 238, 0.3);
  color: var(--cyan);
}

.msg--user .msg__avatar {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--line-strong);
  color: var(--t2);
}

.msg__col {
  min-width: 0;
  max-width: calc(100% - 46px);
  display: flex;
  flex-direction: column;
}

.msg--user .msg__col { align-items: flex-end; }

.msg__bubble {
  padding: 14px 17px;
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
  background: var(--glass);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.msg--assistant .msg__bubble {
  border-top-left-radius: var(--r-xs);
  border-left: 2px solid rgba(34, 211, 238, 0.5);
}

.msg--user .msg__bubble {
  border-top-right-radius: var(--r-xs);
  background: linear-gradient(135deg, rgba(34, 211, 238, 0.13), rgba(168, 85, 247, 0.11));
  border-color: rgba(34, 211, 238, 0.26);
}

.msg__bubble--err {
  border-color: rgba(248, 113, 113, 0.4) !important;
  background: var(--danger-dim) !important;
  color: #FCA5A5;
}

.msg__text {
  font-size: 14.3px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg__thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 13.5px;
  color: var(--t3);
}

.dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--cyan);
  animation: pulse-soft 1.2s var(--ease) infinite;
}

.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }

.msg__ops {
  display: flex;
  gap: 4px;
  margin-top: 7px;
  opacity: 0;
  transition: opacity var(--dur) var(--ease);
}

.msg:hover .msg__ops { opacity: 1; }

.msg__op {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border-radius: var(--r-xs);
  font-size: 12px;
  color: var(--t3);
  transition: all var(--dur) var(--ease);
}

.msg__op:hover:not(:disabled) { color: var(--cyan); background: var(--glass-hover); }
.msg__op:disabled { opacity: 0.4; cursor: not-allowed; }

/* ---------------- 输入区 ---------------- */
.composer {
  padding: 12px 26px 18px;
  border-top: 1px solid var(--line);
  background: rgba(8, 11, 20, 0.55);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.composer__box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  max-width: 880px;
  margin: 0 auto;
  padding: 9px 9px 9px 16px;
  border-radius: var(--r-lg);
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid var(--line);
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.composer__box:focus-within {
  border-color: rgba(34, 211, 238, 0.5);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.1);
}

.composer__box.is-busy { opacity: 0.72; }

.composer__input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  outline: none;
  resize: none;
  font-size: 14.3px;
  line-height: 1.65;
  max-height: 168px;
  padding: 8px 0;
  color: var(--t1);
}

.composer__input::placeholder { color: var(--t4); }

.composer__send {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: var(--r-md);
  background: var(--grad-brand);
  color: #05070D;
  transition: all var(--dur) var(--ease);
  box-shadow: 0 6px 20px -10px rgba(34, 211, 238, 0.9);
}

.composer__send:hover:not(:disabled) { filter: brightness(1.08); }

.composer__send:disabled {
  background: rgba(255, 255, 255, 0.07);
  color: var(--t4);
  box-shadow: none;
  cursor: not-allowed;
}

.composer__hint {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  max-width: 880px;
  margin: 8px auto 0;
  font-size: 11.5px;
  color: var(--t4);
}

kbd {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid var(--line);
}

/* 地图面板过渡 */
.map-enter-active, .map-leave-active { transition: all 0.28s var(--ease); }
.map-enter-from, .map-leave-to { opacity: 0; transform: translateX(24px); }

@media (max-width: 1080px) {
  .side { width: 240px; }
}

@media (max-width: 820px) {
  .side { display: none; }
  .thread__head, .thread__body, .composer { padding-left: 16px; padding-right: 16px; }
}
</style>
