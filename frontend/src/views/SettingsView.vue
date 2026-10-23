<script setup lang="ts">
import { ref } from 'vue'
import ModelConnectionSettings from '../components/ModelConnectionSettings.vue'
import { setTheme, theme, type ThemePreference } from '../stores/preferences'
const message = ref('')
function changeTheme(event: Event) {
  if (!setTheme((event.target as HTMLSelectElement).value as ThemePreference)) message.value = '外观已应用；当前浏览器无法保存偏好。'
}
</script>
<template>
  <div class="page settings-page">
    <header class="page-heading"><div><span class="eyebrow">WORKSPACE PREFERENCES</span><h1>系统设置</h1><p>管理当前浏览器的外观和大模型连接。</p></div><RouterLink to="/workbench" class="btn">返回工作台</RouterLink></header>
    <div class="settings-layout"><nav class="settings-nav" aria-label="设置分类"><a href="#appearance">外观</a><a href="#model-connection">大模型连接</a></nav><div class="settings-content">
      <section id="appearance" class="card settings-section"><span class="eyebrow">APPEARANCE</span><h2>外观</h2><div class="setting-line"><div><h3>页面主题</h3><p>跟随系统时，随设备的外观设置自动切换。</p></div><select aria-label="页面主题" :value="theme" @change="changeTheme"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div><p v-if="message" class="notice" role="status">{{ message }}</p></section>
      <ModelConnectionSettings />
    </div></div>
  </div>
</template>
<style scoped>
.settings-layout{display:grid;grid-template-columns:150px minmax(0,1fr);gap:32px;max-width:1160px}.settings-nav{display:flex;flex-direction:column;gap:20px;align-self:start;position:sticky;top:140px;font-size:12px;border-left:1px solid var(--border);padding:8px 18px}.settings-content{min-width:0}.settings-section{scroll-margin-top:140px;padding:28px;margin-bottom:24px}.settings-section h2{font-size:22px;font-weight:500;margin:8px 0 22px}.settings-section h3{font-size:13px;font-weight:500}.setting-line p{font-size:12px;color:var(--muted);line-height:1.9}.setting-line{display:flex;justify-content:space-between;gap:24px;align-items:center}.setting-line select{width:160px;max-width:45%;padding:10px 12px;border:1px solid var(--border-strong);background:var(--card);color:var(--ink);border-radius:4px;font:inherit}
@media(max-width:900px){.settings-layout{grid-template-columns:1fr;gap:18px}.settings-nav{position:static;flex-direction:row;border-left:0;border-bottom:1px solid var(--border);padding:0 0 16px}.settings-section{padding:20px}}
</style>
