<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import GeneCategoryGuide from './GeneCategoryGuide.vue'
import type { GeneAnnotation, GeneCategory } from '../types/geneEducation'

const props = withDefaults(defineProps<{
  modelValue: string
  context: string
  items: string[]
  genes?: GeneAnnotation[]
  categories?: GeneCategory[]
  loading?: boolean
  error?: string | null
  warning?: string | null
}>(), {genes:()=>[], categories:()=>[], loading:false})
const emit = defineEmits<{'update:modelValue': [value: string]; retry: []}>()
const query = ref(props.modelValue), category = ref(''), dropdownOpen = ref(false), highlightIndex = ref(-1)
let closeTimer: number | undefined
const annotations = computed(() => new Map(props.genes.map(gene => [gene.symbol, gene])))
const selectedAnnotation = computed(() => annotations.value.get(props.modelValue))
const filteredItems = computed(() => {
  const text = query.value.trim().toUpperCase()
  return props.items.filter(symbol => {
    const gene = annotations.value.get(symbol)
    return (!category.value || gene?.category_ids.includes(category.value)) &&
      (!text || `${symbol} ${gene?.approved_symbol ?? ''} ${gene?.name_zh ?? ''} ${gene?.name_en ?? ''}`.toUpperCase().includes(text))
  })
})
watch(() => props.modelValue, value => { query.value = value })
watch(() => props.context, () => { category.value='';query.value=props.modelValue;dropdownOpen.value=false;highlightIndex.value=-1 })
watch([query, category, () => props.items], () => { highlightIndex.value=-1 })
function categoryNames(symbol: string) {
  const ids = annotations.value.get(symbol)?.category_ids ?? []
  return props.categories.filter(item => ids.includes(item.id)).map(item => item.name_zh).join('、')
}
function openDropdown() { window.clearTimeout(closeTimer);dropdownOpen.value=true;highlightIndex.value=-1 }
function changeCategory() { query.value='';openDropdown() }
function pick(symbol: string) { emit('update:modelValue', symbol);query.value=symbol;dropdownOpen.value=false }
function closeSoon() {
  window.clearTimeout(closeTimer)
  closeTimer = window.setTimeout(() => {
    dropdownOpen.value=false
    const symbol = query.value.trim().toUpperCase()
    if (filteredItems.value.includes(symbol)) pick(symbol)
    else query.value=props.modelValue
  }, 160)
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { dropdownOpen.value=false;query.value=props.modelValue;return }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();window.clearTimeout(closeTimer);dropdownOpen.value=true
    highlightIndex.value = event.key === 'ArrowDown'
      ? Math.min(highlightIndex.value + 1, filteredItems.value.length - 1)
      : Math.max(highlightIndex.value - 1, 0)
  } else if (event.key === 'Enter') {
    // Enter selects a candidate; it must not submit the enclosing experiment form.
    event.preventDefault()
    const symbol = filteredItems.value[highlightIndex.value >= 0 ? highlightIndex.value : 0]
    if (dropdownOpen.value && symbol) pick(symbol)
  }
}
onBeforeUnmount(() => window.clearTimeout(closeTimer))
</script>

<template>
  <div class="gene-picker">
    <div class="gene-picker-controls">
      <label class="label" for="perturbation-category">基因功能分类 · Gene function class</label>
      <select id="perturbation-category" v-model="category" class="input gene-category-select" :disabled="loading" @change="changeCategory"><option value="">全部可用扰动基因</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name_zh }} · {{ item.name_en }}（{{ item.count }}）</option></select>
      <label class="label" for="perturbation-input">扰动基因</label>
      <div class="perturbation-box">
        <input id="perturbation-input" v-model="query" class="input" type="text" role="combobox" :aria-expanded="dropdownOpen" aria-controls="perturbation-listbox" :aria-activedescendant="dropdownOpen && highlightIndex>=0 ? `perturbation-option-${highlightIndex}` : undefined" aria-autocomplete="list" placeholder="搜索扰动基因…" autocomplete="off" :disabled="loading" @focus="openDropdown" @click="openDropdown" @input="openDropdown" @blur="closeSoon" @keydown="keydown" />
        <div v-if="dropdownOpen" id="perturbation-listbox" class="dropdown" role="listbox" aria-label="可选扰动基因"><p v-if="loading" class="dropdown-note">正在加载扰动列表…</p><p v-else-if="!filteredItems.length" class="dropdown-note">无匹配的可用扰动</p><template v-else><button v-for="(symbol,index) in filteredItems" :id="`perturbation-option-${index}`" :key="symbol" type="button" role="option" :aria-label="symbol" :aria-selected="modelValue===symbol" class="dropdown-item" :class="{highlighted:index===highlightIndex}" @mousedown.prevent @click="pick(symbol)">{{ symbol }}<small aria-hidden="true">{{ categoryNames(symbol) }}</small></button></template></div>
      </div>
    </div>
    <div class="gene-picker-details">
      <p v-if="selectedAnnotation" class="selected-gene-annotation"><strong>已选 {{ selectedAnnotation.symbol }}</strong><span v-if="selectedAnnotation.name_zh" lang="zh-CN">{{ selectedAnnotation.name_zh }}</span><span lang="en">{{ selectedAnnotation.name_en }}</span><span>{{ categoryNames(selectedAnnotation.symbol) }}</span></p>
      <slot />
      <GeneCategoryGuide :categories="categories" :selected="category" />
      <p v-if="warning" class="field-error">{{ warning }}</p>
      <p v-if="error" class="field-error">扰动列表加载失败：{{ error }} <button type="button" class="btn btn-ghost btn-sm" @click="emit('retry')">重试</button></p>
    </div>
  </div>
</template>

<style scoped>
.gene-category-select{width:100%;min-width:0;margin-bottom:14px;font-size:11px}.selected-gene-annotation{font-size:10px;line-height:1.8;color:var(--muted);margin:10px 0}.selected-gene-annotation span{display:block;overflow-wrap:anywhere}.selected-gene-annotation strong{font-weight:500;color:var(--ink)}.perturbation-box{position:relative}.dropdown{position:absolute;top:calc(100% + 4px);left:0;right:0;max-height:240px;overflow-y:auto;background:var(--card);border:1px solid var(--border-strong);border-radius:var(--radius-sm);box-shadow:var(--shadow-lg);z-index:40;padding:4px}.dropdown-item{display:block;width:100%;text-align:left;appearance:none;border:none;background:none;padding:7px 10px;font-size:13px;font-family:var(--font);border-radius:6px;cursor:pointer;color:var(--ink)}.dropdown-item:hover,.dropdown-item.highlighted{background:var(--primary-weak);color:var(--primary)}.dropdown-item small{display:block;color:var(--muted);font-size:10px;line-height:1.6;margin-top:3px}.dropdown-note{margin:6px 10px;font-size:12px;color:var(--muted)}
</style>
