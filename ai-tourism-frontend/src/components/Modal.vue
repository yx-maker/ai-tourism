<script setup>
import { watch, onUnmounted } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  width: { type: String, default: '520px' },
  closeOnBackdrop: { type: Boolean, default: true }
})

const emit = defineEmits(['update:modelValue'])

function close() {
  emit('update:modelValue', false)
}

function onKey(e) {
  if (e.key === 'Escape') close()
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      document.addEventListener('keydown', onKey)
      document.body.style.overflow = 'hidden'
    } else {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }
)

onUnmounted(() => {
  document.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="mask" @click.self="closeOnBackdrop && close()">
        <div class="modal" :style="{ width }" role="dialog" aria-modal="true">
          <header class="modal__head">
            <div>
              <h3 class="modal__title">{{ title }}</h3>
              <p v-if="subtitle" class="modal__sub">{{ subtitle }}</p>
            </div>
            <button class="modal__x" aria-label="关闭" @click="close">
              <Icon name="close" :size="16" />
            </button>
          </header>
          <div class="modal__body">
            <slot />
          </div>
          <footer v-if="$slots.footer" class="modal__foot">
            <slot name="footer" />
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 8000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(3, 5, 10, 0.72);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.modal {
  max-width: 100%;
  max-height: 86vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(20, 27, 48, 0.98), rgba(11, 16, 32, 0.98));
  border: 1px solid var(--line-strong);
  border-radius: var(--r-xl);
  box-shadow: var(--sh-3);
  overflow: hidden;
}

.modal__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid var(--line);
}

.modal__title {
  font-size: 16px;
  font-weight: 680;
  letter-spacing: -0.2px;
}

.modal__sub {
  margin-top: 4px;
  font-size: 12.5px;
  color: var(--t3);
}

.modal__x {
  color: var(--t3);
  padding: 6px;
  border-radius: var(--r-xs);
  transition: color var(--dur) var(--ease), background var(--dur) var(--ease);
}

.modal__x:hover { color: var(--t1); background: var(--glass-hover); }

.modal__body {
  padding: 20px 22px;
  overflow-y: auto;
}

.modal__foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 15px 22px 19px;
  border-top: 1px solid var(--line);
  background: rgba(0, 0, 0, 0.18);
}

.modal-enter-active { transition: opacity 0.22s var(--ease); }
.modal-leave-active { transition: opacity 0.16s var(--ease); }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-active .modal { transition: transform 0.28s var(--ease-out); }
.modal-enter-from .modal { transform: scale(0.95) translateY(14px); }
</style>
