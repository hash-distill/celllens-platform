<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { accessSession } from '../stores/access'
const route = useRoute()
type SectionItem = { to: string; label: string; active: boolean; detail?: string; index?: string }
const isAtlas = computed(() => !accessSession.value?.read_only && (['/data-catalog','/datasets'].includes(route.path) || route.path.startsWith('/methods')))
const items = computed<SectionItem[]>(() => {
  if (accessSession.value?.read_only) return ['/records','/compare','/data-catalog'].includes(route.path)||route.path.startsWith('/methods') ? [{to:'/records?status=completed',label:'已发布案例',active:route.path==='/records'}, {to:'/data-catalog',label:'案例覆盖子集',active:route.path==='/data-catalog'}] : []
  if (route.path === '/records' || route.path === '/compare') return [{ to: '/records', label: '全部实验', active: route.path === '/records' }, { to: '/compare', label: '预测结果比较', active: route.path === '/compare' }]
  if (isAtlas.value) return [
    {to:'/data-catalog', label:'数据与扰动', detail:'查找可分析的研究组合', index:'01', active:['/data-catalog','/datasets'].includes(route.path)},
    {to:'/methods/backgrounds', label:'细胞与样本', detail:'了解背景、对照与表达面板', index:'02', active:route.path === '/methods/backgrounds'},
    {to:'/methods/models', label:'模型与方法', detail:'理解表达预测与功能推断', index:'03', active:route.path === '/methods/models'},
    {to:'/methods/coverage', label:'代谢覆盖', detail:'核对代谢基因与任务范围', index:'04', active:route.path === '/methods/coverage'},
  ]
  return []
})
</script>
<template>
  <nav v-if="items.length" class="section-navigation" :class="{'atlas-navigation':isAtlas}" :aria-label="isAtlas ? '数据图谱栏目' : '当前栏目'">
    <RouterLink v-for="item in items" :key="item.to" :to="item.to" :class="{active:item.active}" :aria-current="item.active ? 'page' : undefined">
      <span v-if="item.index" class="section-index" aria-hidden="true">{{ item.index }}</span>
      <span class="section-copy"><span class="section-label">{{ item.label }}</span><small v-if="item.detail">{{ item.detail }}</small></span>
      <span v-if="isAtlas" class="section-arrow" aria-hidden="true">↗</span>
    </RouterLink>
  </nav>
</template>
<style scoped>
.section-navigation{display:flex;gap:28px;flex-wrap:wrap;padding:16px max(4%,calc((100% - 1320px)/2)) 0;border-bottom:1px solid var(--border);background:var(--card)}
.section-navigation a{padding:0 0 13px;font-size:12px;color:var(--muted);text-decoration:none;border-bottom:2px solid transparent}
.section-navigation a.active{color:var(--primary);border-color:var(--primary);font-weight:500}
.atlas-navigation{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;padding-top:0;background:var(--card)}
.atlas-navigation a{position:relative;display:flex;align-items:center;gap:13px;padding:20px 18px;border-bottom-width:3px;min-width:0;transition:background .18s}
.atlas-navigation a:first-child{padding-left:0}.atlas-navigation a:hover{background:var(--surface-soft)}
.atlas-navigation a.active{background:linear-gradient(0deg,var(--primary-weak),transparent)}
.section-index{font:22px Georgia,serif;color:var(--faint)}.active .section-index{color:var(--primary)}
.section-copy{min-width:0}.section-label{display:block;font-size:14px}.section-copy small{display:block;font-size:11px;font-weight:400;line-height:1.7;margin-top:5px;color:var(--muted)}
.section-arrow{margin-left:auto;color:var(--faint);font-size:16px}.active .section-arrow{color:var(--primary)}
@media(max-width:1050px){.atlas-navigation a{gap:9px;padding:17px 10px}.section-arrow{display:none}.section-index{font-size:19px}.section-copy small{font-size:10px}}
@media(max-width:650px){.section-navigation{gap:20px;padding-left:20px;padding-right:20px}.atlas-navigation{gap:0;grid-template-columns:repeat(2,minmax(0,1fr))}.atlas-navigation a,.atlas-navigation a:first-child{padding:13px 9px}.section-label{font-size:13px}.section-copy small{font-size:10px}.section-index{font-size:18px}}
@media(prefers-reduced-motion:reduce){.atlas-navigation a{transition:none}}
</style>
