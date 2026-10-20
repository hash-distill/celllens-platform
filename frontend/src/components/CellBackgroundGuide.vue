<script setup lang="ts">
import { computed } from 'vue'
import { getCellBackground } from '../data/cellBackgrounds'
import CellBackgroundCard from './CellBackgroundCard.vue'
const props = defineProps<{ cellLine?: string; cellLines: string[] }>()
const selected = computed(() => getCellBackground(props.cellLine))
const backgrounds = computed(() => [...new Set(props.cellLines)].flatMap(id => { const item = getCellBackground(id); return item ? [item] : [] }))
</script>

<template>
  <section v-if="selected || backgrounds.length" id="cell-backgrounds" class="cell-background-guide" aria-label="细胞背景介绍">
    <div class="guide-heading"><div><span class="eyebrow">CELL BACKGROUNDS</span><h2>细胞背景介绍</h2><p>认识细胞来源、主要特点与常见研究用途。</p></div><span v-if="selected" class="current-label">当前背景 · {{ selected.id }}</span></div>
    <CellBackgroundCard v-if="selected" :background="selected" />
    <details v-if="backgrounds.length" class="all-backgrounds"><summary>查看各细胞背景 · Compare cell backgrounds</summary><div class="background-grid"><CellBackgroundCard v-for="background in backgrounds" :key="background.id" :background="background" /></div></details>
    <p class="background-note">介绍描述细胞系的一般特征；实验所用亚克隆与处理条件以对应数据来源为准。</p><p class="background-note" lang="en">These descriptions summarize general cell-line properties. Exact subclones and experimental conditions depend on the corresponding data source.</p>
  </section>
</template>

<style scoped>
.cell-background-guide{margin:28px 0 32px;scroll-margin-top:100px}.guide-heading{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:18px}.guide-heading h2{font-size:20px;font-weight:500;margin:8px 0}.guide-heading p,.current-label{font-size:11px;color:var(--muted);line-height:1.8}.current-label{color:var(--primary);white-space:nowrap}.all-backgrounds{margin-top:18px}.all-backgrounds summary{font-size:12px;cursor:pointer;color:var(--primary)}.background-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-top:18px}.background-note{font-size:10px;color:var(--muted);line-height:1.8;margin:14px 0 0}.background-note[lang=en]{margin-top:4px}
</style>
