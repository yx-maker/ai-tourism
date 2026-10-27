<script setup>
/**
 * Markdown 渲染：marked 解析 + DOMPurify 消毒
 * 行程正文含大量标题/列表/表格，必须消毒后再 v-html
 */
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const props = defineProps({
  source: { type: String, default: '' },
  /** 流式输出中：显示闪烁光标 */
  streaming: { type: Boolean, default: false }
})

marked.setOptions({ gfm: true, breaks: true })

const html = computed(() => {
  const raw = props.source || ''
  if (!raw) return ''
  let out
  try {
    out = marked.parse(raw)
  } catch {
    // 解析失败（极少数不完整语法）时退化为纯文本展示，避免整条消息消失
    return DOMPurify.sanitize(
      `<p>${raw.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>')}</p>`
    )
  }
  return DOMPurify.sanitize(out, {
    ADD_ATTR: ['target', 'rel'],
    FORBID_TAGS: ['style', 'iframe', 'form', 'input', 'button'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick']
  })
})
</script>

<template>
  <div class="md" :class="{ 'md-caret': streaming }" v-html="html" />
</template>
