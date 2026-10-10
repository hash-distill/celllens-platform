<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import { ApiError } from '../../api/http'
import type { TaskTraceResponse } from '../../types/trace'
import { fmtDelta, fmtNumber } from '../../utils/format'

const props = defineProps<{ runId: string; taskId: string; taskLabel: string; available?: boolean | null }>()
const TraceNetwork = defineAsyncComponent(() => import('./TraceNetwork.vue'))
const spatial = ref(false)
const data = ref<TaskTraceResponse | null>(null)
const error = ref<ApiError | null>(null)
const loading = ref(false)
const selectedReaction = ref('')
const reaction = computed(() => data.value?.reactions.find(r => r.id === selectedReaction.value))
let controller: AbortController | undefined
async function load() {
  controller?.abort()
  const active = new AbortController()
  controller = active
  data.value = null; error.value = null; loading.value = true; selectedReaction.value = ''
  if (props.available === false) {
    loading.value = false
    return
  }
  try {
    const result = await api.getTaskTrace(props.runId, props.taskId, active.signal)
    if (active.signal.aborted) return
    data.value = result
    selectedReaction.value = result.reactions[0]?.id ?? ''
  } catch (err) {
    if (active.signal.aborted) return
    error.value = err instanceof ApiError ? err : new ApiError({kind:'network', status:null, code:null, message:'追溯结果读取失败', endpoint:'/task-trace'})
  } finally { if (!active.signal.aborted) loading.value = false }
}
watch(() => [props.runId, props.taskId, props.available], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="task-trace" aria-label="任务证据追溯">
    <header class="trace-heading"><div><span class="micro">CELLLENS / EVIDENCE TRACE</span><h2>从功能变化，追溯关联依据。</h2></div><span class="trace-kind">知识库关联</span></header>
    <p v-if="loading" class="trace-message" role="status">正在读取本次运行的任务关联记录…</p>
    <div v-else-if="available === false" class="trace-message" role="status"><h3>本次运行尚无关联追溯记录</h3><p>当前任务的分数与覆盖信息仍可查看。本次保存结果未提供该任务的反应—基因追溯；完整关联需由新分析生成。</p></div>
    <div v-else-if="error" class="trace-message"><h3>{{ error.code === 'TASK_TRACE_UNAVAILABLE' ? '本次运行尚无关联追溯记录' : error.code === 'TASK_NOT_FOUND' ? '未找到该任务的关联记录' : '关联追溯暂时不可用' }}</h3><p>{{ error.code === 'TASK_TRACE_UNAVAILABLE' ? '已有表达与代谢结果仍可查看。使用当前版本重新运行后，可保存任务—反应—基因关联及数据库版本。合成记录没有真实知识关联产物。' : error.message }}</p><button v-if="error.status !== 404" class="btn btn-sm" @click="load">重试追溯</button></div>
    <template v-else-if="data">
      <p class="trace-caption">连线表示已记录的知识库组成关系；数值来自本次运行。相关基因不等于已验证的因果贡献。</p>
      <button class="btn btn-sm" :aria-pressed="spatial" @click="spatial = !spatial">{{ spatial ? '收起空间网络' : '探索三维功能网络' }}</button>
      <TraceNetwork v-if="spatial" :data="data" :selected-reaction="selectedReaction" @select="selectedReaction = $event" />
      <div class="trace-network">
        <div class="trace-task"><span class="column-label">代谢任务</span><h3>{{ data.task.label || taskLabel }}</h3><p>{{ data.task.category || '未提供功能分类' }}</p><strong>{{ fmtDelta(data.task.predicted_delta) }}</strong><span class="trace-unit">任务分数变化</span><dl><dt>对照</dt><dd>{{ fmtNumber(data.task.control) }}</dd><dt>预测</dt><dd>{{ fmtNumber(data.task.predicted) }}</dd></dl><small class="mono">{{ data.task.id }}</small></div>
        <div class="trace-connector" aria-hidden="true">←<small>组成</small></div>
        <div class="trace-reactions"><span class="column-label">关联反应 · {{ data.total_reactions }}</span><p v-if="!data.reactions.length" class="trace-caption">知识库未提供关联反应。</p><div class="trace-scroll"><button v-for="row in data.reactions" :key="row.id" class="reaction-node" :class="{active:selectedReaction === row.id}" :aria-pressed="selectedReaction === row.id" @click="selectedReaction = row.id"><span>{{ row.label }}<small class="mono">{{ row.id }}</small></span><strong>{{ fmtDelta(row.predicted_delta, 3) }}</strong></button></div><p v-if="data.truncated" class="trace-caption">已截取 {{ data.reactions.length }} / {{ data.total_reactions }} 条反应。</p></div>
        <div class="trace-connector" aria-hidden="true">←<small>关联</small></div>
        <div class="trace-genes"><span class="column-label">{{ reaction?.id ?? '所选反应' }} / 相关基因</span><template v-if="reaction"><p class="reaction-values">反应分数：{{ fmtNumber(reaction.control) }} → {{ fmtNumber(reaction.predicted) }}</p><p v-if="!reaction.genes.length" class="trace-caption">未提供关联基因。</p><div class="trace-scroll"><div v-for="g in reaction.genes" :key="g.id" class="trace-gene"><span class="mono">{{ g.label || g.id }}</span><span>{{ fmtDelta(g.predicted_delta, 3) }}</span><small>表达 {{ fmtNumber(g.control, 3) }} → {{ fmtNumber(g.predicted, 3) }}</small></div></div><p v-if="reaction.truncated" class="trace-caption">已截取 {{ reaction.genes.length }} / {{ reaction.total_genes }} 个基因。</p></template></div>
      </div>
      <details class="trace-provenance"><summary>数据库 {{ data.database_version }} · 查看追溯来源</summary><p>清单 SHA-256 <code>{{ data.database_provenance.manifest_sha256 }}</code></p><p>运行 <code>{{ data.run_id }}</code> · 关联类型：知识库关联</p><p>本视图未提供评分决定基因归因；缺失数值显示“未提供”。</p><p v-for="warning in data.warnings" :key="warning">{{ warning }}</p></details>
    </template>
  </section>
</template>

<style scoped>
.task-trace{margin-top:16px;border:1px solid var(--border-strong);background:var(--card);padding:24px;min-width:0}.trace-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.trace-heading .micro{font-size:9px;color:var(--primary);letter-spacing:.13em}.trace-heading h2{font-size:19px;font-weight:500;margin:8px 0}.trace-kind{border:1px solid #b6caba;padding:4px 8px;color:var(--primary);font-size:10px;white-space:nowrap}.trace-caption{font-size:11px;color:var(--muted);line-height:1.8}.trace-network{display:grid;grid-template-columns:minmax(140px,1fr) 28px minmax(160px,1.3fr) 28px minmax(140px,1fr);margin:22px 0;align-items:stretch}.trace-task{background:#ecf2eb;padding:20px;display:flex;flex-direction:column;min-width:0}.column-label{font-size:10px;color:var(--primary);letter-spacing:.05em;display:block;margin-bottom:15px;overflow-wrap:anywhere}.trace-task h3{font-size:15px;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.trace-task p{font-size:10px;color:var(--muted)}.trace-task>strong{font:32px Georgia,serif;margin-top:10px}.trace-unit{font-size:10px;color:var(--muted);margin:5px 0}.trace-task dl{display:grid;grid-template-columns:1fr 1fr;font-size:11px}.trace-task dd{margin:0;text-align:right}.trace-task small{font-size:9px;color:var(--muted);overflow-wrap:anywhere}.trace-connector{display:flex;flex-direction:column;justify-content:center;align-items:center;color:#809e90;font-size:23px}.trace-connector small{font-size:8px}.trace-reactions,.trace-genes{padding:15px 10px;border:1px solid var(--border);min-width:0}.trace-scroll{max-height:275px;overflow:auto}.reaction-node{display:flex;width:100%;align-items:center;justify-content:space-between;gap:12px;background:transparent;border:0;border-bottom:1px solid var(--border);color:var(--ink);padding:12px 8px;cursor:pointer;text-align:left;font:11px var(--font)}.reaction-node>span{overflow-wrap:anywhere}.reaction-node small{display:block;font-size:9px;color:var(--muted);margin-top:4px}.reaction-node strong{font:12px Consolas,monospace;white-space:nowrap}.reaction-node.active{background:#edf3ec;box-shadow:inset 2px 0 var(--primary)}.trace-gene{display:grid;grid-template-columns:1fr auto;gap:5px;padding:10px 6px;border-bottom:1px solid var(--border);font-size:11px}.trace-gene small{grid-column:1/-1;font-size:9px;color:var(--muted)}.reaction-values{font-size:10px;color:var(--muted)}.trace-provenance{font-size:10px;color:var(--muted);border-top:1px solid var(--border);padding-top:12px}.trace-provenance summary{cursor:pointer;color:var(--primary)}.trace-provenance code{overflow-wrap:anywhere}.trace-message{padding:22px 0;color:var(--muted);font-size:12px;line-height:1.8}.trace-message h3{font-size:14px;color:var(--ink);font-weight:500}@media(max-width:850px){.trace-network{grid-template-columns:1fr}.trace-connector{padding:6px;transform:none;font-size:18px;flex-direction:row;gap:8px}.trace-connector small{font-size:10px}.task-trace{padding:18px}.trace-heading h2{font-size:16px}.trace-heading{gap:10px}}
</style>
