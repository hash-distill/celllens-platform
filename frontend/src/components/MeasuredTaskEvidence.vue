<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { apiFetch } from '../api/http'
import { taskName, metabolicGroupName } from '../utils/biologyLocale'
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
  <section class="task-evidence card" aria-label="实测任务成员证据">
    <header>
      <div><span class="eyebrow">TASK → REACTION → GENE</span><h2>沿着任务，核查成员证据</h2><p>从当前实测评分追查知识库关联与输入覆盖。</p></div>
      <button v-if="data" class="btn btn-sm" @click="exportEvidence">导出任务证据 · JSON</button>
    </header>
    <p v-if="!taskId" class="muted">在上方选择一项任务，查看其关联反应、已覆盖基因与缺失成员。</p>
    <p v-else-if="loading" role="status">正在核验本次任务的知识库版本…</p>
    <div v-else-if="error" class="notice notice-warn" role="alert"><p>{{ error }}</p><button class="btn btn-sm" @click="refresh++">重新读取</button></div>
    <template v-else-if="data">
      <div class="evidence-identity"><h3>{{ taskName(data.task.id) }}</h3><p>{{ data.task.id }}</p><span>{{ metabolicGroupName(data.task.category) }}<template v-if="data.task.subcategory"> / {{ data.task.subcategory }}</template></span></div>
      <div class="trace-summary">
        <div><strong>{{ data.coverage.present }} / {{ data.coverage.total }}</strong><span>任务关联基因已覆盖</span></div>
        <div><strong>{{ data.reactions.length }}</strong><span>知识库关联反应</span></div>
        <div><strong>{{ value(data.task.observed_delta) }}</strong><span>任务评分变化 · 实测 − 对照</span></div>
      </div>
      <div class="trace-members">
        <div><h4>已覆盖成员 <span>{{ presentGenes.length }}</span></h4><div class="gene-chips"><button v-for="gene in presentGenes" :key="gene.id" @click="emit('select-gene', gene.id)">{{ gene.id }} ↗</button><span v-if="!presentGenes.length" class="muted">当前输入未覆盖成员</span></div></div>
        <div><h4>缺失成员 <span>{{ data.coverage.missing.length }}</span></h4><p class="missing-members">{{ data.coverage.missing.join(' · ') || '本次输入中未发现缺失成员' }}</p></div>
      </div>
      <div v-if="data.reactions.length" class="reaction-evidence">
        <label>检查关联反应<select v-model="reactionId"><option v-for="item in data.reactions" :key="item.id" :value="item.id">{{ item.id }}</option></select></label>
        <template v-if="reaction">
          <div class="reaction-rule"><span>知识库 GPR 规则</span><code>{{ reaction.gene_rule || '本版本未提供规则' }}</code></div>
          <div class="reaction-values"><span>对照 <strong>{{ value(reaction.control) }}</strong></span><span>扰动实测 <strong>{{ value(reaction.observed) }}</strong></span><span>差值 <strong>{{ value(reaction.observed_delta) }}</strong></span></div>
          <p class="unit-note">反应值为表达派生支持评分。下方基因值为 mean(log1p(CP10K))，两类数值不可相互比较。</p>
          <div class="table-wrap"><table class="table"><thead><tr><th>反应关联基因</th><th>输入覆盖</th><th>对照</th><th>扰动实测</th><th>表达差值</th></tr></thead><tbody><tr v-for="gene in reaction.genes" :key="gene.id"><td><button v-if="gene.present" class="gene-link" @click="emit('select-gene', gene.id)">{{ gene.id }} ↗</button><span v-else>{{ gene.id }}</span></td><td>{{ gene.present ? '已覆盖' : '缺失' }}</td><td>{{ value(gene.control) }}</td><td>{{ value(gene.observed) }}</td><td>{{ value(gene.observed_delta) }}</td></tr></tbody></table></div>
        </template>
      </div>
      <footer><p>知识库：{{ data.database_version }}</p><details><summary>查看关联来源与解释范围</summary><p>本次分析清单</p><code>{{ data.analysis_manifest_sha256 || '未提供' }}</code><p>知识库清单</p><code>{{ data.database_provenance.manifest_sha256 }}</code><ul><li v-for="line in data.limitations" :key="line">{{ line }}</li></ul></details></footer>
    </template>
  </section>
</template>

<style scoped>
.task-evidence{min-width:0}.task-evidence header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.eyebrow{font-size:11px;letter-spacing:1px;color:var(--primary)}h2{font-size:22px;font-weight:500;margin:10px 0}header p,.evidence-identity p{color:var(--muted);font-size:13px;line-height:1.8;margin:0}.evidence-identity{margin-top:22px;padding-top:20px;border-top:1px solid var(--border)}h3{font-size:19px;margin:0 0 7px}.evidence-identity>span{font-size:12px;color:var(--muted)}.trace-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border:1px solid var(--border);background:var(--surface-soft);border-radius:12px;margin:20px 0;overflow:hidden}.trace-summary>div{padding:19px;border-right:1px solid var(--border)}.trace-summary>div:last-child{border:0}.trace-summary strong{display:block;font-size:25px;color:var(--primary-strong);font-weight:500}.trace-summary span{display:block;font-size:12px;color:var(--muted);margin-top:8px}.trace-members{display:grid;grid-template-columns:1fr 1fr;gap:24px}h4{font-size:14px;margin:8px 0 12px}h4 span{font-weight:400;color:var(--muted);margin-left:5px}.gene-chips{display:flex;flex-wrap:wrap;gap:7px}.gene-chips button{border:1px solid var(--border);border-radius:6px;background:var(--primary-weak);color:var(--primary-strong);padding:5px 8px;font-size:12px;cursor:pointer}.missing-members{font-size:13px;line-height:1.9;overflow-wrap:anywhere;color:var(--muted)}.reaction-evidence{margin-top:24px;padding-top:22px;border-top:1px solid var(--border)}label{display:flex;align-items:center;gap:15px;font-size:14px}select{padding:9px 12px;max-width:100%;background:var(--card);color:var(--ink);border:1px solid var(--border);border-radius:7px;font:inherit}.reaction-rule{margin:16px 0;padding:15px;border-radius:8px;background:var(--surface-soft)}.reaction-rule span{display:block;font-size:12px;color:var(--muted);margin-bottom:7px}.reaction-rule code{font-size:13px;overflow-wrap:anywhere}.reaction-values{display:flex;gap:28px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.reaction-values strong{margin-left:8px;color:var(--ink);font-weight:500}.unit-note{font-size:12px;line-height:1.9;color:var(--muted)}.table-wrap{max-width:100%;overflow:auto}.table{min-width:510px}.table th,.table td{font-size:13px}.gene-link{border:0;background:transparent;color:var(--primary-strong);font:inherit;cursor:pointer;text-decoration:underline;text-underline-offset:3px}footer{border-top:1px solid var(--border);padding-top:15px;margin-top:20px;font-size:12px;color:var(--muted);line-height:1.9}footer code{display:block;margin-top:12px;overflow-wrap:anywhere}summary{cursor:pointer;color:var(--primary)}@media(max-width:700px){.task-evidence header{flex-direction:column}.trace-summary{grid-template-columns:1fr}.trace-summary>div{border-right:0;border-bottom:1px solid var(--border);padding:13px 16px}.trace-summary strong{font-size:21px}.trace-members{grid-template-columns:1fr;gap:15px}label{align-items:flex-start;flex-direction:column;gap:8px}.reaction-values{gap:14px}h2{font-size:20px}}
</style>
