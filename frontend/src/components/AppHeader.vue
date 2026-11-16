<script setup lang="ts">
import { computed } from 'vue'
import { accessSession } from '../stores/access'
import { useRoute } from 'vue-router'
import { useServiceStore } from '../stores/service'
import { isDark, setTheme } from '../stores/appearance'
import UiIcon from './UiIcon.vue'
import BrandMark from './BrandMark.vue'
const route = useRoute()
const service = useServiceStore()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const links = [
  { to: '/', label: '研究概览' },
  { to: '/research', label: '研究工作台' },
  { to: '/data-catalog', label: '数据图谱' },
  { to: '/records', label: '实验记录' },
]
function active(path: string) {
  if (path === '/research') return route.path === '/research' || route.path === '/workbench' || route.path === '/compare' || /^\/(runs|measured)\//.test(route.path)
  if (path === '/data-catalog') return route.path === '/data-catalog' || route.path.startsWith('/methods')
  return route.path === path
}
</script>
<template>
  <header class="app-header national-header"><div class="header-inner">
    <RouterLink to="/" class="brand" aria-label="CellLens 细胞知镜首页"><BrandMark /><strong>CellLens</strong><span>细胞知镜</span></RouterLink>
    <nav class="header-nav" aria-label="主导航"><RouterLink v-for="link in links" :key="link.to" :to="readOnly && link.to==='/research' ? '/records?view=results' : link.to" :class="{ active: active(link.to) }" :aria-current="active(link.to) ? 'page' : undefined">{{ readOnly && link.to==='/research' ? '已发布案例' : link.label }}</RouterLink></nav>
    <div class="header-actions">
      <RouterLink v-if="!readOnly" to="/status" class="service-indicator" :title="'查看实际服务状态：' + service.levelLabel"><i :class="service.level" aria-hidden="true"/><span>{{ service.levelLabel }}</span></RouterLink>
      <RouterLink :to="readOnly ? '/records?view=results' : '/research'" class="header-create"><span aria-hidden="true">{{readOnly?'↗':'＋'}}</span> {{readOnly?'浏览案例':'新建分析'}}</RouterLink>
      <RouterLink to="/about" class="header-icon" aria-label="使用帮助" title="使用帮助"><UiIcon name="help" :size="17" /></RouterLink>
      <button class="header-icon" type="button" :aria-label="isDark ? '切换到明亮模式' : '切换到深色模式'" :title="isDark ? '切换到明亮模式' : '切换到深色模式'" @click="setTheme(isDark ? 'light' : 'dark')"><UiIcon :name="isDark ? 'sun' : 'moon'" :size="17" /></button>
    </div>
  </div></header>
</template>
<style scoped>
.national-header{background:var(--header-glass);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50;backdrop-filter:blur(20px)}.header-inner{width:100%;max-width:1600px;margin:auto;padding:0 4%;display:flex;align-items:center;gap:36px;min-height:78px}.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;flex:none}.brand strong{font:27px Georgia,serif;letter-spacing:-1.1px;font-weight:400}.brand>span{font-size:12px;letter-spacing:2px;border-left:1px solid var(--border-strong);padding-left:12px;margin-left:2px}.header-nav{display:flex;align-self:stretch;align-items:stretch;gap:28px;flex:0 0 auto;min-width:0}.header-nav>a{position:relative;display:flex;align-items:center;justify-content:center;font-size:13px;color:var(--muted);white-space:nowrap;text-decoration:none}.header-nav>a.active{color:var(--primary-strong);font-weight:600}.header-nav>a.active:after{content:'';position:absolute;bottom:0;left:calc(50% - 11px);height:3px;width:22px;border-radius:3px;background:var(--primary)}.header-actions{display:flex;align-items:center;gap:11px;margin-left:auto;flex:none}.service-indicator{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:32px;color:var(--muted);font-size:10px;white-space:nowrap;text-decoration:none}.service-indicator i{width:6px;height:6px;border-radius:50%;background:var(--faint)}.service-indicator i.ok{background:var(--ok)}.service-indicator i.down{background:var(--danger)}.service-indicator i.degraded{background:var(--warn)}.header-create{background:var(--primary-strong);color:var(--on-primary);border:1px solid var(--primary-strong);padding:9px 13px;border-radius:8px;text-decoration:none;font-size:12px;white-space:nowrap;display:flex;align-items:center;gap:4px}.header-create>span{font-size:17px;line-height:1}.header-icon{width:29px;height:32px;display:inline-flex;align-items:center;justify-content:center;border:0;background:transparent;color:var(--muted);cursor:pointer;border-radius:6px}.header-icon:hover{background:var(--primary-weak);color:var(--primary)}.header-create:hover{background:var(--primary);border-color:var(--primary)}.header-nav a:hover{color:var(--primary)}
@media(max-width:1360px){.header-inner{gap:27px;padding:0 3%}.header-nav{gap:24px}.brand>span{display:none}.header-actions{gap:8px}}@media(max-width:1100px){.header-inner{gap:25px}.header-nav{gap:18px}.service-indicator span{display:none}.header-create{padding:8px 10px}.brand strong{font-size:25px}}@media(max-width:820px){.header-inner{flex-wrap:wrap;gap:0;padding:0 20px;min-height:68px}.brand{height:62px}.header-actions{gap:7px}.header-nav{order:3;width:100%;height:43px;justify-content:space-between;gap:12px}.header-nav>a{font-size:12px}.header-create{font-size:11px}.brand strong{font-size:24px}.brand :deep(svg){width:33px;height:33px}.service-indicator{display:none}}@media(max-width:430px){.header-inner{padding:0 15px}.header-actions{gap:2px}.header-create{padding:7px 8px;margin-right:4px}.header-icon{width:26px}}
</style>
