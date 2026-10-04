<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore } from '../stores/run'
import { fmtDelta, STATUS_LABEL } from '../utils/format'
const props = defineProps<{ runId?: string }>()
const runs = useRunStore()
const entry = computed(() => props.runId ? runs.entry(props.runId) : null)
const genes = computed(() => entry.value?.summary.data?.top_genes.slice(0, 4) ?? [])
const maxDelta = computed(() => Math.max(1e-9, ...genes.value.map(g => Math.abs(g.predicted_delta))))
</script>
<template>
  <section class="experiment-dock" aria-label="结果摘要">
    <div class="dock-heading"><span class="dock-active">结果摘要</span><span class="micro">{{ entry?.record ? STATUS_LABEL[entry.record.status] : 'NEW EXPERIMENT' }}</span><RouterLink v-if="runId && entry?.record?.status === 'completed'" :to="{path:'/runs/'+encodeURIComponent(runId),query:{tab:'genes'}}">查看完整结果 →</RouterLink></div>
    <div v-if="genes.length" class="dock-results"><div v-for="gene in genes" :key="gene.id" class="dock-gene"><b class="mono">{{ gene.label }}</b><div class="mini-delta"><i :class="{positive:gene.predicted_delta>=0}" :style="{width: (Math.abs(gene.predicted_delta)/maxDelta*46)+'%'}"></i></div><span class="mono">{{ fmtDelta(gene.predicted_delta,3) }}</span></div><p class="micro">预测 − 对照；结构与数值分别展示。</p></div>
    <div v-else-if="entry?.summary.status==='error'" class="dock-empty"><div><h3>本次摘要读取失败</h3><p>{{ entry.summary.error?.message }}</p></div><button v-if="runId" class="btn btn-sm" @click="runs.retryBlock(runId,'summary')">重试</button></div>
    <div v-else-if="entry?.record" class="dock-empty"><span class="dock-index mono">—</span><div><h3>{{ entry.record.status === 'failed' ? '本次计算失败' : entry.record.status !== 'completed' ? '正在等待本次实验结果' : entry.summary.status !== 'ok' ? '正在读取本次摘要…' : '本次摘要未提供基因变化' }}</h3><p>表达变化、任务评分和来源记录以本次实验为准。</p></div></div>
    <div v-else class="dock-empty"><span class="dock-index mono">01</span><div><h3>从一次基因扰动开始</h3><p>选择细胞背景与扰动，运行后在这里查看结果。</p></div><RouterLink to="/demo" class="dock-demo">先浏览结构演示 →</RouterLink></div>
  </section>
</template>
<style scoped>
.experiment-dock{background:var(--card);border:1px solid var(--border);border-top:0;padding:0 20px 15px;min-height:136px}.dock-heading{display:flex;align-items:center;gap:22px;height:44px;border-bottom:1px solid var(--border);font-size:12px}.dock-active{height:44px;display:flex;align-items:center;border-bottom:2px solid var(--primary);color:var(--primary);font-weight:600}.dock-heading a{margin-left:auto;font-size:11px}.dock-empty{display:flex;align-items:center;gap:18px;padding-top:20px}.dock-index{font-size:34px;color:#a9b7b1;line-height:1}.dock-empty h3{font-size:14px;font-weight:500}.dock-empty p{font-size:11px;color:var(--muted);margin:6px 0 0}.dock-demo{margin-left:auto;font-size:11px}.dock-results{display:grid;grid-template-columns:1fr 1fr;gap:8px 25px;margin-top:12px}.dock-gene{display:flex;align-items:center;gap:12px;font-size:11px}.dock-gene b{width:64px;font-weight:500}.dock-gene>span{width:62px;text-align:right}.mini-delta{position:relative;flex:1;height:15px;border-left:1px solid transparent;background:linear-gradient(to right,transparent 49.6%,#d5ddd7 49.6%,#d5ddd7 50.4%,transparent 50.4%)}.mini-delta i{height:8px;position:absolute;top:4px;right:50%;background:var(--delta-down)}.mini-delta i.positive{left:50%;right:auto;background:var(--delta-up)}.dock-results p{grid-column:1/-1;margin:0}@media(max-width:767px){.dock-demo{display:none}.dock-results{grid-template-columns:1fr}.dock-empty{padding:15px 0}}
</style>
