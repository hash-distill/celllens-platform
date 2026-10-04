<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useServiceStore } from '../stores/service'
import { useRecentStore } from '../stores/recent'
import UiIcon from './UiIcon.vue'
const route = useRoute()
const service = useServiceStore()
const recent = useRecentStore()
const runId = computed(() => typeof route.params.runId === 'string' ? route.params.runId : typeof route.query.run === 'string' ? route.query.run : recent.items[0]?.run_id)
const resultPath = computed(() => runId.value ? '/runs/'+encodeURIComponent(runId.value) : null)
const demoTarget = computed(() => ({path:'/demo',query:runId.value ? {run:runId.value} : {}}))
</script>
<template>
  <header class="app-header">
    <RouterLink to="/workbench" class="brand"><img src="/favicon.png" width="29" height="29" alt="" /><strong>细胞知镜</strong><span>CellLens</span></RouterLink>
    <nav class="header-nav" aria-label="主导航">
      <RouterLink to="/workbench" :class="{active:route.path==='/workbench'}">实验工作台</RouterLink>
      <RouterLink v-if="resultPath" :to="resultPath" :class="{active:route.path.startsWith('/runs/')}">结果分析</RouterLink>
      <span v-else class="nav-disabled" title="打开一个运行后查看结果">结果分析</span>
      <RouterLink to="/compare" :class="{active:route.path==='/compare'}">实验比较</RouterLink>
    </nav>
    <RouterLink to="/about" class="service-indicator" :title="'服务状态：'+service.levelLabel"><i :style="{background:service.level==='ok'?'var(--ok)':service.level==='down'?'var(--danger)':service.level==='degraded'?'var(--warn)':'var(--faint)'}"></i><span>{{ service.levelLabel }}</span></RouterLink>
    <RouterLink :to="demoTarget" class="header-demo"><UiIcon name="play" :size="14" /><span>演示模式</span></RouterLink>
    <RouterLink to="/about" class="header-methods" title="方法与来源"><UiIcon name="help" :size="18" /></RouterLink>
  </header>
</template>
<style scoped>
.app-header{height:58px;background:#fcfcfa;border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 24px;gap:28px;position:sticky;top:0;z-index:50}.brand{display:flex;align-items:center;gap:10px;color:var(--ink);text-decoration:none;flex:none}.brand img{object-fit:contain}.brand strong{font-size:18px;letter-spacing:.04em}.brand>span{font-size:15px;letter-spacing:.02em;margin-left:3px;font-weight:500}.header-nav{align-self:stretch;display:flex;gap:26px;margin-left:15px;flex:1}.header-nav>a,.nav-disabled{display:flex;align-items:center;font-size:12px;color:var(--muted);border-bottom:2px solid transparent;padding-top:2px;text-decoration:none;white-space:nowrap}.header-nav .active{color:var(--primary);border-bottom-color:var(--primary);font-weight:600}.nav-disabled{color:var(--faint)}.service-indicator{display:flex;gap:7px;align-items:center;color:var(--muted);font-size:10px;white-space:nowrap;text-decoration:none}.service-indicator i{width:6px;height:6px;border-radius:50%;background:var(--ok)}.service-indicator i.offline{background:var(--danger)}.header-demo{display:flex;align-items:center;gap:8px;border:1px solid #bdccc4;border-radius:3px;padding:6px 13px;color:var(--primary);font-size:11px;text-decoration:none;white-space:nowrap}.header-methods{color:var(--muted);display:grid;place-items:center}@media(max-width:1000px){.app-header{gap:15px;padding:0 15px}.header-nav{margin-left:0;gap:16px}.service-indicator{display:none}}@media(max-width:680px){.brand>span,.header-methods{display:none}.app-header{gap:12px}.brand strong{font-size:15px}.header-nav{gap:12px}.header-nav>a,.nav-disabled{font-size:10px}.header-demo{padding:5px}.header-demo span{display:none}.brand img{width:24px;height:24px}}@media(max-width:440px){.brand strong{display:none}}
</style>
