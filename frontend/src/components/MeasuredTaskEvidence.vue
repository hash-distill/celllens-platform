<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiFetch } from '../api/http'
import { taskName, metabolicGroupName } from '../utils/biologyLocale'
import MetabolicAssociation from './MetabolicAssociation.vue'
import { downloadBlob } from '../utils/csv'

const props = defineProps<{ analysisId: string; taskId: string }>()
const emit = defineEmits<{ 'select-gene': [id: string] }>()
interface Score { control: number | null; observed: number | null; observed_delta: number | null }
interface Gene extends Score { id: string; present: boolean }
interface Evidence {
  analysis_id: string
  analysis_manifest_sha256?: string
  source_kind: 'measured'
  relationship_kind: 'knowledge_association'
  database_version: string
  database_provenance: { manifest_sha256: string }
  task: Score & { id: string; category: string | null; subcategory: string | null }
  coverage: { present: number; total: number; missing: string[] }
  genes: Gene[]
  reactions: Array<Score & { id: string; gene_rule: string | null; genes: Gene[] }>
  limitations: string[]
}
const data = ref<Evidence | null>(null), loading = ref(false), error = ref(''), refresh = ref(0)
const reactionId = ref('')
const reaction = computed(() => data.value?.reactions.find(item => item.id === reactionId.value) ?? null)
const presentGenes = computed(() => data.value?.genes.filter(item => item.present) ?? [])
watch([() => props.analysisId, () => props.taskId, refresh], async (_value, _old, cleanup) => {
  const controller = new AbortController()
  cleanup(() => controller.abort())
  data.value = null; error.value = ''; reactionId.value = ''; loading.value = false
  if (!props.taskId) return
  loading.value = true
  try {
    const result = await apiFetch<Evidence>(`/measured/analyses/${encodeURIComponent(props.analysisId)}/task-evidence`, {
      query: { task: props.taskId }, signal: controller.signal,
    })
    if (controller.signal.aborted) return
    if (result.analysis_id !== props.analysisId || result.task.id !== props.taskId || result.source_kind !== 'measured' || result.relationship_kind !== 'knowledge_association') throw new Error('任务证据与当前分析不一致，已停止展示。')
    data.value = result; reactionId.value = result.reactions[0]?.id ?? ''
  } catch (reason) {
    if (!controller.signal.aborted) error.value = reason instanceof Error ? reason.message : '任务证据读取失败'
  } finally { if (!controller.signal.aborted) loading.value = false }
}, { immediate: true })
function value(number: number | null | undefined) {
  return number == null || !Number.isFinite(number) ? '未提供' : number.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}
function exportEvidence() {
  if (data.value) downloadBlob(new Blob([JSON.stringify(data.value, null, 2)], { type: 'application/json' }), `${props.analysisId}_task-evidence.json`)
}
</script>

<template>
  <section class="task-evidence card" aria-label="代谢任务关联详情">
    <header><div><span class="eyebrow">GENE · REACTION · TASK</span><h2>任务关联图</h2><p>从任务评分追溯关联反应，查看参与基因的表达响应。</p></div><button v-if="data" class="btn btn-sm" @click="exportEvidence">导出任务数据 · JSON</button></header>
    <p v-if="!taskId" class="muted">选择一项代谢任务，查看关联反应与基因。</p>
    <p v-else-if="loading" role="status">正在加载任务关联与本次评分…</p>
    <div v-else-if="error" class="notice notice-warn" role="alert"><p>{{ error }}</p><button class="btn btn-sm" @click="refresh++">重新读取</button></div>
    <template v-else-if="data">
      <div class="evidence-identity"><div><span class="category-label">{{ metabolicGroupName(data.task.category) }}</span><h3>{{ taskName(data.task.id) }}</h3><p>{{ data.task.id }}</p></div><label v-if="data.reactions.length">关联反应 · {{ data.reactions.length }} 项<select v-model="reactionId"><option v-for="item in data.reactions" :key="item.id" :value="item.id">{{ item.id }}</option></select></label></div>
      <MetabolicAssociation v-if="reaction" :key="analysisId + taskId" :task="data.task" :label="taskName(data.task.id)" :reaction="reaction" :context="analysisId" @gene="emit('select-gene', $event)" />
      <p v-else class="muted">本版本没有该任务的关联反应记录。任务评分：对照 {{ value(data.task.control) }} → 实测 {{ value(data.task.observed) }}。</p>
      <details class="quality-details"><summary>数据质量与计算依据 <span>{{ data.coverage.present }} / {{ data.coverage.total }} 个关联基因有输入 · {{ data.coverage.missing.length }} 个缺失</span></summary>
        <p class="unit-note">任务和反应值为表达派生支持评分；基因值为平均表达。输入完整性用于判断分数的解释范围，不代表功能已得到实验验证。</p>
        <p class="muted">本次缺失基因：{{ data.coverage.missing.join(' · ') || '无' }}</p>
        <p class="muted">有输入的关联基因：{{ presentGenes.map(gene => gene.id).join(' · ') || '无' }}</p>
        <template v-if="reaction"><div class="reaction-rule"><span>当前反应的知识库 GPR 规则</span><code>{{ reaction.gene_rule || '本版本未提供规则' }}</code></div>
        <div class="table-wrap"><table class="table"><thead><tr><th>反应关联基因</th><th>输入状态</th><th>对照</th><th>扰动实测</th><th>表达差值</th></tr></thead><tbody><tr v-for="gene in reaction.genes" :key="gene.id"><td><button v-if="gene.present" class="gene-link" @click="emit('select-gene', gene.id)">{{ gene.id }} ↗</button><span v-else>{{ gene.id }}</span></td><td>{{ gene.present ? '有输入' : '未提供' }}</td><td>{{ value(gene.control) }}</td><td>{{ value(gene.observed) }}</td><td>{{ value(gene.observed_delta) }}</td></tr></tbody></table></div></template>
        <p>知识库：{{ data.database_version }}</p><p>本次分析清单</p><code>{{ data.analysis_manifest_sha256 || '未提供' }}</code><p>知识库清单</p><code>{{ data.database_provenance.manifest_sha256 }}</code><ul><li v-for="line in data.limitations" :key="line">{{ line }}</li></ul>
      </details>
    </template>
  </section>
</template>
<style scoped>
.task-evidence{min-width:0}.task-evidence header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.eyebrow{font-size:11px;letter-spacing:2px;color:var(--primary)}h2{font-size:24px;font-weight:500;margin:10px 0}header p,.evidence-identity p{color:var(--muted);font-size:13px;line-height:1.8;margin:0}.evidence-identity{margin-top:22px;padding-top:20px;border-top:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:20px}h3{font-size:22px;font-weight:500;margin:10px 0 7px}.category-label{display:inline-block;border-radius:20px;padding:5px 10px;background:var(--primary-weak);color:var(--primary-strong);font-size:12px}label{display:grid;gap:8px;font-size:12px;color:var(--muted);min-width:190px}select{padding:10px 12px;max-width:100%;background:var(--card);color:var(--ink);border:1px solid var(--border);border-radius:7px;font:inherit}.reaction-rule{margin:16px 0;padding:15px;border-radius:8px;background:var(--surface-soft)}.reaction-rule span{display:block;font-size:12px;color:var(--muted);margin-bottom:7px}.reaction-rule code{font-size:13px;overflow-wrap:anywhere}.unit-note{font-size:13px;line-height:1.9;color:var(--muted)}.table-wrap{max-width:100%;overflow:auto}.table{min-width:510px}.table th,.table td{font-size:13px}.gene-link{border:0;background:transparent;color:var(--primary-strong);font:inherit;cursor:pointer;text-decoration:underline;text-underline-offset:3px}.quality-details{border-top:1px solid var(--border);padding-top:18px;margin-top:22px;font-size:12px;line-height:1.9;color:var(--muted)}.quality-details code{display:block;overflow-wrap:anywhere}summary{cursor:pointer;color:var(--primary);font-size:14px}summary span{font-size:12px;color:var(--muted);margin-left:16px}@media(max-width:700px){.task-evidence header,.evidence-identity{flex-direction:column;align-items:stretch}.quality-details summary span{display:block;margin:6px 0}h2{font-size:21px}}
</style>
