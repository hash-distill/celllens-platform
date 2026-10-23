<script setup lang="ts">
import UiIcon from './UiIcon.vue'
import { assistantOpen, openAssistant } from '../stores/assistantSource'
function scroll(to: 'top' | 'bottom') {
  window.scrollTo({top: to === 'top' ? 0 : document.documentElement.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'})
}
</script>
<template>
  <aside class="utility-rail" aria-label="页面快捷工具">
    <button type="button" title="AI 科研解读" aria-label="AI 解读" aria-controls="assistant-dialog" :aria-expanded="assistantOpen" @click="assistantOpen ? assistantOpen = false : openAssistant()"><UiIcon name="sparkle" /></button>
    <RouterLink to="/settings#model-connection" title="模型设置" aria-label="模型设置"><UiIcon name="settings" /></RouterLink>
    <span class="rail-divider"></span>
    <button type="button" title="直达顶部" aria-label="直达顶部" @click="scroll('top')"><UiIcon name="top" /></button>
    <button type="button" title="直达底部" aria-label="直达底部" @click="scroll('bottom')"><UiIcon name="bottom" /></button>
    <span class="rail-divider"></span>
    <RouterLink to="/about" title="使用说明" aria-label="使用说明"><UiIcon name="help" /></RouterLink>
  </aside>
</template>
<style scoped>
.utility-rail{position:fixed;right:12px;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:4px;padding:7px;background:var(--card);border:1px solid var(--border);border-radius:6px;z-index:45;box-shadow:var(--shadow-lg)}.utility-rail button,.utility-rail a{display:flex;align-items:center;justify-content:center;width:34px;height:36px;background:none;border:0;color:var(--muted);cursor:pointer;border-radius:3px}.utility-rail button:hover,.utility-rail a:hover{background:var(--primary-weak);color:var(--primary)}.rail-divider{height:1px;background:var(--border);margin:2px 4px}
</style>
