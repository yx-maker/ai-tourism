<script setup>
import { toastState, dismiss } from '../stores/toast.js'
import Icon from './Icon.vue'

const ICONS = { success: 'check', error: 'alert', warn: 'alert', info: 'info' }
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toastState.items" :key="t.id" class="toast" :class="`toast--${t.type}`">
        <span class="toast__icon">
          <Icon :name="ICONS[t.type] || 'info'" :size="15" />
        </span>
        <div class="toast__body">
          <div v-if="t.title" class="toast__title">{{ t.title }}</div>
          <div class="toast__msg">{{ t.message }}</div>
        </div>
        <button class="toast__x" aria-label="关闭" @click="dismiss(t.id)">
          <Icon name="close" :size="13" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  bottom: 22px;
  right: 18px;
  z-index: 9000;
  display: flex;
  flex-direction: column-reverse;
  gap: 10px;
  width: min(370px, calc(100vw - 36px));
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 12px 13px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--sh-2);
}

.toast__icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: var(--r-xs);
  flex: none;
  margin-top: 1px;
}

.toast--success .toast__icon { background: var(--ok-dim); color: var(--ok); }
.toast--error .toast__icon { background: var(--danger-dim); color: var(--danger); }
.toast--warn .toast__icon { background: var(--warn-dim); color: var(--warn); }
.toast--info .toast__icon { background: var(--info-dim); color: var(--info); }

.toast__body { flex: 1; min-width: 0; }

.toast__title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 2px;
}

.toast__msg {
  font-size: 13px;
  color: var(--t2);
  line-height: 1.55;
  word-break: break-word;
}

.toast__x {
  color: var(--t4);
  padding: 3px;
  border-radius: var(--r-xs);
  flex: none;
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.toast__x:hover { color: var(--t1); background: var(--glass-hover); }

.toast-enter-active { transition: all 0.28s var(--ease-out); }
.toast-leave-active { transition: all 0.2s var(--ease); position: absolute; width: 100%; }
.toast-enter-from { opacity: 0; transform: translateX(28px) scale(0.96); }
.toast-leave-to { opacity: 0; transform: translateX(20px); }
.toast-move { transition: transform 0.28s var(--ease); }

/* 窄屏底部就是输入框，通知改挂到导航下方，避免挡住打字 */
@media (max-width: 780px) {
  .toasts {
    top: 68px;
    bottom: auto;
    right: 12px;
    width: calc(100vw - 24px);
    flex-direction: column;
  }
}
</style>
