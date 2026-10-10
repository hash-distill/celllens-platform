<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useServiceStore } from '../stores/service'
import { useCandidatesStore } from '../stores/candidates'
const route = useRoute()
const service = useServiceStore()
const candidates = useCandidatesStore()
const runId = computed(() => typeof route.query.run === 'string' ? route.query.run : '')
const demoTarget = computed(() => ({path:'/demo',query:runId.value ? {run:runId.value} : {}}))
</script>
<template>
  <header class="app-header"><div class="header-inner">
    <RouterLink to="/" class="brand" aria-label="细胞知镜首页"><img src="/favicon.png" width="29" height="29" alt="" /><strong>细胞知镜</strong><span>CellLens</span></RouterLink>
    <nav class="header-nav" aria-label="主导航">
      <RouterLink to="/" :class="{active:route.path==='/'}">首页</RouterLink>
      <RouterLink :to="{path:'/workbench',query:runId?{run:runId}:{}}" :class="{active:route.path==='/workbench'}">实验工作台</RouterLink>
      <RouterLink to="/records" :class="{active:route.path==='/records'}">实验记录</RouterLink>
      <RouterLink to="/compare" :class="{active:route.path==='/compare'}">实验比较<span v-if="candidates.items.length" class="nav-count">{{ candidates.items.length }}</span></RouterLink>
      <RouterLink :to="demoTarget" :class="{active:route.path==='/demo'}">结果解读</RouterLink>
      <RouterLink to="/about" :class="{active:route.path==='/about'}">使用说明</RouterLink>
    </nav>
    <RouterLink to="/about" class="service-indicator" :title="'服务状态：'+service.levelLabel"><i :style="{background:service.level==='ok'?'var(--ok)':service.level==='down'?'var(--danger)':service.level==='degraded'?'var(--warn)':'var(--faint)'}"></i><span>{{ service.levelLabel }}</span></RouterLink>
  </div></header>
</template>
<style scoped>
.app-header{background:var(--card);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:50}.header-inner{max-width:1360px;margin:auto;padding:0 32px;display:flex;align-items:center;gap:30px;min-height:70px}.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;flex:none}.brand strong{font-size:17px}.brand>span{font:15px Georgia,serif}.header-nav{display:flex;align-self:stretch;gap:22px;flex:1}.header-nav>a{display:flex;align-items:center;gap:6px;border-bottom:2px solid transparent;font-size:12px;color:var(--muted);white-space:nowrap;text-decoration:none}.header-nav>a.active{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}.nav-count{font-size:9px;background:var(--primary-weak);border-radius:50%;padding:0 5px}.service-indicator{display:flex;gap:6px;align-items:center;white-space:nowrap;color:var(--muted);font-size:10px}.service-indicator i{width:6px;height:6px;border-radius:50%}@media(max-width:1100px){.service-indicator{display:none}.header-inner{gap:24px}}@media(max-width:760px){.header-inner{padding:14px 16px 0;gap:12px;flex-wrap:wrap}.brand{padding-bottom:5px}.header-nav{order:3;flex-basis:100%;overflow-x:auto;gap:24px;height:43px;scrollbar-width:none}.header-nav>a{font-size:11px}.brand strong{font-size:16px}.service-indicator{display:flex;margin-left:auto;padding-bottom:5px}}
</style>
