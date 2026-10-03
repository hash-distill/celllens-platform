<script setup lang="ts">
import { computed } from 'vue'
import type { CoverageSummary } from '../types/run'
import { fmtPercent } from '../utils/format'

/**
 * 覆盖摘要卡：文案与当前计算语义一致。
 * 低覆盖一眼可见，即使 warnings 为空。
 */

const props = defineProps<{ coverage: CoverageSummary }>()

interface CardSpec {
  key: string
  name: string
  value: string
  hint: string
  low: boolean
}

const cards = computed<CardSpec[]>(() => {
  const c = props.coverage
  return [
    {
      key: 'state',
      name: '对齐基因占参考面板比例',
      value: fmtPercent(c.state_gene_fraction),
      hint: '不是全基因组覆盖率',
      low: false,
    },
    {
      key: 'metabolic',
      name: '代谢库基因覆盖率',
      value: fmtPercent(c.metabolic_gene_fraction),
      hint: '已覆盖代谢库基因的比例',
      low: c.metabolic_gene_fraction < 0.5,
    },
    {
      key: 'reaction',
      name: '反应所需基因平均覆盖比例',
      value: fmtPercent(c.reaction_fraction),
      hint: '各反应基因覆盖的平均值，不是完整反应占比',
      low: c.reaction_fraction < 0.5,
    },
    {
      key: 'supported',
      name: '覆盖支持任务数',
      value: String(c.supported_tasks),
      hint: '覆盖规则支持，不等于预测被实验证实',
      low: false,
    },
    {
      key: 'exploratory',
      name: '探索性任务数',
      value: String(c.exploratory_tasks),
      hint: '有限制的候选解释',
      low: false,
    },
    {
      key: 'insufficient',
      name: '证据不足任务数',
      value: String(c.insufficient_tasks),
      hint: '不能作为可靠代谢结论',
      low: c.insufficient_tasks > 0,
    },
  ]
})
</script>

<template>
  <div class="coverage-grid" role="list" aria-label="覆盖摘要">
    <div
      v-for="card in cards"
      :key="card.key"
      class="coverage-card"
      :class="{ low: card.low }"
      role="listitem"
    >
      <div class="coverage-value">{{ card.value }}</div>
      <div class="coverage-name">{{ card.name }}</div>
      <div class="coverage-hint">{{ card.hint }}</div>
    </div>
  </div>
</template>

<style scoped>
.coverage-hint {
  font-size: 11px;
  color: var(--faint);
  margin-top: 4px;
  line-height: 1.4;
}
</style>
