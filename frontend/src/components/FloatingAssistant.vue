<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { assistantSource } from '../stores/assistantSource'
import AssistantPanel from './AssistantPanel.vue'
import UiIcon from './UiIcon.vue'

const open = ref(false)
const launcher = ref<HTMLButtonElement | null>(null), closeButton = ref<HTMLButtonElement | null>(null)
async function toggle() {
  open.value = !open.value
  await nextTick()
  if (open.value) closeButton.value?.focus()
  else launcher.value?.focus()
}
function close() {open.value = false; launcher.value?.focus()}
function onKey(event: KeyboardEvent) {
  if (open.value && event.key === 'Escape' && !event.defaultPrevented) {event.preventDefault(); close()}
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>
<template>
  <aside class="floating-assistant" aria-label="AI 解读工具">
    <section v-show="open" id="floating-assistant-dialog" class="assistant-dialog" role="dialog" aria-label="AI 实验解读">
      <header class="floating-heading"><div><span class="eyebrow">CELLLENS ASSISTANT</span><h2><UiIcon name="sparkle" :size="18" />AI 实验解读</h2></div><button ref="closeButton" class="close-assistant" type="button" aria-label="收起 AI 解读" title="收起 AI 解读" @click="close">−</button></header>
      <div class="floating-body">
        <template v-if="assistantSource"><div class="floating-source"><span>当前实验</span><strong>{{ assistantSource.title }}</strong><code>{{ assistantSource.id }}</code></div>
          <AssistantPanel v-if="assistantSource.completed" :key="assistantSource.kind + ':' + assistantSource.id" :source-kind="assistantSource.kind" :source-id="assistantSource.id" />
          <div v-else class="assistant-empty"><h3>实验完成后即可解读</h3><p>当前实验尚未完成。结果保存后，可以在这里预览摘要并生成 AI 解读。</p></div>
        </template>
        <div v-else class="assistant-empty"><UiIcon name="file" :size="28" /><h3>打开一个实验，开始解读。</h3><p>从实验记录选择在线实验，AI 会根据这次实验的结果辅助解释变化、覆盖范围与后续验证。</p><RouterLink to="/records" class="btn btn-primary" @click="close">选择实验</RouterLink><RouterLink to="/settings#model-connection" class="assistant-settings" @click="close">配置大模型连接 →</RouterLink></div>
      </div>
    </section>
    <button ref="launcher" class="assistant-launcher" type="button" aria-label="AI 解读" aria-controls="floating-assistant-dialog" :aria-expanded="open" @click="toggle"><UiIcon name="sparkle" :size="21" /><span>AI 解读</span><i v-if="assistantSource?.completed" aria-hidden="true" /></button>
  </aside>
</template>
<style scoped>
.floating-assistant{position:fixed;right:24px;bottom:24px;z-index:65}.assistant-launcher{display:flex;align-items:center;justify-content:center;gap:10px;min-height:50px;padding:0 20px;border:1px solid var(--primary);border-radius:25px;background:var(--primary);color:var(--card);box-shadow:var(--shadow-lg);font:500 14px var(--font);cursor:pointer}.assistant-launcher:hover{background:var(--primary-strong)}.assistant-launcher i{width:6px;height:6px;border-radius:50%;background:var(--card);opacity:.75}.assistant-launcher:focus-visible,.close-assistant:focus-visible{outline:2px solid var(--primary);outline-offset:4px}.assistant-dialog{position:absolute;right:0;bottom:66px;width:440px;max-height:min(720px,calc(100vh - 150px));display:flex;flex-direction:column;background:var(--card);color:var(--ink);border:1px solid var(--border-strong);border-radius:10px;box-shadow:var(--shadow-lg);overflow:hidden}.floating-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:19px 22px;border-bottom:1px solid var(--border);flex:none}.floating-heading .eyebrow{font-size:9px;letter-spacing:.13em;color:var(--primary)}.floating-heading h2{display:flex;align-items:center;gap:8px;font-size:17px;font-weight:500;margin:8px 0 0}.close-assistant{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border:1px solid var(--border);border-radius:50%;background:transparent;color:var(--muted);font-size:23px;cursor:pointer}.close-assistant:hover{background:var(--surface-soft)}.floating-body{overflow-y:auto;overscroll-behavior:contain;min-height:0;padding:20px 22px}.floating-source{display:flex;flex-direction:column;gap:8px;margin-bottom:18px;padding:14px;background:var(--surface-soft);border-left:2px solid var(--primary)}.floating-source span{font-size:10px;color:var(--muted)}.floating-source strong{font-size:13px;font-weight:500;overflow-wrap:anywhere}.floating-source code{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.assistant-empty{padding:12px 0 16px}.assistant-empty>svg{color:var(--primary)}.assistant-empty h3{font-size:19px;font-weight:500;margin:16px 0 12px}.assistant-empty p{font-size:12px;color:var(--muted);line-height:1.9;margin-bottom:22px}.assistant-settings{display:block;font-size:11px;margin-top:18px}.floating-body :deep(.assistant-panel){padding:0;margin:0;border:0;background:transparent;box-shadow:none}.floating-body :deep(.assistant-panel header){align-items:start;gap:12px}.floating-body :deep(.assistant-panel header .eyebrow){display:none}.floating-body :deep(.assistant-panel h2){font-size:15px;margin:0 0 8px}.floating-body :deep(.assistant-panel header p){font-size:11px;margin:0}.floating-body :deep(.assistant-boundary){font-size:10px;margin:18px 0;padding-left:10px}.floating-body :deep(.assistant-controls){gap:12px}.floating-body :deep(.context-preview){padding:12px;margin:16px 0}.floating-body :deep(.context-preview pre){max-height:180px;padding:10px}.floating-body :deep(.generated-result){padding:16px 12px}.floating-body :deep(.generated-heading){flex-direction:column;align-items:start;gap:6px}.floating-body :deep(.generated-text){font-size:12px;line-height:1.9;margin:18px 0}
</style>
