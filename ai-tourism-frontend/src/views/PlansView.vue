<script setup>
/**
 * 我的行程（旅行计划持久化，开题报告数据库设计「行程表」落地）
 *
 * 能力：计划列表 / 详情（攻略 + 路线图 + 预算快照）/ 编辑（乐观锁 + 服务端重算）/ 归档删除
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../components/Icon.vue'
import MdView from '../components/MdView.vue'
import Modal from '../components/Modal.vue'
import RouteMap from '../components/RouteMap.vue'
import { travelPlanApi } from '../api/index.js'
import { toast, errText } from '../stores/toast.js'

const router = useRouter()

/* ---------------- 列表 ---------------- */
const plans = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)

async function loadList() {
  loading.value = true
  try {
    const d = await travelPlanApi.list({ page: page.value, pageSize: pageSize.value })
    plans.value = d?.list || []
    total.value = Number(d?.total || 0)
  } catch (e) {
    toast.error(errText(e, '计划列表加载失败'))
    plans.value = []
  } finally {
    loading.value = false
  }
}

function go(p) {
  page.value = p
  loadList()
}

/* ---------------- 详情 ---------------- */
const active = ref(null)
const detailLoading = ref(false)

const budget = computed(() => {
  const raw = active.value?.budget_json
  if (!raw) return null
  try {
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch {
    return null
  }
})

const detailItems = computed(() => (Array.isArray(budget.value?.items) ? budget.value.items : []))

const SOURCE_META = {
  TRAIN_API: { text: '真实票价', cls: 'real', tip: '来自 12306 同步的第三方聚合 API' },
  SNAPSHOT: { text: '快照价', cls: 'snap', tip: '来自景点库真实票价 / 酒店价格快照表' },
  ITINERARY: { text: '攻略载明', cls: 'itin', tip: '取自行程攻略中明确写明的价格' },
  ESTIMATE: { text: '系统估算', cls: 'est', tip: '未取到真实价格，按行业均价估算' }
}
function sourceMeta(s) {
  return SOURCE_META[s] || SOURCE_META.ESTIMATE
}

function money(v) {
  const n = Number(v)
  return Number.isFinite(n) ? `¥${n.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}` : '—'
}

function fmtTime(t) {
  if (!t) return ''
  const s = String(t).replace('T', ' ')
  return s.length >= 16 ? s.slice(5, 16) : s
}

/** 从 daily_routes 提取地图点位（与 ChatView 同一结构） */
const mapPoints = computed(() => {
  const raw = active.value?.daily_routes
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    const pts = []
    ;(parsed?.dailyRoutes || []).forEach((d, di) => {
      ;(d.points || []).forEach((p) => {
        if (p.longitude && p.latitude) {
          pts.push({ name: p.keyword, city: p.city, lng: p.longitude, lat: p.latitude, day: di + 1 })
        }
      })
    })
    return pts
  } catch {
    return []
  }
})

async function openDetail(plan) {
  detailLoading.value = true
  active.value = null
  try {
    active.value = await travelPlanApi.detail(plan.plan_id)
  } catch (e) {
    toast.error(errText(e, '计划详情加载失败'))
  } finally {
    detailLoading.value = false
  }
}

function backToList() {
  active.value = null
  loadList()
}

/* ---------------- 编辑（乐观锁 + 服务端重算） ---------------- */
const showEdit = ref(false)
const saving = ref(false)
const editForm = ref({ plan_id: '', version: 0, title: '', days: 1, budget_amount: '', content: '' })

function askEdit(plan) {
  editForm.value = {
    plan_id: plan.plan_id,
    version: plan.version ?? 0,
    title: plan.title || '',
    days: plan.days || 1,
    budget_amount: plan.budget_amount ?? '',
    content: plan.content || ''
  }
  showEdit.value = true
}

async function doEdit() {
  if (!editForm.value.content.trim()) {
    toast.warn('行程内容不能为空')
    return
  }
  saving.value = true
  try {
    const payload = {
      plan_id: editForm.value.plan_id,
      version: editForm.value.version,
      title: editForm.value.title.trim() || undefined,
      days: Number(editForm.value.days) || undefined,
      budget_amount: editForm.value.budget_amount === '' ? undefined : Number(editForm.value.budget_amount),
      content: editForm.value.content
    }
    const updated = await travelPlanApi.update(payload)
    toast.success('已保存，预算已由服务端重新计算')
    showEdit.value = false
    // 同步本地版本号，避免连续编辑触发乐观锁冲突
    editForm.value.version = updated?.version ?? editForm.value.version
    active.value = updated || active.value
    await loadList()
  } catch (e) {
    const msg = errText(e, '保存失败')
    if (msg.includes('4090') || msg.includes('版本冲突') || msg.includes('已被其他会话修改')) {
      toast.error('该计划已被其他页面修改，请关闭后重新打开')
      showEdit.value = false
      await loadList()
    } else {
      toast.error(msg)
    }
  } finally {
    saving.value = false
  }
}

/* ---------------- 删除 ---------------- */
const deleteTarget = ref(null)

async function doDelete() {
  const plan = deleteTarget.value
  if (!plan) return
  try {
    await travelPlanApi.remove(plan.plan_id)
    toast.success('计划已归档')
    if (active.value?.plan_id === plan.plan_id) active.value = null
    await loadList()
  } catch (e) {
    toast.error(errText(e, '删除失败'))
  } finally {
    deleteTarget.value = null
  }
}

onMounted(loadList)
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">我的行程</h1>
          <p class="page-head__sub">
            保存的旅行计划可随时查看、编辑并重算预算；编辑保存采用乐观锁，避免并发覆盖。
          </p>
        </div>
        <button class="btn btn--quiet" @click="router.push({ name: 'chat' })">
          <Icon name="plus" :size="14" /> 去规划新行程
        </button>
      </header>

      <!-- ============ 计划详情 ============ -->
      <template v-if="active">
        <div class="detail-bar">
          <button class="btn btn--quiet btn--sm" @click="backToList">
            <Icon name="chevronLeft" :size="14" /> 返回列表
          </button>
          <div class="detail-bar__actions">
            <button class="btn btn--ghost btn--sm" @click="askEdit(active)">
              <Icon name="edit" :size="14" /> 编辑并重算
            </button>
            <button class="btn btn--ghost btn--sm danger" @click="deleteTarget = active">
              <Icon name="trash" :size="14" /> 归档
            </button>
          </div>
        </div>

        <div class="detail-grid">
          <div class="detail-main">
            <section class="card card--solid panel">
              <div class="panel__head">
                <h2 class="panel__title">
                  <Icon name="route" :size="16" /> {{ active.title || '未命名计划' }}
                </h2>
                <span class="t3" style="font-size: 12.5px">
                  {{ active.dest_city || '—' }} · {{ active.days }} 天 · 版本 v{{ active.version }}
                </span>
              </div>
              <div class="detail-content">
                <MdView :source="active.content || ''" />
              </div>
            </section>

            <section v-if="budget" class="card card--solid panel">
              <div class="panel__head">
                <h2 class="panel__title"><Icon name="coins" :size="16" /> 预算快照</h2>
                <span class="t3" style="font-size: 12.5px">保存时的分析结果，编辑后自动重算</span>
              </div>
              <div class="budget-figs">
                <div class="fig">
                  <div class="fig__k">总花费</div>
                  <div class="fig__v">{{ money(budget.totalBudget) }}</div>
                </div>
                <div class="fig">
                  <div class="fig__k">交通</div>
                  <div class="fig__v">{{ money(budget.transportCost) }}</div>
                </div>
                <div class="fig">
                  <div class="fig__k">住宿</div>
                  <div class="fig__v">{{ money(budget.accommodationCost) }}</div>
                </div>
                <div class="fig">
                  <div class="fig__k">餐饮</div>
                  <div class="fig__v">{{ money(budget.foodCost) }}</div>
                </div>
                <div class="fig">
                  <div class="fig__k">门票</div>
                  <div class="fig__v">{{ money(budget.ticketCost) }}</div>
                </div>
                <div class="fig">
                  <div class="fig__k">其他</div>
                  <div class="fig__v">{{ money(budget.otherCost) }}</div>
                </div>
              </div>
              <ul v-if="detailItems.length" class="items">
                <li v-for="(it, i) in detailItems" :key="i" class="item">
                  <span class="item__cat">{{ it.category }}</span>
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
            </section>
          </div>

          <aside class="detail-side">
            <div class="detail-map">
              <RouteMap :points="mapPoints" />
            </div>
          </aside>
        </div>
      </template>

      <!-- ============ 计划列表 ============ -->
      <template v-else>
        <div v-if="loading" class="plan-grid">
          <div v-for="i in 4" :key="i" class="skeleton" style="height: 132px" />
        </div>

        <div v-else-if="!plans.length" class="card panel empty">
          <div class="empty__icon"><Icon name="route" :size="22" /></div>
          <div class="empty__title">还没有保存的行程</div>
          <p class="empty__desc">
            在「智能规划」生成攻略后，点击消息下方的「保存为行程」，或在「预算分析」页点击「保存为行程」。
            保存后的计划可以随时查看、编辑，编辑后预算会自动重新计算。
          </p>
          <button class="btn btn--primary" @click="router.push({ name: 'chat' })">
            <Icon name="sparkle" :size="15" /> 去规划行程
          </button>
        </div>

        <div v-else class="plan-list">
          <article v-for="p in plans" :key="p.plan_id" class="plan-row" @click="openDetail(p)">
            <span class="plan-row__city">{{ p.dest_city || '旅行' }}</span>
            <div class="plan-row__main">
              <h3 class="plan-row__title truncate">{{ p.title || '未命名计划' }}</h3>
              <div class="plan-row__meta">
                <span>{{ p.budget_amount ? '预算 ' + money(p.budget_amount) : '未设预算' }}</span>
                <span class="plan-row__sep">·</span>
                <span>更新于 {{ fmtTime(p.modify_time) }}</span>
              </div>
            </div>
            <span class="plan-row__days">{{ p.days }} 天</span>
            <Icon name="chevronRight" :size="15" class="plan-row__go" />
          </article>
        </div>

        <div v-if="total > pageSize" class="pager">
          <button class="btn btn--quiet btn--sm" :disabled="page <= 1" @click="go(page - 1)">
            <Icon name="chevronLeft" :size="14" /> 上一页
          </button>
          <span class="t3" style="font-size: 12.5px">第 {{ page }} 页 / 共 {{ Math.ceil(total / pageSize) }} 页</span>
          <button class="btn btn--quiet btn--sm" :disabled="page >= Math.ceil(total / pageSize)" @click="go(page + 1)">
            下一页 <Icon name="chevronRight" :size="14" />
          </button>
        </div>
      </template>
    </div>

    <!-- ============ 编辑弹窗 ============ -->
    <Modal v-model="showEdit" title="编辑行程（保存后服务端重算预算）" width="720px">
      <div class="field">
        <label class="field__label">标题</label>
        <input v-model="editForm.title" class="input" type="text" maxlength="120" placeholder="计划标题" />
      </div>
      <div class="grid-2" style="margin-top: 12px">
        <div class="field">
          <label class="field__label">行程天数</label>
          <input v-model.number="editForm.days" class="input" type="number" min="1" max="30" />
        </div>
        <div class="field">
          <label class="field__label">预算（元，留空表示不约束）</label>
          <input v-model="editForm.budget_amount" class="input" type="number" min="0" placeholder="如 3000" />
        </div>
      </div>
      <div class="field" style="margin-top: 12px">
        <label class="field__label">
          行程内容
          <span class="t3">— 修改内容后保存，预算会按新内容在服务端重新计算</span>
        </label>
        <textarea v-model="editForm.content" class="textarea" rows="14" />
      </div>
      <template #footer>
        <button class="btn btn--ghost" @click="showEdit = false">取消</button>
        <button class="btn btn--primary" :disabled="saving" @click="doEdit">
          <span v-if="saving" class="spinner" />
          {{ saving ? '保存并重算中…' : '保存并重算预算' }}
        </button>
      </template>
    </Modal>

    <!-- ============ 归档确认 ============ -->
    <Modal v-model="deleteTarget" title="归档行程" width="420px">
      <p class="t2">
        确定要归档「<strong>{{ deleteTarget?.title || '未命名计划' }}</strong>」吗？归档后不会出现在列表中。
      </p>
      <template #footer>
        <button class="btn btn--ghost" @click="deleteTarget = null">取消</button>
        <button class="btn btn--danger" @click="doDelete">确认归档</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
/* 页面滚动容器：缺失会被父级 .app__main(overflow:hidden) 裁掉超出的行程内容 */
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

/* ---------------- 行程列表：一行一条，靠线分隔 ---------------- */
.plan-list {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  overflow: hidden;
}

.plan-row {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr) auto 18px;
  align-items: center;
  gap: 18px;
  padding: 17px 20px;
  cursor: pointer;
  border-bottom: 1px solid var(--line-faint);
  transition: background var(--dur) var(--ease);
}

.plan-row:last-child { border-bottom: 0; }

.plan-row:hover { background: var(--paper); }

.plan-row__city {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--accent-text);
  padding: 3px 8px;
  border: 1px solid var(--accent-line);
  border-radius: 3px;
  background: var(--accent-dim);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-row__main { min-width: 0; }

.plan-row__title {
  font-size: 14.5px;
  font-weight: 550;
  color: var(--ink);
  letter-spacing: -0.015em;
}

.plan-row__meta {
  display: flex;
  gap: 6px;
  margin-top: 3px;
  font-size: 11.5px;
  color: var(--ink-4);
  font-variant-numeric: tabular-nums;
}

.plan-row__sep { color: var(--line-strong); }

.plan-row__days {
  font-family: var(--font-mono);
  font-size: 11.5px;
  color: var(--ink-3);
  padding: 3px 8px;
  border-radius: 3px;
  background: var(--paper-2);
}

.plan-row__go {
  color: var(--line-strong);
  transition: color var(--dur) var(--ease), transform var(--dur) var(--ease);
}

.plan-row:hover .plan-row__go { color: var(--ink-3); transform: translateX(2px); }

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 22px;
}

/* ---------------- 详情 ---------------- */
.detail-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}

.detail-bar__actions { display: flex; gap: 8px; }

.danger { color: var(--danger); }
.danger:hover { background: var(--danger-dim); border-color: var(--danger-line); }

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 18px;
  align-items: start;
}

.detail-main { display: flex; flex-direction: column; gap: 18px; min-width: 0; }

.detail-content { font-size: 14px; line-height: 1.8; }

.detail-side { position: sticky; top: 0; }

.detail-map {
  border-radius: var(--r-lg);
  overflow: hidden;
  border: 1px solid var(--line);
  height: 580px;
  display: flex;
  background: var(--surface);
}

.detail-map > :deep(.map) {
  width: 100%;
  border-left: 0;
}

/* ---------------- 预算快照 ---------------- */
.budget-figs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 20px;
  padding: 18px 0;
  margin-bottom: 6px;
  border-top: 1px solid var(--line-faint);
  border-bottom: 1px solid var(--line-faint);
}

.budget-figs .fig__k {
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.02em;
}

.budget-figs .fig__v {
  margin-top: 2px;
  font-size: 17px;
  font-weight: 600;
  color: var(--ink);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

/* ---------------- 费用明细 ---------------- */
.items { list-style: none; display: flex; flex-direction: column; }

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

@media (max-width: 1100px) {
  .detail-grid { grid-template-columns: minmax(0, 1fr); }
  .detail-side { position: static; }
  .detail-map { height: 420px; }
  .page__inner { padding: 22px 18px 48px; }
}

@media (max-width: 640px) {
  .plan-row { grid-template-columns: 68px minmax(0, 1fr) auto; gap: 12px; padding: 14px; }
  .plan-row__go { display: none; }
  .budget-figs { grid-template-columns: repeat(2, 1fr); }
}
</style>
