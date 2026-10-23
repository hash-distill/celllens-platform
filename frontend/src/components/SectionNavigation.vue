<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const items = computed(() => {
  if ((route.path === '/records' && route.query.view === 'results') || route.path === '/compare' || /^\/(runs|measured)\//.test(route.path)) return [{to:'/records?view=results', label:'结果列表', active:route.path === '/records'}, {to:'/compare', label:'预测结果比较', active:route.path === '/compare'}]
  if (route.path === '/data-catalog' || route.path.startsWith('/methods')) return [{to:'/data-catalog', label:'组合覆盖查询', active:route.path === '/data-catalog'}, {to:'/methods/models', label:'模型与方法', active:route.path === '/methods/models'}, {to:'/methods/backgrounds', label:'细胞背景', active:route.path === '/methods/backgrounds'}, {to:'/methods/coverage', label:'代谢覆盖', active:route.path === '/methods/coverage'}]
  return []
})
</script>
<template><nav v-if="items.length" class="section-navigation" aria-label="当前栏目"><RouterLink v-for="item in items" :key="item.to" :to="item.to" :class="{active:item.active}" :aria-current="item.active ? 'page' : undefined">{{ item.label }}</RouterLink></nav></template>
<style scoped>
.section-navigation{display:flex;gap:24px;flex-wrap:wrap;padding:18px 32px 0;border-bottom:1px solid var(--border);background:var(--card)}.section-navigation a{padding:0 0 14px;font-size:12px;color:var(--muted);text-decoration:none;border-bottom:2px solid transparent}.section-navigation a.active{color:var(--primary);border-color:var(--primary)}
</style>
