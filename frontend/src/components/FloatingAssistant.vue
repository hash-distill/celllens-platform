<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { assistantOpen, assistantSelection, assistantSource } from '../stores/assistantSource'
import { taskName } from '../utils/biologyLocale'
import AssistantPanel from './AssistantPanel.vue'
import UiIcon from './UiIcon.vue'

const route = useRoute()
const closeButton = ref<HTMLButtonElement | null>(null)
let returnFocus: HTMLElement | null = null
const focusLabel = computed(() => {
  const focus = assistantSelection.value
  if (assistantSource.value?.kind === 'measured') {
    const label = focus.view === 'genes' ? '实测基因表达变化' : focus.view === 'metabolism' ? '实测表达派生代谢评分' : '本次实测分析'
    return focus.feature_id ? `${label} · ${focus.feature_kind === 'task' ? taskName(focus.feature_id) : focus.feature_id}` : label
  }
  if (focus.view === 'chart') return `${focus.space === 'metabolic' ? '代谢' : '表达'} ${(focus.embedding ?? 'pca').toUpperCase()} · ${focus.feature_kind === 'task' ? taskName(focus.feature_id ?? '') : focus.feature_id}`
  return {overview:'本次实验', genes:'基因表达变化', metabolism:'代谢任务变化', comparison:'预测与实测比较'}[focus.view]
})
watch(assistantOpen, async open => {
  if (open) {returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null; await nextTick(); if (assistantOpen.value) closeButton.value?.focus()}
})
function close() {
  assistantOpen.value = false
  if (returnFocus?.isConnected) returnFocus.focus()
  else document.querySelector<HTMLButtonElement>('.utility-rail button[aria-label="AI 解读"]')?.focus()
}
function onKey(event: KeyboardEvent) {
  if (assistantOpen.value && event.key === 'Escape' && !event.defaultPrevented) {event.preventDefault(); close()}
}
watch(() => route.path, path => {if (path === '/settings' && assistantOpen.value) close()})
document.addEventListener('keydown', onKey)
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>
<template>
  <section v-show="assistantOpen" id="assistant-dialog" class="assistant-dialog" role="dialog" aria-modal="false" aria-label="AI 科研解读">
    <header class="floating-heading"><div><span class="eyebrow">RESEARCH ASSISTANT</span><h2><UiIcon name="sparkle" :size="18" />AI 科研解读</h2></div><button ref="closeButton" class="close-assistant" type="button" aria-label="收起 AI 解读" title="收起 AI 解读 · Esc" @click="close">×</button></header>
    <div class="floating-body">
      <template v-if="assistantSource">
        <div class="floating-source"><span>{{ assistantSource.kind === 'measured' ? '当前实测分析' : '当前预测实验' }}</span><strong>{{ assistantSource.title }}</strong><p class="focus-label">{{ focusLabel }}</p></div>
        <AssistantPanel v-if="assistantSource.completed" :source-kind="assistantSource.kind" :source-id="assistantSource.id" :selection="assistantSelection" />
        <div v-else class="assistant-empty"><h3>分析完成后即可解读</h3><p>结果保存后，可以在这里预览摘要并生成解读。</p></div>
      </template>
      <div v-else class="assistant-empty"><UiIcon name="chart" :size="30" /><h3>选择一份结果，开始解读</h3><p>打开实测分析或预测结果后，可解释基因表达与代谢任务变化，并提出后续验证建议。</p><RouterLink to="/records" class="btn btn-primary" @click="close">选择结果</RouterLink><RouterLink to="/settings#model-connection" class="assistant-settings" @click="close">配置大模型连接 →</RouterLink></div>
    </div>
    <footer>AI 辅助解读 · 结论请结合原始数据核对</footer>
  </section>
</template>
<style scoped>
.assistant-dialog{position:fixed;right:66px;top:94px;bottom:22px;width:440px;max-height:calc(100dvh - 116px);z-index:64;display:flex;flex-direction:column;background:var(--card);color:var(--ink);border:1px solid var(--border-strong);border-radius:8px;box-shadow:var(--shadow-lg);overflow:hidden}
.floating-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:20px 22px;border-bottom:1px solid var(--border);flex:none}.floating-heading .eyebrow{font-size:10px;letter-spacing:.13em;color:var(--primary)}.floating-heading h2{display:flex;align-items:center;gap:9px;font-size:19px;font-weight:500;margin:8px 0 0}.close-assistant{width:34px;height:34px;border:1px solid var(--border);border-radius:50%;background:transparent;color:var(--muted);font-size:23px;cursor:pointer}.close-assistant:hover{background:var(--surface-soft)}.close-assistant:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.floating-body{overflow-y:auto;overscroll-behavior:contain;min-height:0;padding:20px 22px}.floating-source{padding:14px 16px;margin-bottom:20px;background:var(--surface-soft);border-left:2px solid var(--primary)}.floating-source>span{font-size:11px;color:var(--muted);display:block;margin-bottom:6px}.floating-source strong{font-size:14px;font-weight:500}.focus-label{font-size:12px;color:var(--primary);margin:8px 0 0;overflow-wrap:anywhere}.assistant-empty{padding:18px 0}.assistant-empty>svg{color:var(--primary)}.assistant-empty h3{font-size:20px;font-weight:500;margin:18px 0 12px}.assistant-empty p{font-size:13px;color:var(--muted);line-height:1.9;margin-bottom:24px}.assistant-settings{display:block;font-size:12px;margin-top:20px}.assistant-dialog>footer{border-top:1px solid var(--border);padding:11px 22px;font-size:10px;color:var(--muted);flex:none}
</style>
