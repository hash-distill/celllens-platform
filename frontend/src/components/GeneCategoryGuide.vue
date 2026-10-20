<script setup lang="ts">
import { computed } from 'vue'
import type { GeneCategory } from '../types/geneEducation'
const props = withDefaults(defineProps<{categories: GeneCategory[]; selected?: string}>(), {selected: ''})
const active = computed(() => props.categories.find(item => item.id === props.selected))
</script>
<template>
  <div class="category-guide">
    <article v-if="active" class="category-definition" aria-label="当前基因类别介绍">
      <h3>{{ active.name_zh }} <small lang="en">{{ active.name_en }}</small></h3>
      <p>{{ active.description_zh }}</p><p lang="en">{{ active.description_en }}</p>
    </article>
    <details>
      <summary>基因分类说明 · Gene class guide</summary>
      <p>按 PANTHER 蛋白功能类别及其层级归类，代谢酶细分为酶学子类。一个基因可属于多个类别，类别计数不相加作为基因总数。</p>
      <p lang="en">Classes follow the PANTHER Protein Class hierarchy, with enzyme subclasses shown separately. Genes may have multiple classes; class counts should not be summed.</p>
      <div class="category-definitions"><article v-for="item in categories" :key="item.id"><h3>{{ item.name_zh }} <span>{{ item.count }} 个基因</span></h3><small lang="en">{{ item.name_en }}</small><p>{{ item.description_zh }}</p><p lang="en">{{ item.description_en }}</p></article></div>
      <a href="https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0" target="_blank" rel="noopener">PANTHER Protein Class · 分类来源 ↗</a>
    </details>
  </div>
</template>
<style scoped>
.category-guide{font-size:11px;line-height:1.8;color:var(--muted);margin:14px 0}.category-guide summary{cursor:pointer;color:var(--primary)}.category-definition{background:var(--primary-weak);padding:14px 16px;margin-bottom:12px}.category-guide h3{font-size:12px;font-weight:500;color:var(--ink);margin:0 0 6px}.category-guide h3 small{display:block;color:var(--primary);font-size:11px;margin-top:3px}.category-guide p{margin:5px 0}.category-guide p[lang=en]{font-size:10px}.category-definitions{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:16px;margin:16px 0}.category-definitions article{border-top:1px solid var(--border);padding-top:12px}.category-definitions h3 span{font-size:10px;font-weight:400;color:var(--muted);margin-left:8px}.category-definitions small{color:var(--primary)}
</style>
