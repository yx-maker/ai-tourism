<script setup>
import { ref, computed, onMounted } from 'vue'
import Icon from '../components/Icon.vue'
import Modal from '../components/Modal.vue'
import { favoriteApi, poiApi } from '../api/index.js'
import { toast, errText } from '../stores/toast.js'

const list = ref([])
const poiMap = ref({})
const loading = ref(false)
const removing = ref(null)

// v-model 只接受成员表达式，不能写 !!xxx，用可写 computed 桥接
const showRemoving = computed({
  get: () => !!removing.value,
  set: (v) => {
    if (!v) removing.value = null
  }
})

const cityGroups = computed(() => {
  const m = new Map()
  list.value.forEach((f) => {
    const c = f.city_name || '其他'
    if (!m.has(c)) m.set(c, [])
    m.get(c).push(f)
  })
  return [...m.entries()].sort((a, b) => b[1].length - a[1].length)
})

function detail(f) {
  return poiMap.value[f.poi_id] || null
}

function priceText(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return '免费'
  return `¥${n}`
}

function fmtDate(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 10)
}

async function load() {
  loading.value = true
  try {
    const [favs, page] = await Promise.all([
      favoriteApi.list(),
      poiApi.page({ page: 1, pageSize: 200 }).catch(() => ({ list: [] }))
    ])
    list.value = favs || []
    const m = {}
    ;(page.list || []).forEach((p) => {
      m[p.id] = p
    })
    poiMap.value = m
  } catch (e) {
    toast.error(errText(e, '收藏列表加载失败'))
    list.value = []
  } finally {
    loading.value = false
  }
}

async function doRemove() {
  const f = removing.value
  try {
    await favoriteApi.remove(f.poi_id)
    list.value = list.value.filter((x) => x.poi_id !== f.poi_id)
    toast.success('已取消收藏')
  } catch (e) {
    toast.error(errText(e, '取消收藏失败'))
  } finally {
    removing.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page__inner">
      <header class="page-head">
        <div>
          <h1 class="page-head__title">我的收藏</h1>
          <p class="page-head__sub">
            已收藏 <strong>{{ list.length }}</strong> 个景点
            <template v-if="cityGroups.length"> · 分布在 {{ cityGroups.length }} 个城市</template>
          </p>
        </div>
        <RouterLink to="/poi" class="btn btn--primary">
          <Icon name="pin" :size="15" /> 去景点库
        </RouterLink>
      </header>

      <div v-if="loading" class="grid">
        <div v-for="i in 4" :key="i" class="card fav-card">
          <div class="skeleton" style="height: 17px; width: 55%" />
          <div class="skeleton" style="height: 12px; width: 90%; margin-top: 12px" />
          <div class="skeleton" style="height: 30px; width: 100%; margin-top: 18px" />
        </div>
      </div>

      <div v-else-if="!list.length" class="card empty">
        <div class="empty__icon"><Icon name="heart" :size="27" /></div>
        <div class="empty__title">还没有收藏任何景点</div>
        <p class="empty__desc">
          去「景点库」浏览 118 条真实 POI，点击卡片上的「收藏」即可加入这里。
        </p>
        <RouterLink to="/poi" class="btn btn--primary" style="margin-top: 4px">
          <Icon name="pin" :size="15" /> 浏览景点库
        </RouterLink>
      </div>

      <template v-else>
        <section v-for="[city, items] in cityGroups" :key="city" class="group">
          <div class="group__head">
            <span class="group__city"><Icon name="pin" :size="13" /> {{ city }}</span>
            <span class="group__count">{{ items.length }} 个</span>
          </div>

          <div class="grid">
            <article v-for="f in items" :key="f.id" class="card card--solid card--hover fav-card">
              <div class="fav-card__top">
                <h3 class="fav-card__name">{{ f.poi_name }}</h3>
                <button class="fav-card__x" title="取消收藏" @click="removing = f">
                  <Icon name="trash" :size="14" />
                </button>
              </div>

              <p class="fav-card__desc">{{ detail(f)?.poi_description || '暂无描述' }}</p>

              <div class="fav-card__meta">
                <span class="fav-card__price" :class="{ 'is-free': !(Number(detail(f)?.ticket_price) > 0) }">
                  <Icon name="coins" :size="13" />
                  {{ detail(f) ? priceText(detail(f).ticket_price) : '—' }}
                </span>
                <span v-if="detail(f)?.poi_rank_in_china" class="badge badge--brand">
                  全国 #{{ detail(f).poi_rank_in_china }}
                </span>
                <span class="fav-card__date">{{ fmtDate(f.created_time) }} 收藏</span>
              </div>
            </article>
          </div>
        </section>
      </template>
    </div>

    <Modal v-model="showRemoving" title="取消收藏" width="420px">
      <p class="t2">
        确定要取消收藏「<strong>{{ removing?.poi_name }}</strong>」吗？
      </p>
      <template #footer>
        <button class="btn btn--ghost" @click="removing = null">取消</button>
        <button class="btn btn--danger" @click="doRemove">确认取消</button>
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

.group { margin-bottom: 30px; }

.group__head {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 13px;
}

.group__city {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  font-weight: 620;
  color: #CFFAFE;
  padding: 5px 12px;
  border-radius: var(--r-full);
  background: var(--grad-brand-soft);
  border: 1px solid rgba(34, 211, 238, 0.26);
}

.group__count { font-size: 12.5px; color: var(--t4); }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(288px, 1fr));
  gap: 15px;
}

.fav-card {
  display: flex;
  flex-direction: column;
  padding: 16px 18px 14px;
}

.fav-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.fav-card__name {
  font-size: 15.5px;
  font-weight: 650;
  letter-spacing: -0.2px;
}

.fav-card__x {
  display: grid;
  place-items: center;
  width: 27px;
  height: 27px;
  flex: none;
  border-radius: var(--r-xs);
  color: var(--t4);
  transition: all var(--dur) var(--ease);
}

.fav-card__x:hover { color: var(--danger); background: var(--danger-dim); }

.fav-card__desc {
  flex: 1;
  font-size: 12.8px;
  line-height: 1.68;
  color: var(--t3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fav-card__meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.fav-card__price {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.8px;
  font-weight: 620;
  color: #FCD34D;
}

.fav-card__price.is-free { color: var(--teal); }

.fav-card__date {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--t4);
}

@media (max-width: 720px) {
  .page__inner { padding: 22px 16px 44px; }
  .grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
