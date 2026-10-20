<script setup lang="ts">
import type { CellBackground } from '../data/cellBackgrounds'
withDefaults(defineProps<{ background: CellBackground; compact?: boolean }>(), { compact: false })
</script>

<template>
  <article class="cell-background-card" :class="{ compact }" :aria-label="background.id + ' 细胞背景介绍'">
    <header><h3>{{ background.id }} <small lang="en">{{ background.name }}</small></h3><span class="cell-growth">{{ background.growth_zh }} <span lang="en">{{ background.growth_en }}</span></span></header>
    <p class="cell-type">{{ background.type_zh }}<span lang="en">{{ background.type_en }}</span></p>
    <section class="cell-origin"><h4>来源 <small lang="en">Origin</small></h4><p>{{ background.origin_zh }}</p><p lang="en">{{ background.origin_en }}</p></section>
    <details v-if="compact" class="cell-extra"><summary>特点与研究用途 · Features &amp; research uses</summary><section><h4>生物学特点 <small lang="en">Biological features</small></h4><p>{{ background.features_zh }}</p><p lang="en">{{ background.features_en }}</p></section><section><h4>常见研究用途 <small lang="en">Research uses</small></h4><p>{{ background.uses_zh }}</p><p lang="en">{{ background.uses_en }}</p></section><footer><a v-for="source in background.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener">{{ source.label }} ↗</a></footer></details>
    <template v-else><section><h4>生物学特点 <small lang="en">Biological features</small></h4><p>{{ background.features_zh }}</p><p lang="en">{{ background.features_en }}</p></section><section><h4>常见研究用途 <small lang="en">Research uses</small></h4><p>{{ background.uses_zh }}</p><p lang="en">{{ background.uses_en }}</p></section><footer><a v-for="source in background.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener">{{ source.label }} ↗</a></footer></template>
  </article>
</template>

<style scoped>
.cell-background-card{min-width:0;border:1px solid var(--border);padding:22px 24px;background:var(--card);font-size:12px;line-height:1.9;overflow-wrap:anywhere}.cell-background-card header{display:flex;align-items:start;justify-content:space-between;gap:16px}.cell-background-card h3{font-size:20px;font-weight:500;margin:0;color:var(--primary-strong)}.cell-background-card h3 small{display:block;font-size:11px;color:var(--muted);font-weight:400}.cell-growth{font-size:10px;color:var(--primary);text-align:right;flex:none}.cell-growth span{display:block}.cell-type{font-size:13px;color:var(--ink);margin:12px 0 18px}.cell-type span{display:block;font-size:11px;color:var(--primary)}.cell-background-card h4{font-size:11px;font-weight:500;margin:18px 0 7px;color:var(--ink)}.cell-background-card h4 small{font-size:10px;color:var(--muted);font-weight:400;margin-left:6px}.cell-background-card p{margin:6px 0}.cell-background-card p[lang=en]{font-size:11px;color:var(--muted);line-height:1.8}.cell-background-card footer{display:flex;flex-wrap:wrap;gap:6px 18px;margin-top:20px;padding-top:12px;border-top:1px solid var(--border);font-size:10px}.cell-extra{margin-top:16px}.cell-extra summary{cursor:pointer;color:var(--primary);font-size:11px}.compact{padding:16px;margin-top:16px;background:var(--primary-weak);font-size:11px}.compact h3{font-size:16px}.compact .cell-type{font-size:12px;margin-top:10px}.compact p[lang=en]{font-size:10px}
</style>
