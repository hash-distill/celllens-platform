<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useServiceStore } from '../stores/service'
import { useCandidatesStore } from '../stores/candidates'
import { isDark, setTheme } from '../stores/appearance'
import UiIcon from './UiIcon.vue'
import brandIcon from '../assets/optimized/brand-icon.png'
const route = useRoute()
const service = useServiceStore()
const candidates = useCandidatesStore()
</script>
<template>
  <header class="app-header"><div class="header-inner">
    <RouterLink to="/" class="brand" aria-label="细胞知镜首页"><img :src="brandIcon" width="29" height="29" alt="" /><strong>细胞知镜</strong><span>CellLens</span></RouterLink>
    <nav class="header-nav" aria-label="主导航">
      <RouterLink to="/research" :class="{active:route.path==='/research'}">研究分析</RouterLink>
      <RouterLink to="/records?view=results" :class="{active:(route.path==='/records' && route.query.view==='results') || route.path==='/compare' || /^\/(runs|measured)\//.test(route.path)}">结果解读<span v-if="candidates.items.length" class="nav-count">{{ candidates.items.length }}</span></RouterLink>
      <RouterLink to="/records" :class="{active:route.path==='/records' && route.query.view!=='results'}">实验记录</RouterLink>
      <RouterLink to="/data-catalog" :class="{active:route.path==='/data-catalog' || route.path.startsWith('/methods')}">数据与方法</RouterLink>
      <RouterLink to="/about" :class="{active:route.path==='/about'}">使用说明</RouterLink>
    </nav>
    <div class="header-actions">
    <button class="theme-toggle" type="button" :aria-label="isDark ? '切换到明亮模式' : '切换到深色模式'" :title="isDark ? '切换到明亮模式' : '切换到深色模式'" @click="setTheme(isDark ? 'light' : 'dark')"><UiIcon :name="isDark ? 'sun' : 'moon'" :size="16" /><span>{{ isDark ? '明亮模式' : '深色模式' }}</span></button>
    <RouterLink to="/status" class="service-indicator" :title="'查看服务状态：'+service.levelLabel" :aria-label="'查看服务状态：'+service.levelLabel"><i :style="{background:service.level==='ok'?'var(--ok)':service.level==='down'?'var(--danger)':service.level==='degraded'?'var(--warn)':'var(--faint)'}" aria-hidden="true"></i><span>{{ service.levelLabel }}</span></RouterLink>
    </div>
  </div></header>
</template>
<style scoped>
.app-header{background:var(--card);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50}
.header-inner{box-sizing:border-box;width:100%;max-width:none;margin:0;padding:0 24px;display:flex;align-items:center;gap:24px;min-height:70px}
.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;flex:none}
.brand strong{font-size:17px}.brand>span{font:15px Georgia,serif}
.header-nav{display:flex;align-self:stretch;justify-content:flex-start;gap:16px;flex:0 0 auto;min-width:0}
.header-nav>a{display:flex;align-items:center;justify-content:center;gap:5px;padding:0 10px;border-bottom:2px solid transparent;font-size:12px;color:var(--muted);white-space:nowrap;text-decoration:none}
.header-nav>a.active{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}
.nav-count{font-size:9px;background:var(--primary-weak);border-radius:50%;padding:0 5px}
.header-actions{display:flex;align-items:center;gap:12px;margin-left:auto;flex:none}
.theme-toggle,.service-indicator{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:34px;padding:8px 12px;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--muted);font:400 12px var(--font);white-space:nowrap;text-decoration:none;cursor:pointer}
.theme-toggle:hover,.service-indicator:hover{color:var(--primary);background:var(--primary-weak);border-color:var(--primary)}
.theme-toggle:focus-visible,.service-indicator:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
.service-indicator i{width:8px;height:8px;border-radius:50%;flex:none}
@media(max-width:1439px){.header-inner{gap:16px;padding:0 20px}.brand>span{display:none}.header-nav{gap:4px}.header-nav>a{padding:0 5px}.header-actions{gap:8px}.theme-toggle>span{display:none}.theme-toggle{padding:8px}.service-indicator{padding:8px 10px}}
</style>
