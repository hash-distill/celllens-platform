<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { OverviewSource, OverviewTaskRow } from '../utils/resultOverview'
import { taskPair, scoreLabel } from '../utils/metabolicVisualization'
import { downloadBlob, downloadCsv } from '../utils/csv'
const props = withDefaults(defineProps<{ tasks: OverviewTaskRow[]; sourceKind: OverviewSource; compact?: boolean; selectedId?: string; context?: string; readOnly?: boolean }>(), { compact: false, context: '' })
const emit = defineEmits<{ select: [id: string] }>()
const category = ref(''), search = ref(''), direction = ref(''), page = ref(1)
const plot = ref<SVGSVGElement | null>(null)
const targetLabel = computed(() => props.sourceKind === 'run' ? '模型预测' : '扰动实测')
const pairs = computed(() => props.tasks.map(row => taskPair(row, props.sourceKind)))
const groups = computed(() => [...new Set(props.tasks.map(row => row.category || '未分类'))].sort())
const directions = [{ id: 'up', name: '评分上升', color: '#ad7139' }, { id: 'down', name: '评分下降', color: '#25816c' }, { id: 'same', name: '评分不变', color: '#82938e' }, { id: 'missing', name: '无配对值', color: '#abb6b0' }]
const groupRows = computed(() => pairs.value.filter(row => (!category.value || (row.category || '未分类') === category.value) && `${row.id} ${row.label || ''}`.toLowerCase().includes(search.value.trim().toLowerCase())))
const filtered = computed(() => groupRows.value.filter(row => !direction.value || row.direction === direction.value).sort((a, b) => (a.category || '').localeCompare(b.category || '', 'zh-CN') || (a.label || a.id).localeCompare(b.label || b.id, 'zh-CN')))
const size = computed(() => props.compact ? 6 : 10)
const pages = computed(() => Math.max(1, Math.ceil(filtered.value.length / size.value)))
const visible = computed(() => filtered.value.slice((page.value - 1) * size.value, page.value * size.value))
watch([category, search, direction, () => props.tasks, size], () => { page.value = 1 })
watch(() => props.context, () => { category.value = ''; search.value = ''; direction.value = ''; page.value = 1 })
const color = (key: string) => directions.find(item => item.id === key)?.color || '#82938e'
function choose(id: string) { if (!props.readOnly) emit('select', id) }
function exportSvg() {
  if (!plot.value) return
  const copy = plot.value.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  downloadBlob(new Blob([new XMLSerializer().serializeToString(copy)], { type: 'image/svg+xml;charset=utf-8' }), `${props.context || 'celllens'}_metabolic-tasks_page-${page.value}.svg`)
}
function exportCsv() {
  downloadCsv(`${props.context || 'celllens'}_metabolic-tasks.csv`, ['研究记录', '结果类型', '任务', '名称', '分类', '对照', targetLabel.value, '差值', '说明'], filtered.value.map(row => [props.context, props.sourceKind, row.id, row.label, row.category, row.control, row.target, row.delta, '表达派生支持评分；非代谢通量']))
}
</script>

<template>
  <section class="metabolic-atlas" aria-label="代谢任务可视化">
    <header><div><p class="atlas-eyebrow">METABOLIC RESPONSE</p><h3>{{ compact ? '代谢任务变化' : '代谢任务响应图谱' }}</h3><p class="atlas-subtitle">连接同一任务的两组评分，观察变化方向与幅度。</p></div><div v-if="!compact" class="atlas-exports"><button class="btn btn-sm" :disabled="!visible.length" @click="exportSvg">导出图像 · SVG</button><button class="btn btn-sm" :disabled="!filtered.length" @click="exportCsv">导出筛选 · CSV</button></div></header>
    <div class="atlas-filters"><label>任务分类<select v-model="category"><option value="">全部分类 · {{ tasks.length }} 项</option><option v-for="group in groups" :key="group" :value="group">{{ group }}</option></select></label><label class="atlas-search">查找任务<input v-model="search" placeholder="输入任务名称或关键词" type="search" /></label></div>
    <div class="direction-filters" aria-label="按评分变化方向筛选"><button :aria-pressed="!direction" @click="direction = ''">全部 {{ groupRows.length }}</button><button v-for="item in directions" :key="item.id" :aria-pressed="direction === item.id" @click="direction = direction === item.id ? '' : item.id"><i :style="{ background: item.color }" />{{ item.name }} <strong>{{ groupRows.filter(row => row.direction === item.id).length }}</strong></button></div>
    <div v-if="visible.length" class="atlas-chart">
      <svg ref="plot" xmlns="http://www.w3.org/2000/svg" :viewBox="`0 0 940 ${100 + visible.length * 66}`" width="940" :height="100 + visible.length * 66" font-family="Arial, Microsoft YaHei, sans-serif" font-size="13" fill="#24453b" role="img" aria-label="代谢任务配对评分图">
        <title>代谢任务配对评分 · {{ targetLabel }}</title><desc>{{ context }}；{{ sourceKind }}；分类 {{ category || '全部' }}；筛选 {{ direction || '全部方向' }}；搜索 {{ search || '无' }}；第 {{ page }} 页。各行独立尺度，只比较同一任务；评分不是通量。</desc>
        <rect width="940" height="100%" fill="#fcfdf9" rx="12" />
        <text x="18" y="27" font-size="12" fill="#647d72">任务 / 分类</text><circle cx="357" cy="23" r="5" fill="#fcfdf9" stroke="#82938e" stroke-width="2"/><text x="370" y="27">对照</text><circle cx="440" cy="23" r="5" fill="#25816c"/><text x="453" y="27">{{ targetLabel }}</text><text x="666" y="27" fill="#647d72">对照 → {{ targetLabel }}</text><text x="916" y="27" text-anchor="end" fill="#647d72">评分差值</text>
        <g v-for="(row, index) in visible" :key="row.id" :transform="`translate(0 ${42 + index * 66})`" :role="readOnly ? undefined : 'button'" :tabindex="readOnly ? undefined : 0" :aria-label="`${row.label || row.id}，对照 ${scoreLabel(row.control)}，${targetLabel} ${scoreLabel(row.target)}，查看任务`" @click="choose(row.id)" @keydown.enter="choose(row.id)" @keydown.space.prevent="choose(row.id)" class="atlas-row">
          <title>{{ row.label || row.id }} · {{ row.id }}</title><rect x="8" y="0" width="924" height="62" rx="7" :fill="selectedId === row.id ? '#e4f0e7' : index % 2 ? '#f2f6ee' : '#fcfdf9'" :stroke="selectedId === row.id ? '#25816c' : 'none'" />
          <text x="18" y="25" font-size="14">{{ (row.label || row.id).length > 24 ? (row.label || row.id).slice(0, 24) + '…' : row.label || row.id }}</text><text x="18" y="46" font-size="11" fill="#74877c">{{ row.category || '未分类' }}</text>
          <line x1="355" x2="630" y1="29" y2="29" stroke="#dce5d9" stroke-width="2"/><line :x1="355 + row.zeroPosition * 275" :x2="355 + row.zeroPosition * 275" y1="21" y2="37" stroke="#bac9bf" />
          <line v-if="row.controlPosition !== null && row.targetPosition !== null" :x1="355 + row.controlPosition * 275" :x2="355 + row.targetPosition * 275" y1="29" y2="29" :stroke="color(row.direction)" stroke-width="4" />
          <circle v-if="row.controlPosition !== null" :cx="355 + row.controlPosition * 275" cy="29" r="6" fill="#fcfdf9" stroke="#82938e" stroke-width="2"/><circle v-if="row.targetPosition !== null" :cx="355 + row.targetPosition * 275" cy="29" r="4" :fill="color(row.direction)" />
          <text x="666" y="33" font-size="12">{{ scoreLabel(row.control) }} → {{ scoreLabel(row.target) }}</text><text x="916" y="33" text-anchor="end" :fill="color(row.direction)" font-weight="600">{{ scoreLabel(row.delta, true) }}</text>
        </g><text x="18" :y="80 + visible.length * 66" font-size="11" fill="#647d72">各行独立尺度 · 仅比较同一任务 · 表达派生支持评分，非代谢通量</text>
      </svg>
    </div><p v-else class="atlas-empty">没有符合条件的任务，请调整分类或关键词。</p>
    <footer><span>共 {{ filtered.length }} 项 · 第 {{ page }} / {{ pages }} 页<span v-if="!readOnly"> · 点击任务查看关联反应</span></span><div><button :disabled="page <= 1" @click="page--">上一页</button><button :disabled="page >= pages" @click="page++">下一页</button></div></footer>
  </section>
</template>

<style scoped>
.metabolic-atlas{min-width:0;color:var(--ink)}header{display:flex;justify-content:space-between;gap:18px;align-items:start}.atlas-eyebrow{font-size:11px;letter-spacing:2px;color:var(--primary);margin:0 0 8px}h3{font-size:22px;font-weight:500;margin:0}.atlas-subtitle{font-size:13px;color:var(--muted);line-height:1.8;margin:8px 0 16px}.atlas-exports{display:flex;gap:8px;flex-wrap:wrap}.atlas-filters{display:flex;gap:16px;margin:8px 0 16px}.atlas-filters label{display:grid;gap:7px;font-size:12px;color:var(--muted);flex:1;min-width:0}select,input{width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--ink);padding:10px 12px;font:inherit;min-width:0}.direction-filters{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 14px}.direction-filters button{display:flex;gap:6px;align-items:center;border:1px solid var(--border);background:transparent;color:var(--muted);border-radius:20px;padding:7px 10px;font-size:12px;cursor:pointer}.direction-filters button[aria-pressed=true]{background:var(--primary-weak);border-color:var(--primary);color:var(--primary-strong)}i{width:7px;height:7px;border-radius:50%}.atlas-chart{overflow-x:auto;border:1px solid var(--border);border-radius:12px}.atlas-chart svg{display:block;width:100%;height:auto;min-width:650px}.atlas-row{cursor:pointer}.atlas-row:hover rect,.atlas-row:focus rect{stroke:#25816c;stroke-width:1.5}.atlas-row:focus{outline:none}footer{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-top:14px;font-size:12px;color:var(--muted)}footer div{display:flex;gap:8px}footer button{border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--ink);padding:7px 10px;cursor:pointer}button:disabled{opacity:.4;cursor:default}button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--primary);outline-offset:2px}.atlas-empty{padding:30px;color:var(--muted);text-align:center}@media(max-width:700px){header{flex-direction:column}.atlas-filters{flex-direction:column}footer{flex-wrap:wrap}}
</style>
