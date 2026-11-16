<script setup lang="ts">
import { computed } from 'vue'
import type { CoverageTask } from '../types/coverage'

const props = defineProps<{tasks: CoverageTask[]; selectedId: string}>()
const emit = defineEmits<{select: [id: string]}>()
const statusLabels = { full:'完整', partial:'部分', absent:'未覆盖', unmapped:'未登记' } as const
const counts = computed(() => Object.entries(statusLabels).map(([status, label]) => ({status, label, count:props.tasks.filter(task => task.coverage_status === status).length})))
function label(task: CoverageTask) {
  return `${task.guide?.name_zh || task.label}：${task.coverage_status === 'unmapped' ? '未登记关联基因，覆盖比例不可计算' : `${statusLabels[task.coverage_status]}，已覆盖 ${task.n_present_all} / ${task.n_genes_all} 个关联基因`}`
}
</script>

<template>
  <section class="task-coverage-chart" aria-label="代谢任务关联基因覆盖图">
    <header><h3>任务覆盖图 <span>{{ tasks.length }} 项</span></h3><div class="chart-legend"><span v-for="item in counts" :key="item.status"><i :class="item.status" />{{ item.label }} {{ item.count }}</span></div></header>
    <p>每个圆点代表一项任务，填充比例表示知识库关联基因的覆盖率。虚线圆表示未登记关联基因，不能计算覆盖比例。点击圆点查看任务详情。</p>
    <div class="task-dot-grid">
      <button v-for="task in tasks" :key="task.id" type="button" class="task-dot" :class="{selected: selectedId === task.id, full: task.coverage_status === 'full', absent: task.coverage_status === 'absent', unmapped: task.coverage_status === 'unmapped'}" :style="{'--coverage-angle': Math.min(1, Math.max(0, task.fraction_present_all)) * 360 + 'deg'}" :aria-label="label(task)" :title="label(task)" :aria-pressed="selectedId === task.id" @click="emit('select', task.id)"><span aria-hidden="true" /></button>
    </div>
  </section>
</template>

<style scoped>
.task-coverage-chart{margin:20px 0 10px;padding:18px 20px;background:var(--surface-soft);border:1px solid var(--border)}header{display:flex;align-items:center;justify-content:space-between;gap:20px}h3{font-size:13px;font-weight:500;margin:0;color:var(--ink)}h3>span{font-size:11px;font-weight:400;color:var(--muted);margin-left:10px}.chart-legend{display:flex;gap:16px;font-size:10px;color:var(--muted)}.chart-legend>span{display:flex;align-items:center;gap:6px}.chart-legend i{display:block;width:8px;height:8px;border-radius:50%;background:var(--border-strong)}.chart-legend i.full{background:var(--primary)}p{font-size:11px;color:var(--muted);line-height:1.8;margin:10px 0 14px}.task-dot-grid{display:grid;grid-template-columns:repeat(auto-fill,28px);gap:7px}.task-dot{--coverage-angle:0deg;display:grid;place-items:center;width:28px;height:28px;border:0;padding:3px;border-radius:50%;background:transparent;cursor:pointer}.task-dot>span{width:20px;height:20px;border-radius:50%;background:conic-gradient(var(--primary) var(--coverage-angle),var(--border) 0);position:relative}.task-dot:not(.full)>span::after{content:'';position:absolute;inset:5px;background:var(--surface-soft);border-radius:50%}.task-dot:hover{background:var(--primary-weak)}.task-dot.selected{outline:1px solid var(--primary);outline-offset:1px}.task-dot:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
</style>

<style scoped>
.task-coverage-chart{border-radius:8px}.chart-legend{flex-wrap:wrap;gap:8px 13px}.chart-legend i.partial{background:var(--primary-soft)}.chart-legend i.absent{background:transparent;border:1px solid var(--muted)}.chart-legend i.unmapped{background:transparent;border:1px dashed var(--muted)}.task-dot.absent>span{background:transparent;border:1px solid var(--border-strong)}.task-dot.unmapped>span{background:transparent;border:1px dashed var(--muted)}.task-dot.unmapped>span::after,.task-dot.absent>span::after{display:none}@media(max-width:650px){header{flex-wrap:wrap;gap:10px}.task-coverage-chart{padding:15px}.chart-legend{font-size:10px}}
</style>
