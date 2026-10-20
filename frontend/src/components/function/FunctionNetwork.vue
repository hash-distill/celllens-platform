<script setup lang="ts">
import { computed } from 'vue'
import { KIND_LABEL, nodeColor, nodeTextColor, nodeValue, scaleFor } from '../../utils/functionNetwork'
import type { FunctionNode, ValueSource, NodeKind } from '../../utils/functionNetwork'
import { fmtNumber } from '../../utils/format'
const props = defineProps<{ nodes: FunctionNode[]; source: ValueSource; label: string; selected: string }>()
const emit = defineEmits<{ select: [kind: NodeKind, id: string] }>()
const height = computed(() => Math.max(260, props.nodes.filter(node => node.kind === 'gene').length * 52 + 90))
const kinds: NodeKind[] = ['gene', 'reaction', 'task']
function color(node: FunctionNode) { return nodeColor(nodeValue(node.score, props.source), scaleFor(props.nodes, node.kind, props.source === 'delta')) }
function textColor(node: FunctionNode) { return nodeTextColor(nodeValue(node.score,props.source),scaleFor(props.nodes,node.kind,props.source==='delta')) }
function range(kind: NodeKind) {
  const max = fmtNumber(scaleFor(props.nodes,kind,props.source==='delta'),3)
  const signed = props.source==='delta' || props.nodes.some(node => node.kind===kind && ['control','predicted','observed'].some(source => (nodeValue(node.score,source as ValueSource) ?? 0)<0))
  return signed ? '−'+max+'…+'+max : '0…'+max
}
</script>
<template>
  <article class="network-panel" :data-source="source">
    <header><strong>{{ label }}</strong><small>{{ source === 'delta' ? '预测 − 对照' : source === 'observed' ? '对照 + 保存的观测差值' : '保存的群体均值' }}</small></header>
    <div class="network-scroll">
      <svg :viewBox="`0 0 560 ${height}`" role="group" :aria-label="label+'功能关联网络'">
        <text v-for="(kind,index) in kinds" :key="kind" :x="92+index*185" y="25" text-anchor="middle" class="column-label">{{ KIND_LABEL[kind] }}</text>
        <template v-for="node in nodes" :key="node.kind+node.score.id">
          <path v-if="node.kind==='gene'" :d="`M ${node.x+67} ${node.y} L 211 ${height/2}`" class="association" />
          <path v-if="node.kind==='reaction'" :d="`M 345 ${node.y} L 395 ${node.y}`" class="association" />
        </template>
        <g v-for="node in nodes" :key="node.kind+node.score.id" class="function-node" :class="{selected:selected===node.kind+':'+node.score.id,missing:nodeValue(node.score,source)===null}"
          role="button" tabindex="0" :aria-label="`${KIND_LABEL[node.kind]} ${node.score.label} ${fmtNumber(nodeValue(node.score,source))}`" :aria-pressed="selected===node.kind+':'+node.score.id"
          :data-node="node.kind+':'+node.score.id" :data-value="nodeValue(node.score,source)" :transform="`translate(${node.x},${node.y})`"
          @click="emit('select',node.kind,node.score.id)" @keydown.enter="emit('select',node.kind,node.score.id)" @keydown.space.prevent="emit('select',node.kind,node.score.id)">
          <title>{{ node.score.label }} · {{ fmtNumber(nodeValue(node.score,source)) }}</title>
          <rect x="-67" y="-21" width="134" height="42" :rx="node.kind==='gene'?21:4" :fill="color(node)" />
          <text y="-5" text-anchor="middle" class="node-name" :fill="textColor(node)">{{ node.kind==='task'?'当前任务':(node.kind==='gene'?node.score.label:node.score.id).slice(0,10) }}{{ node.kind!=='task' && (node.kind==='gene'?node.score.label:node.score.id).length>10?'…':'' }}</text>
          <text y="15" text-anchor="middle" class="node-value" :fill="textColor(node)">{{ fmtNumber(nodeValue(node.score,source),3) }}</text>
        </g>
      </svg>
    </div>
    <footer><span v-for="kind in kinds" :key="kind">{{ KIND_LABEL[kind] }}：{{ range(kind) }}</span></footer>
  </article>
</template>
<style scoped>
.network-panel{min-width:0;border:1px solid var(--border);background:var(--figure-soft-bg)}.network-panel header{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:14px 16px;border-bottom:1px solid var(--border)}header strong{font-size:13px;font-weight:500}header small{font-size:9px;color:var(--muted)}.network-scroll{max-height:390px;overflow:auto}svg{display:block;width:100%;min-width:310px}.column-label{fill:var(--network-column);font-size:20px}.association{fill:none;stroke:var(--network-association);stroke-width:1.3}.function-node{cursor:pointer;outline:none}.function-node rect{stroke:var(--network-node-stroke);stroke-width:1}.function-node:hover rect,.function-node:focus rect,.function-node.selected rect{stroke:var(--network-node-active);stroke-width:3}.function-node.missing rect{stroke-dasharray:4 3}.node-name{font:20px Consolas,monospace}.node-value{font:18px Consolas,monospace}footer{display:flex;flex-wrap:wrap;gap:10px;padding:12px;font-size:9px;color:var(--muted);border-top:1px solid var(--border)}
</style>
