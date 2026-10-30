<script setup>
/**
 * 行程路线图
 * 优先加载高德 JS API（国内可用、有深色底图）；
 * 加载失败/超时则降级为按天分组的点位列表，保证功能不消失。
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  points: { type: Array, default: () => [] }
})
defineEmits(['close'])

const el = ref(null)
const status = ref('idle') // idle | loading | ready | failed
const failReason = ref('')
const activeDay = ref(0)

let map = null
let overlays = []

const KEY = import.meta.env.VITE_AMAP_API_KEY
const SECURITY = import.meta.env.VITE_AMAP_SECURITY_JS_CODE

const days = computed(() => {
  const set = [...new Set(props.points.map((p) => p.day))].sort((a, b) => a - b)
  return set
})

const visiblePoints = computed(() =>
  activeDay.value ? props.points.filter((p) => p.day === activeDay.value) : props.points
)

/* ---------------- 脚本加载 ---------------- */
let loadPromise = null

function loadAmap() {
  if (window.AMap) return Promise.resolve(window.AMap)
  if (loadPromise) return loadPromise
  if (!KEY) return Promise.reject(new Error('未配置 VITE_AMAP_API_KEY'))

  loadPromise = new Promise((resolve, reject) => {
    if (SECURITY) {
      window._AMapSecurityConfig = { securityJsCode: SECURITY }
    }
    const timer = setTimeout(() => reject(new Error('地图服务加载超时')), 9000)
    const s = document.createElement('script')
    s.src = `https://webapi.amap.com/maps?v=2.0&key=${KEY}`
    s.async = true
    s.onload = () => {
      clearTimeout(timer)
      window.AMap ? resolve(window.AMap) : reject(new Error('地图脚本已加载但对象不可用'))
    }
    s.onerror = () => {
      clearTimeout(timer)
      reject(new Error('地图脚本请求失败（可能被网络拦截）'))
    }
    document.head.appendChild(s)
  })
  return loadPromise
}

/* ---------------- 渲染 ---------------- */
function clearOverlays() {
  if (map && overlays.length) map.remove(overlays)
  overlays = []
}

function render() {
  if (!map) return
  // 先清空旧覆盖物：切换到无点位会话时地图不能残留上一个行程的标记
  clearOverlays()
  if (!visiblePoints.value.length) return

  const AMap = window.AMap
  const pts = visiblePoints.value

  pts.forEach((p, i) => {
    const marker = new AMap.Marker({
      position: [p.lng, p.lat],
      title: p.name,
      anchor: 'center',
      content: `<div class="amap-dot" data-i="${i + 1}">${i + 1}</div>`,
      offset: new AMap.Pixel(-13, -13)
    })
    marker.setLabel({
      direction: 'bottom',
      offset: new AMap.Pixel(0, 6),
      content: `<div class="amap-label">${p.name}</div>`
    })
    overlays.push(marker)
  })

  if (pts.length > 1) {
    overlays.push(
      new AMap.Polyline({
        path: pts.map((p) => [p.lng, p.lat]),
        strokeColor: '#0B6B63',
        strokeWeight: 3,
        strokeOpacity: 0.9,
        strokeStyle: 'solid',
        lineJoin: 'round',
        showDir: true
      })
    )
  }

  map.add(overlays)
  map.setFitView(overlays, false, [70, 70, 70, 70], 15)
}

async function boot() {
  if (!props.points.length) return
  status.value = 'loading'
  try {
    await loadAmap()
    await nextTick()
    if (!el.value) return

    map = new window.AMap.Map(el.value, {
      zoom: 6,
      center: [props.points[0].lng, props.points[0].lat],
      mapStyle: 'amap://styles/normal',
      viewMode: '2D',
      zooms: [3, 18]
    })
    status.value = 'ready'
    render()
  } catch (e) {
    status.value = 'failed'
    failReason.value = e.message || '地图初始化失败'
  }
}

onMounted(boot)

watch(
  () => props.points,
  () => {
    if (status.value === 'ready') render()
    else if (status.value === 'failed' || status.value === 'idle') boot()
  },
  { deep: true }
)

watch(activeDay, () => {
  if (status.value === 'ready') render()
})

onUnmounted(() => {
  clearOverlays()
  map?.destroy()
  map = null
})
</script>

<template>
  <aside class="map" :class="{ 'is-empty': !points.length }">
    <header class="map__head">
      <div class="map__title">
        <Icon name="route" :size="16" />
        <span>行程路线</span>
      </div>
      <button class="map__x" aria-label="关闭" @click="$emit('close')">
        <Icon name="close" :size="15" />
      </button>
    </header>

    <div v-if="days.length > 1" class="map__days">
      <button class="map__day" :class="{ 'is-on': activeDay === 0 }" @click="activeDay = 0">
        全部
      </button>
      <button
        v-for="d in days"
        :key="d"
        class="map__day"
        :class="{ 'is-on': activeDay === d }"
        @click="activeDay = d"
      >
        D{{ d }}
      </button>
    </div>

    <div class="map__canvas-wrap" :class="{ 'is-empty': !points.length }">
      <!-- 无坐标点位时的占位（尚未生成行程 / 该会话无路线） -->
      <div v-if="!points.length" class="map__overlay">
        <div class="map__fb-icon"><Icon name="compass" :size="24" /></div>
        <p class="map__fb-title">路线图待生成</p>
        <p class="map__fb-desc">在左侧描述旅行需求（目的地 / 天数 / 预算），<br />生成行程后这里会自动标注每日景点与路线</p>
      </div>

      <div v-else-if="status !== 'failed'" ref="el" class="map__canvas" />

      <div v-if="status === 'loading'" class="map__overlay">
        <span class="spinner" style="width: 22px; height: 22px; border-width: 2.4px" />
        <p>正在加载地图…</p>
      </div>

      <div v-if="status === 'failed'" class="map__fallback">
        <div class="map__fb-icon"><Icon name="pin" :size="24" /></div>
        <p class="map__fb-title">地图不可用</p>
        <p class="map__fb-desc">{{ failReason }}</p>
        <p class="map__fb-hint">已改为点位清单展示，行程内容不受影响。</p>
      </div>
    </div>

    <!-- 点位清单（始终展示，作为地图的补充与降级） -->
    <div class="map__list">
      <div v-for="(p, i) in visiblePoints" :key="`${p.name}-${i}`" class="poi">
        <span class="poi__idx">{{ i + 1 }}</span>
        <div class="poi__body">
          <div class="poi__name truncate">{{ p.name }}</div>
          <div class="poi__meta">
            <span v-if="p.city">{{ p.city }}</span>
            <span v-if="p.day" class="poi__day">D{{ p.day }}</span>
          </div>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.map {
  width: 380px;
  flex: none;
  display: flex;
  flex-direction: column;
  border-left: 1px solid var(--line);
  background: var(--paper);
}

.map__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 58px;
  flex: none;
  padding: 0 16px;
  border-bottom: 1px solid var(--line-faint);
}

.map__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: -0.012em;
}

.map__title svg { color: var(--ink-3); }

.map__x {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  color: var(--ink-3);
  border-radius: var(--r-xs);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.map__x:hover { color: var(--ink); background: var(--paper-2); }

.map__days {
  display: flex;
  gap: 4px;
  padding: 12px 16px 0;
  flex-wrap: wrap;
  flex: none;
}

.map__day {
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-xs);
  font-size: 11.5px;
  font-family: var(--font-mono);
  color: var(--ink-3);
  border: 1px solid var(--line);
  background: var(--surface);
  transition: color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    background var(--dur) var(--ease);
}

.map__day:hover { color: var(--ink); border-color: var(--line-strong); }

.map__day.is-on {
  color: #FCFBF7;
  border-color: var(--ink);
  background: var(--ink);
}

.map__canvas-wrap {
  position: relative;
  height: 264px;
  margin: 12px 16px;
  border-radius: var(--r-md);
  overflow: hidden;
  border: 1px solid var(--line);
  background: #EFEDE5;
  flex: none;
}

/* 无路线时让占位区吃掉剩余高度，避免面板下半部空荡 */
.map__canvas-wrap.is-empty {
  flex: 1;
  min-height: 240px;
  height: auto;
}

/* 空态下点位清单没有内容，不再占位 */
.map.is-empty .map__list {
  flex: none;
  padding-bottom: 0;
}

.map__canvas { width: 100%; height: 100%; }

.map__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 20px;
  text-align: center;
  font-size: 12.5px;
  color: var(--ink-3);
  background: var(--surface);
}

.map__fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 20px;
  text-align: center;
}

.map__fb-icon {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink-3);
  margin-bottom: 4px;
}

.map__fb-title { font-size: 13px; font-weight: 600; color: var(--ink-2); }
.map__fb-desc { font-size: 11.5px; color: var(--ink-3); line-height: 1.65; }
.map__fb-hint { font-size: 11px; color: var(--ink-4); }

.map__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 10px 16px;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.map__none {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 10px;
  font-size: 12px;
  color: var(--ink-4);
  line-height: 1.6;
}

.poi {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 9px;
  border-radius: var(--r-sm);
  transition: background var(--dur) var(--ease);
}

.poi:hover { background: var(--surface); }

.poi__idx {
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  flex: none;
  border-radius: 50%;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 500;
  color: #FCFBF7;
  background: var(--accent);
}

.poi__body { min-width: 0; flex: 1; }

.poi__name { font-size: 12.5px; color: var(--ink); }

.poi__meta {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: var(--ink-4);
  margin-top: 1px;
}

.poi__day {
  padding: 0 5px;
  border-radius: 3px;
  background: var(--paper-2);
  border: 1px solid var(--line);
  color: var(--ink-3);
  font-family: var(--font-mono);
  font-size: 10px;
}

@media (max-width: 1320px) {
  .map { width: 330px; }
}

@media (max-width: 1080px) {
  .map { display: none; }
}
</style>

<style>
/* 高德 Marker 自定义内容（非 scoped：由 AMap 注入到地图容器内） */
.amap-dot {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: "Geist Mono", ui-monospace, monospace;
  font-size: 11px;
  font-weight: 500;
  color: #FCFBF7;
  background: #0B6B63;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.9), 0 2px 8px rgba(23, 22, 15, 0.28);
}

.amap-label {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  white-space: nowrap;
  color: #17160F;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid #E3E0D5;
  box-shadow: 0 1px 3px rgba(23, 22, 15, 0.12);
}

.amap-info-content {
  background: #FFFFFF !important;
  color: #17160F !important;
  border: 1px solid #E3E0D5 !important;
  border-radius: 8px !important;
}
</style>
