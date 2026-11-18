<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import UiIcon from './UiIcon.vue'
import { accessSession } from '../stores/access'
import { assistantOpen, openAssistant } from '../stores/assistantSource'
const expanded = ref(false), route = useRoute()
const toggle = ref<HTMLButtonElement | null>(null)
async function closeTools() {
  if (!expanded.value) return
  expanded.value = false
  await nextTick()
  if (toggle.value?.offsetParent !== null) toggle.value?.focus()
}
watch(() => route.fullPath, () => { expanded.value = false })
function scroll(to: 'top' | 'bottom') {
  expanded.value = false
  window.scrollTo({ top: to === 'top' ? 0 : document.documentElement.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
}
function toggleAssistant() {
  expanded.value = false
  if (assistantOpen.value) assistantOpen.value = false
  else openAssistant()
}
</script>
<template>
  <aside class="utility-rail" aria-label="页面快捷工具" @keydown.esc="closeTools">
    <button ref="toggle" type="button" class="rail-toggle" aria-controls="page-shortcuts" :aria-expanded="expanded" @click="expanded = !expanded"><UiIcon name="help" :size="18" /><span>页面工具</span><span aria-hidden="true">{{ expanded ? '−' : '+' }}</span></button>
    <div id="page-shortcuts" class="rail-tools" :class="{ expanded }">
      <button v-if="!accessSession?.read_only" type="button" title="AI 科研解读" aria-label="AI 科研解读" aria-controls="assistant-dialog" :aria-expanded="assistantOpen" @click="toggleAssistant"><UiIcon name="sparkle" /><span class="rail-label">AI 科研解读</span></button>
      <RouterLink v-if="!accessSession?.read_only" to="/settings#model-connection" title="模型设置"><UiIcon name="settings" /><span class="rail-label">模型设置</span></RouterLink>
      <span class="rail-divider" aria-hidden="true"></span>
      <button type="button" title="直达顶部" @click="scroll('top')"><UiIcon name="top" /><span class="rail-label">直达顶部</span></button>
      <button type="button" title="直达底部" @click="scroll('bottom')"><UiIcon name="bottom" /><span class="rail-label">直达底部</span></button>
      <span class="rail-divider" aria-hidden="true"></span>
      <RouterLink to="/about" title="使用说明"><UiIcon name="help" /><span class="rail-label">使用说明</span></RouterLink>
    </div>
  </aside>
</template>
<style scoped>
.utility-rail{position:fixed;right:12px;top:50%;transform:translateY(-50%);padding:7px;background:var(--card);border:1px solid var(--border);border-radius:10px;z-index:45;box-shadow:var(--shadow)}.rail-tools{display:flex;flex-direction:column;gap:4px}.utility-rail button,.utility-rail a{display:flex;align-items:center;justify-content:center;gap:10px;width:34px;height:40px;background:none;border:0;color:var(--muted);cursor:pointer;border-radius:6px;text-decoration:none;font:13px var(--font)}.utility-rail button:hover,.utility-rail a:hover{background:var(--primary-weak);color:var(--primary)}.utility-rail .rail-toggle{display:none}.rail-label{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}.rail-divider{height:1px;background:var(--border);margin:2px 4px}
@media(max-width:900px){.utility-rail{position:static;transform:none;width:auto;max-width:calc(100% - 32px);margin:0 16px 20px;box-shadow:none;padding:8px}.utility-rail .rail-toggle{display:flex;width:100%;height:42px;justify-content:flex-start;padding:0 12px;color:var(--primary)}.rail-toggle span:last-child{margin-left:auto}.rail-tools{display:none}.rail-tools.expanded{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;border-top:1px solid var(--border);padding-top:8px;margin-top:6px}.utility-rail .rail-tools button,.utility-rail .rail-tools a{width:100%;height:44px;justify-content:flex-start;padding:0 12px}.rail-label{position:static;width:auto;height:auto;margin:0;overflow:visible;clip-path:none;white-space:normal;font-size:13px}.rail-divider{display:none}}
</style>
