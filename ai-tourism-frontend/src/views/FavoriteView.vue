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
        <div class="empty__icon"><Icon name="heart" :size="22" /></div>
        <div class="empty__title">还没有收藏任何景点</div>
        <p class="empty__desc">
          去「景点库」浏览带真实票价的景点，点卡片右上角的收藏图标即可出现在这里。
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
                  {{ detail(f) ? priceText(detail(f).ticket_price) : '—' }}
                </span>
                <span class="fav-card__side mono">
                  <template v-if="detail(f)?.poi_rank_in_china">全国 #{{ detail(f).poi_rank_in_china }} · </template>
                  {{ fmtDate(f.created_time) }}
                </span>
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
.page { height: 100%; overflow-y: auto; background: var(--paper); }

.page__inner {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 30px 32px 64px;
}

.group { margin-bottom: 32px; }

/* 城市分组：一行标签 + 一条通到底的线，不用高亮胶囊 */
.group__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}

.group__city {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}

.group__city svg { color: var(--ink-4); }

.group__count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--paper-2);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 14px;
}

.fav-card {
  display: flex;
  flex-direction: column;
  padding: 14px 16px 15px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  transition: border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease);
}

.fav-card:hover {
  border-color: var(--line-strong);
  box-shadow: var(--sh-1);
}

.fav-card__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.fav-card__name {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.35;
  color: var(--ink);
}

.fav-card__x {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  flex: none;
  border-radius: var(--r-xs);
  color: var(--ink-4);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.fav-card__x:hover { color: var(--danger); background: var(--danger-dim); }

.fav-card__desc {
  flex: 1;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-3);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.fav-card__meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 9px;
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 11px;
  border-top: 1px solid var(--line-faint);
}

.fav-card__price {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
}

.fav-card__price.is-free { color: var(--accent-text); }

.fav-card__side {
  margin-left: auto;
  font-size: 11px;
  color: var(--ink-4);
}

@media (max-width: 720px) {
  .page__inner { padding: 22px 16px 48px; }
  .grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
