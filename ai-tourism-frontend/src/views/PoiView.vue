<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'
import { poiApi, favoriteApi } from '../api/index.js'
import { isAdmin } from '../stores/auth.js'
import { toast, errText } from '../stores/toast.js'

/* ---------------- 列表 ---------------- */
const list = ref([])
const total = ref(0)
const cities = ref([])
const loading = ref(false)

const query = reactive({ cityName: '', keyword: '', page: 1, pageSize: 12 })

const favIds = ref(new Set())

const admin = computed(() => isAdmin())

const totalPages = computed(() => Math.max(Math.ceil(total.value / query.pageSize), 1))

async function load() {
  loading.value = true
  try {
    const d = await poiApi.page(query)
    list.value = d.list || []
    total.value = d.total || 0
  } catch (e) {
    toast.error(errText(e, '景点列表加载失败'))
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadCities() {
  try {
    cities.value = (await poiApi.cities()) || []
  } catch {
    cities.value = []
  }
}

async function loadFavorites() {
  try {
    const d = (await favoriteApi.list()) || []
    favIds.value = new Set(d.map((f) => f.poi_id))
  } catch {
    favIds.value = new Set()
  }
}

function search() {
  query.page = 1
  load()
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  query.page = p
  load()
}

function resetFilter() {
  query.cityName = ''
  query.keyword = ''
  query.page = 1
  load()
}

/* ---------------- 收藏 ---------------- */
async function toggleFav(p) {
  const has = favIds.value.has(p.id)
  try {
    if (has) await favoriteApi.remove(p.id)
    else await favoriteApi.add(p.id)
    const s = new Set(favIds.value)
    has ? s.delete(p.id) : s.add(p.id)
    favIds.value = s
    toast.success(has ? '已取消收藏' : `已收藏「${p.poi_name}」`)
  } catch (e) {
    toast.error(errText(e, has ? '取消收藏失败' : '收藏失败'))
  }
}

/* ---------------- 增删改（需 ROOT） ---------------- */
const editing = ref(null)
const saving = ref(false)
const deleting = ref(null)

// v-model 只接受成员表达式，不能写 !!xxx，用可写 computed 桥接
const showEditing = computed({
  get: () => !!editing.value,
  set: (v) => {
    if (!v) editing.value = null
  }
})
const showDeleting = computed({
  get: () => !!deleting.value,
  set: (v) => {
    if (!v) deleting.value = null
  }
})

const BLANK = {
  id: null,
  poi_name: '',
  city_name: '',
  poi_description: '',
  poi_longitude: null,
  poi_latitude: null,
  poi_rank_in_city: null,
  poi_rank_in_china: null,
  ticket_price: null
}

const form = reactive({ ...BLANK })

function openCreate() {
  Object.assign(form, BLANK)
  editing.value = { mode: 'create' }
}

function openEdit(p) {
  Object.assign(form, {
    id: p.id,
    poi_name: p.poi_name,
    city_name: p.city_name,
    poi_description: p.poi_description,
    poi_longitude: p.poi_longitude,
    poi_latitude: p.poi_latitude,
    poi_rank_in_city: p.poi_rank_in_city,
    poi_rank_in_china: p.poi_rank_in_china,
    ticket_price: p.ticket_price
  })
  editing.value = { mode: 'edit' }
}

async function save() {
  if (!form.poi_name?.trim()) {
    toast.warn('请填写景点名称')
    return
  }
  if (!form.city_name?.trim()) {
    toast.warn('请填写所在城市')
    return
  }
  saving.value = true
  try {
    const payload = {
      ...form,
      poi_longitude: form.poi_longitude === '' || form.poi_longitude === null ? null : Number(form.poi_longitude),
      poi_latitude: form.poi_latitude === '' || form.poi_latitude === null ? null : Number(form.poi_latitude),
      poi_rank_in_city: form.poi_rank_in_city === '' || form.poi_rank_in_city === null ? null : Number(form.poi_rank_in_city),
      poi_rank_in_china: form.poi_rank_in_china === '' || form.poi_rank_in_china === null ? null : Number(form.poi_rank_in_china),
      ticket_price: form.ticket_price === '' || form.ticket_price === null ? null : Number(form.ticket_price)
    }
    if (editing.value.mode === 'create') {
      delete payload.id
      await poiApi.add(payload)
      toast.success('景点已新增')
    } else {
      await poiApi.update(payload)
      toast.success('景点已更新')
    }
    editing.value = null
    await Promise.all([load(), loadCities()])
  } catch (e) {
    toast.error(errText(e, '保存失败'))
  } finally {
    saving.value = false
  }
}

async function doDelete() {
  try {
    await poiApi.remove(deleting.value.id)
    toast.success('景点已删除')
    deleting.value = null
    await load()
  } catch (e) {
    toast.error(errText(e, '删除失败'))
  }
}

function priceText(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return '免费'
  return `¥${n}`
}

onMounted(async () => {
  await Promise.all([loadCities(), loadFavorites(), load()])
})

watch(() => query.cityName, search)
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">景点库</h1>
          <p class="page-head__sub">
            共 <strong>{{ total }}</strong> 条景点数据 · 覆盖 {{ cities.length }} 个城市
          </p>
        </div>
        <div style="display: flex; gap: 10px">
          <RouterLink to="/favorites" class="btn btn--ghost">
            <Icon name="heart" :size="15" /> 我的收藏
          </RouterLink>
          <button v-if="admin" class="btn btn--primary" @click="openCreate">
            <Icon name="plus" :size="15" /> 新增景点
          </button>
        </div>
      </header>

      <!-- 筛选 -->
      <section class="card card--solid filters">
        <div class="filters__search">
          <Icon name="search" :size="16" />
          <input
            v-model="query.keyword"
            class="filters__input"
            type="text"
            placeholder="搜索景点名称或描述…"
            @keydown.enter="search"
          />
        </div>

        <select v-model="query.cityName" class="select" style="width: 152px">
          <option value="">全部城市</option>
          <option v-for="c in cities" :key="c" :value="c">{{ c }}</option>
        </select>

        <button class="btn btn--primary" @click="search">
          <Icon name="search" :size="15" /> 查询
        </button>
        <button class="btn btn--quiet" @click="resetFilter">
          <Icon name="refresh" :size="15" /> 重置
        </button>
      </section>

      <!-- 列表 -->
      <div v-if="loading" class="grid">
        <div v-for="i in 6" :key="i" class="card poi-card">
          <div class="skeleton" style="height: 18px; width: 58%" />
          <div class="skeleton" style="height: 12px; width: 100%; margin-top: 12px" />
          <div class="skeleton" style="height: 12px; width: 78%; margin-top: 7px" />
          <div class="skeleton" style="height: 30px; width: 100%; margin-top: 18px" />
        </div>
      </div>

      <div v-else-if="!list.length" class="card empty">
        <div class="empty__icon"><Icon name="pin" :size="27" /></div>
        <div class="empty__title">没有匹配的景点</div>
        <p class="empty__desc">换个关键词或城市试试，或点击「重置」查看全部。</p>
      </div>

      <div v-else class="grid">
        <article v-for="p in list" :key="p.id" class="card card--solid card--hover poi-card">
          <div class="poi-card__top">
            <div class="poi-card__city">
              <Icon name="pin" :size="13" />
              {{ p.city_name }}
            </div>
            <div class="poi-card__tags">
              <span v-if="p.poi_rank_in_china" class="badge badge--brand">全国 #{{ p.poi_rank_in_china }}</span>
              <span v-if="p.poi_rank_in_city" class="badge badge--muted">本市 #{{ p.poi_rank_in_city }}</span>
            </div>
          </div>

          <h3 class="poi-card__name">{{ p.poi_name }}</h3>
          <p class="poi-card__desc">{{ p.poi_description || '暂无描述' }}</p>

          <div class="poi-card__meta">
            <span class="poi-card__price" :class="{ 'is-free': !(Number(p.ticket_price) > 0) }">
              <Icon name="coins" :size="13" />
              {{ priceText(p.ticket_price) }}
            </span>
            <span v-if="p.poi_longitude && p.poi_latitude" class="mono t3" style="font-size: 11px">
              {{ Number(p.poi_longitude).toFixed(2) }}, {{ Number(p.poi_latitude).toFixed(2) }}
            </span>
          </div>

          <div class="poi-card__ops">
            <button
              class="btn btn--ghost btn--sm"
              :class="{ 'is-fav': favIds.has(p.id) }"
              @click="toggleFav(p)"
            >
              <Icon name="heart" :size="14" />
              {{ favIds.has(p.id) ? '已收藏' : '收藏' }}
            </button>
            <template v-if="admin">
              <button class="btn btn--quiet btn--sm" title="编辑" @click="openEdit(p)">
                <Icon name="edit" :size="14" />
              </button>
              <button class="btn btn--quiet btn--sm danger" title="删除" @click="deleting = p">
                <Icon name="trash" :size="14" />
              </button>
            </template>
          </div>
        </article>
      </div>

      <!-- 分页 -->
      <div v-if="!loading && totalPages > 1" class="pager">
        <button class="btn btn--ghost btn--sm" :disabled="query.page <= 1" @click="goPage(query.page - 1)">
          <Icon name="chevronLeft" :size="14" /> 上一页
        </button>
        <span class="pager__info">{{ query.page }} / {{ totalPages }}</span>
        <button class="btn btn--ghost btn--sm" :disabled="query.page >= totalPages" @click="goPage(query.page + 1)">
          下一页 <Icon name="chevronRight" :size="14" />
        </button>
      </div>
    </div>

    <!-- 新增/编辑 -->
    <Modal
      v-model="showEditing"
      :title="editing?.mode === 'create' ? '新增景点' : '编辑景点'"
      subtitle="带 * 为必填项"
      width="620px"
    >
      <div class="grid-2">
        <div class="field">
          <label class="field__label">景点名称 *</label>
          <input v-model="form.poi_name" class="input" type="text" placeholder="如：故宫博物院" />
        </div>
        <div class="field">
          <label class="field__label">所在城市 *</label>
          <input v-model="form.city_name" class="input" type="text" placeholder="如：北京" list="city-list" />
          <datalist id="city-list">
            <option v-for="c in cities" :key="c" :value="c" />
          </datalist>
        </div>
      </div>

      <div class="field" style="margin-top: 14px">
        <label class="field__label">景点描述</label>
        <textarea v-model="form.poi_description" class="textarea" rows="3" placeholder="一句话介绍该景点" />
      </div>

      <div class="grid-2" style="margin-top: 14px">
        <div class="field">
          <label class="field__label">经度</label>
          <input v-model="form.poi_longitude" class="input" type="number" step="0.000001" placeholder="116.397" />
        </div>
        <div class="field">
          <label class="field__label">纬度</label>
          <input v-model="form.poi_latitude" class="input" type="number" step="0.000001" placeholder="39.918" />
        </div>
        <div class="field">
          <label class="field__label">本市排名</label>
          <input v-model="form.poi_rank_in_city" class="input" type="number" placeholder="1" />
        </div>
        <div class="field">
          <label class="field__label">全国排名</label>
          <input v-model="form.poi_rank_in_china" class="input" type="number" placeholder="1" />
        </div>
        <div class="field">
          <label class="field__label">门票价格（元，0 表示免费）</label>
          <input v-model="form.ticket_price" class="input" type="number" step="0.01" placeholder="60" />
        </div>
      </div>

      <template #footer>
        <button class="btn btn--ghost" @click="editing = null">取消</button>
        <button class="btn btn--primary" :disabled="saving" @click="save">
          <span v-if="saving" class="spinner" />
          {{ saving ? '保存中…' : '保存' }}
        </button>
      </template>
    </Modal>

    <!-- 删除确认 -->
    <Modal v-model="showDeleting" title="删除景点" width="420px">
      <p class="t2">
        确定要删除「<strong>{{ deleting?.poi_name }}</strong>」吗？该操作不可恢复。
      </p>
      <template #footer>
        <button class="btn btn--ghost" @click="deleting = null">取消</button>
        <button class="btn btn--danger" @click="doDelete">确认删除</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.page { height: 100%; overflow-y: auto; }

.page__inner {
  max-width: 1380px;
  margin: 0 auto;
  padding: 30px 32px 56px;
}

/* 筛选条 */
.filters {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 15px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}

.filters__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  flex: 1;
  min-width: 200px;
  height: 40px;
  padding: 0 13px;
  border-radius: var(--r-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--line);
  color: var(--t3);
}

.filters__search:focus-within {
  border-color: rgba(34, 211, 238, 0.45);
  background: rgba(34, 211, 238, 0.04);
}

.filters__input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  outline: none;
  font-size: 13.5px;
  color: var(--t1);
}

.filters__input::placeholder { color: var(--t4); }

/* 卡片网格 */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(288px, 1fr));
  gap: 16px;
}

.poi-card {
  display: flex;
  flex-direction: column;
  padding: 17px 18px 15px;
}

.poi-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 11px;
}

.poi-card__city {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 550;
  color: #A5F3FC;
  padding: 3px 9px;
  border-radius: var(--r-full);
  background: var(--grad-brand-soft);
  border: 1px solid rgba(34, 211, 238, 0.25);
}

.poi-card__tags { display: flex; gap: 5px; flex-wrap: wrap; }

.poi-card__name {
  font-size: 16px;
  font-weight: 660;
  letter-spacing: -0.2px;
  margin-bottom: 7px;
}

.poi-card__desc {
  flex: 1;
  font-size: 12.9px;
  line-height: 1.7;
  color: var(--t3);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.poi-card__meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 14px 0 12px;
}

.poi-card__price {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 620;
  color: #FCD34D;
}

.poi-card__price.is-free { color: var(--teal); }

.poi-card__ops {
  display: flex;
  align-items: center;
  gap: 7px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.poi-card__ops .btn:first-child { flex: 1; }

.btn.is-fav {
  color: #FCA5A5 !important;
  border-color: rgba(248, 113, 113, 0.34) !important;
  background: var(--danger-dim) !important;
}

.btn.danger:hover { color: var(--danger); background: var(--danger-dim); }

/* 分页 */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 26px;
}

.pager__info {
  font-size: 13px;
  color: var(--t3);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 720px) {
  .page__inner { padding: 22px 16px 44px; }
  .grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
