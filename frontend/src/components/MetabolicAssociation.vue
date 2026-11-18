<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { scoreLabel } from '../utils/metabolicVisualization'
import { downloadBlob } from '../utils/csv'
type NodeScore = { id: string; control: number | null; observed: number | null; observed_delta: number | null }
const props = defineProps<{ task: NodeScore; label: string; reaction: NodeScore & { genes: Array<NodeScore & { present: boolean }> }; context: string }>()
const emit = defineEmits<{ gene: [id: string] }>()
const page = ref(1), plot = ref<SVGSVGElement | null>(null)
const pages = computed(() => Math.max(1, Math.ceil(props.reaction.genes.length / 6)))
const genes = computed(() => props.reaction.genes.slice((page.value - 1) * 6, page.value * 6))
const height = computed(() => Math.max(280, genes.value.length * 76 + 100))
const middle = computed(() => height.value / 2)
watch(() => props.reaction.id, () => { page.value = 1 })
function tint(delta: number | null) { return delta == null ? '#82938e' : delta > 0 ? '#ad7139' : delta < 0 ? '#25816c' : '#82938e' }
function exportSvg() {
  if (!plot.value) return
  const copy = plot.value.cloneNode(true) as SVGSVGElement
  copy.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  downloadBlob(new Blob([new XMLSerializer().serializeToString(copy)], { type: 'image/svg+xml;charset=utf-8' }), `${props.context}_task-association_page-${page.value}.svg`)
}
</script>
<template>
  <div class="association">
    <div class="association-toolbar"><span><i class="up"/>评分／表达上升 <i class="down"/>评分／表达下降</span><button class="btn btn-sm" @click="exportSvg">导出关联图 · SVG</button></div>
    <div class="association-scroll"><svg ref="plot" xmlns="http://www.w3.org/2000/svg" width="960" :height="height" :viewBox="`0 0 960 ${height}`" font-family="Arial, Microsoft YaHei, sans-serif" font-size="13" fill="#24453b" role="img" aria-label="基因、反应与代谢任务关联图">
      <title>{{ label }} · 基因与反应关联</title><desc>{{ context }}；任务 {{ task.id }}；反应 {{ reaction.id }}；第 {{ page }} 页，共 {{ pages }} 页；知识库关联，不代表因果或代谢流向。基因表达与任务、反应评分不是同一尺度。</desc>
      <rect width="960" :height="height" rx="14" fill="#f3f7ef"/><text x="28" y="30" font-size="12" fill="#617b6c">01 / 基因表达</text><text x="370" y="30" font-size="12" fill="#617b6c">02 / 关联反应</text><text x="678" y="30" font-size="12" fill="#617b6c">03 / 代谢任务</text>
      <path v-for="(gene, index) in genes" :key="`edge-${gene.id}`" :d="`M 280 ${78 + index * 76} C 330 ${78 + index * 76}, 320 ${middle}, 370 ${middle}`" stroke="#b6cab9" stroke-width="2" fill="none"/>
      <path :d="`M 600 ${middle} C 630 ${middle}, 648 ${middle}, 678 ${middle}`" stroke="#7ba08e" stroke-width="3" fill="none"/>
      <g v-for="(gene, index) in genes" :key="gene.id" :transform="`translate(28 ${50 + index * 76})`" :role="gene.present ? 'button' : undefined" :tabindex="gene.present ? 0 : undefined" :aria-label="`查看基因 ${gene.id}`" @click="gene.present && emit('gene', gene.id)" @keydown.enter="gene.present && emit('gene', gene.id)" @keydown.space.prevent="gene.present && emit('gene', gene.id)" class="gene-node">
        <title>{{ gene.id }}：对照 {{ scoreLabel(gene.control) }}；扰动实测 {{ scoreLabel(gene.observed) }}</title><rect width="252" height="58" rx="8" fill="#fcfdf9" stroke="#d1decf"/><rect width="4" height="58" rx="2" :fill="tint(gene.observed_delta)"/><text x="16" y="23" font-weight="600">{{ gene.id.length > 20 ? gene.id.slice(0,20) + '…' : gene.id }}</text><text x="16" y="44" font-size="11" fill="#647d72">{{ gene.present ? `${scoreLabel(gene.control)} → ${scoreLabel(gene.observed)}` : '本次输入未提供' }}</text><text x="236" y="23" text-anchor="end" font-size="11" :fill="tint(gene.observed_delta)">{{ scoreLabel(gene.observed_delta, true) }}</text>
      </g>
      <text v-if="!genes.length" x="28" :y="middle" fill="#647d72">本版本没有关联基因记录</text>
      <g :transform="`translate(370 ${middle - 62})`"><rect width="230" height="124" rx="12" fill="#fcfdf9" stroke="#b7cdb8"/><text x="18" y="28" font-weight="600">{{ reaction.id }}</text><text x="18" y="54" fill="#647d72" font-size="11">反应支持评分 · 对照 → 实测</text><text x="18" y="78">{{ scoreLabel(reaction.control) }} → {{ scoreLabel(reaction.observed) }}</text><text x="18" y="106" :fill="tint(reaction.observed_delta)">Δ {{ scoreLabel(reaction.observed_delta, true) }}</text></g>
      <g :transform="`translate(678 ${middle - 73})`"><title>{{ label }} · {{ task.id }}</title><rect width="254" height="146" rx="12" fill="#204e3d"/><text x="18" y="29" fill="#ffffff" font-size="14">{{ label.slice(0,15) }}</text><text v-if="label.length > 15" x="18" y="50" fill="#ffffff" font-size="12">{{ label.slice(15,32) }}{{ label.length > 32 ? '…' : '' }}</text><text x="18" y="76" fill="#c6dbc9" font-size="11">任务支持评分 · 对照 → 实测</text><text x="18" y="101" fill="#ffffff">{{ scoreLabel(task.control) }} → {{ scoreLabel(task.observed) }}</text><text x="18" y="127" fill="#e1d59f">Δ {{ scoreLabel(task.observed_delta, true) }}</text></g>
      <text x="28" :y="height - 18" font-size="11" fill="#647d72">连线表示知识库关联，不表示因果或代谢流向。节点数值分别属于基因表达、反应评分和任务评分。</text>
    </svg></div>
    <div class="association-pagination"><span>当前反应关联 {{ reaction.genes.length }} 个基因 · 点击基因查看表达响应</span><div v-if="pages > 1"><button class="btn btn-sm" :disabled="page <= 1" @click="page--">上一组</button> {{ page }} / {{ pages }} <button class="btn btn-sm" :disabled="page >= pages" @click="page++">下一组</button></div></div>
  </div>
</template>
<style scoped>
.association{margin-top:18px;min-width:0}.association-toolbar,.association-pagination{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:12px 0}.association-toolbar span{display:flex;align-items:center;gap:8px}.association-toolbar i{width:7px;height:7px;border-radius:50%;display:inline-block}.up{background:#ad7139}.down{background:#25816c;margin-left:12px}.association-scroll{overflow:auto;border:1px solid var(--border);border-radius:14px}.association svg{width:100%;height:auto;min-width:700px;display:block}.gene-node[role=button]{cursor:pointer}.gene-node[role=button]:hover rect:first-of-type,.gene-node:focus rect:first-of-type{stroke:#25816c;stroke-width:2}.gene-node:focus{outline:none}
</style>
