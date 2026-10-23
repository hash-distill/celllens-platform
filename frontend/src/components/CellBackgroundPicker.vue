<script setup lang="ts">
import type { CellLine } from '../types/run'

withDefaults(defineProps<{
  modelValue: CellLine
  options: {value: CellLine; disabled?: boolean; reason?: string | null}[]
  compact?: boolean
}>(), {compact:false})
const emit = defineEmits<{'update:modelValue': [value: CellLine]}>()
</script>

<template>
  <div class="cell-background-picker" :class="{compact}">
    <span class="label" id="cell-line-label">细胞背景</span>
    <div class="choice-group cell-choice-group" role="radiogroup" aria-labelledby="cell-line-label">
      <label v-for="option in options" :key="option.value" class="choice" :class="{selected:modelValue===option.value, disabled:option.disabled}" :title="option.disabled ? option.reason ?? '不可用' : undefined">
        <input type="radio" name="cell-line" :value="option.value" :checked="modelValue===option.value" :disabled="option.disabled" @change="emit('update:modelValue', option.value)" />
        <span><span class="choice-name">{{ option.value }}</span><span v-if="option.disabled && option.reason && !compact" class="choice-reason"><br />{{ option.reason }}</span></span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.cell-choice-group{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:1fr;gap:8px}.cell-choice-group .choice{min-width:0;min-height:42px;align-items:center}.compact .choice{padding:10px;font-size:11px}.compact .choice-name{font-size:12px}.choice-reason{font-size:10px;line-height:1.6}
</style>
