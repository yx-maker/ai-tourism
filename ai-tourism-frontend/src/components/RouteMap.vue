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
        strokeColor: '#22D3EE',
        strokeWeight: 3,
        strokeOpacity: 0.85,
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
      mapStyle: 'amap://styles/dark',
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
  <aside class="map">
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

    <div class="map__canvas-wrap">
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
      <div v-if="!points.length" class="map__none">
        <Icon name="info" :size="16" />
        <span>该会话尚未生成带坐标的路线</span>
      </div>

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
  background: rgba(8, 11, 20, 0.62);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.map__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 15px 16px;
  border-bottom: 1px solid var(--line);
}

.map__title {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 14px;
  font-weight: 620;
}

.map__title svg { color: var(--cyan); }

.map__x {
  color: var(--t3);
  padding: 5px;
  border-radius: var(--r-xs);
}

.map__x:hover { color: var(--t1); background: var(--glass-hover); }

.map__days {
  display: flex;
  gap: 5px;
  padding: 11px 16px 0;
  flex-wrap: wrap;
}

.map__day {
  height: 27px;
  padding: 0 11px;
  border-radius: var(--r-full);
  font-size: 12.5px;
  color: var(--t3);
  border: 1px solid var(--line);
  background: var(--glass);
  transition: all var(--dur) var(--ease);
}

.map__day:hover { color: var(--t1); border-color: var(--line-strong); }

.map__day.is-on {
  color: #CFFAFE;
  border-color: rgba(34, 211, 238, 0.4);
  background: var(--grad-brand-soft);
}

.map__canvas-wrap {
  position: relative;
  height: 268px;
  margin: 12px 16px;
  border-radius: var(--r-md);
  overflow: hidden;
  border: 1px solid var(--line);
  background: #0A0F1C;
  flex: none;
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
  font-size: 13px;
  color: var(--t3);
  background: rgba(10, 15, 28, 0.9);
}

.map__fallback {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 20px;
  text-align: center;
}

.map__fb-icon {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  border-radius: var(--r-md);
  background: var(--glass);
  border: 1px solid var(--line);
  color: var(--t3);
  margin-bottom: 4px;
}

.map__fb-title { font-size: 13.5px; font-weight: 600; color: var(--t2); }
.map__fb-desc { font-size: 12px; color: var(--t3); line-height: 1.6; }
.map__fb-hint { font-size: 11.5px; color: var(--t4); }

.map__list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.map__none {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 18px 12px;
  font-size: 12.8px;
  color: var(--t4);
}

.poi {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  transition: background var(--dur) var(--ease);
}

.poi:hover { background: var(--glass-hover); }

.poi__idx {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  flex: none;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 700;
  color: #CFFAFE;
  background: rgba(34, 211, 238, 0.15);
  border: 1px solid rgba(34, 211, 238, 0.35);
}

.poi__body { min-width: 0; flex: 1; }

.poi__name { font-size: 13px; color: var(--t1); }

.poi__meta {
  display: flex;
  gap: 7px;
  font-size: 11.5px;
  color: var(--t4);
  margin-top: 2px;
}

.poi__day {
  padding: 0 6px;
  border-radius: var(--r-full);
  background: rgba(168, 85, 247, 0.14);
  color: #D8B4FE;
}

@media (max-width: 1280px) {
  .map { width: 320px; }
}

@media (max-width: 1080px) {
  .map { display: none; }
}
</style>

<style>
/* 高德 Marker 自定义内容（非 scoped，因为由 AMap 注入到地图容器内） */
.amap-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 11.5px;
  font-weight: 700;
  color: #05070D;
  background: linear-gradient(135deg, #22D3EE, #6366F1);
  box-shadow: 0 0 0 3px rgba(34, 211, 238, 0.22), 0 4px 14px -4px rgba(0, 0, 0, 0.8);
}

.amap-label {
  padding: 2px 7px;
  border-radius: 5px;
  font-size: 11px;
  white-space: nowrap;
  color: #E9EFFA;
  background: rgba(12, 17, 28, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.14);
}

.amap-info-content {
  background: rgba(12, 17, 28, 0.96) !important;
  color: #E9EFFA !important;
  border: 1px solid rgba(255, 255, 255, 0.14) !important;
  border-radius: 10px !important;
}
</style>
