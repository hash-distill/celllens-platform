<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { assistantApi, purposeLabels, type AssistantContext, type AssistantResult, type AssistantSelection, type AssistantSourceKind, type Purpose } from '../api/assistant'
import { ApiError } from '../api/http'
import { apiKey, modelConnection, modelPreferences, modelReady } from '../stores/preferences'
import { downloadBlob } from '../utils/csv'
import { fmtDelta, fmtNumber } from '../utils/format'
import { taskName } from '../utils/biologyLocale'
import type { ScientificCellState } from '../types/cellState'

const props = defineProps<{sourceKind: AssistantSourceKind; sourceId: string; selection: AssistantSelection}>()
const context = ref<AssistantContext | null>(null), result = ref<AssistantResult | null>(null)
const purpose = ref<Purpose>('interpret'), question = ref(''), error = ref('')
const loading = ref(false), generating = ref(false)
const busy = computed(() => loading.value || generating.value)
const measured = computed(() => props.sourceKind === 'measured')
const availablePurposes = computed(() => Object.fromEntries(Object.entries(purposeLabels).filter(([key]) => !measured.value || !['figure','comparison'].includes(key))))
const figure = computed(() => measured.value ? undefined : context.value?.data.figure as ScientificCellState | undefined)
const selectedFeature = computed(() => context.value?.data.selected_feature as {id: string; source: string; units?: string; row: Record<string,unknown>} | undefined)
const groups = ['control','predicted','observed'] as const
const groupLabels = {control:'对照',predicted:'模型预测',observed:'实测'}
const prompts = computed(() => !measured.value && props.selection.view === 'chart' ? ['这张图应该怎么看？','当前指标变化体现了什么？','预测与实测有哪些差异？'] : ['哪些变化最值得关注？','这些结果有哪些局限？','下一步可以验证什么？'])
const rawContext = computed(() => context.value ? JSON.stringify(Object.fromEntries(Object.entries(context.value).filter(([key]) => key !== 'request_budget')), null, 2) : '')
const inputEstimate = computed(() => {
  const budget = context.value?.request_budget, userBytes = budget?.user_bytes[purpose.value]
  if (!budget || userBytes === undefined) return null
  const questionBytes = new TextEncoder().encode(JSON.stringify(question.value.trim())).length
  return Math.ceil(budget.system_bytes / 3) + Math.ceil((userBytes - 2 + questionBytes) / 3) + 16
})
const outputLengthLabel = computed(() => modelPreferences.max_tokens === null ? '模型默认' : `${modelPreferences.max_tokens.toLocaleString()} token`)
const contextLengthLabel = computed(() => modelPreferences.context_window === null ? '模型默认' : `${modelPreferences.context_window.toLocaleString()} token`)
function previewRows(value: unknown): string {
  if (!Array.isArray(value) || !value.length) return '本摘要未提供'
  return value.slice(0,20).map((row: Record<string, unknown>) => {
    const name = row.label ?? row.gene ?? row.task ?? row.id ?? '项目'
    if (measured.value) {
      const control = typeof row.control === 'number' ? fmtNumber(row.control,4) : '未提供'
      const observed = typeof row.observed === 'number' ? fmtNumber(row.observed,4) : '未提供'
      const delta = typeof row.observed_delta === 'number' ? fmtDelta(row.observed_delta,4) : '未提供'
      return `${name}：对照 ${control} · 实测 ${observed} · 实测差值 ${delta}`
    }
    if (props.selection.view === 'comparison') {
      const control = typeof row.control === 'number' ? fmtNumber(row.control,4) : '未提供'
      const predicted = typeof row.predicted === 'number' ? fmtNumber(row.predicted,4) : '未提供'
      const observed = typeof row.observed === 'number' ? fmtNumber(row.observed,4) : '未提供'
      const predictedDelta = typeof row.predicted_delta === 'number' ? fmtDelta(row.predicted_delta,4) : '未提供'
      const observedDelta = typeof row.observed_delta === 'number' ? fmtDelta(row.observed_delta,4) : '未提供'
      return `${name}：匹配对照 ${control} · 预测 ${predicted} · 实测 ${observed} · 预测差值 ${predictedDelta} · 实测差值 ${observedDelta}`
    }
    const delta = typeof row.predicted_delta === 'number' ? fmtDelta(row.predicted_delta,4) : '未提供'
    return `${name}：预测差值 ${delta}`
  }).join('\n')
}
let controller: AbortController | undefined, revision = 0
function cancel() {revision++; controller?.abort(); loading.value = false; generating.value = false}
function reset() {
  cancel(); context.value = null; result.value = null; error.value = ''; question.value = ''
  purpose.value = measured.value && ['chart','comparison'].includes(props.selection.view) ? 'interpret' : props.selection.view === 'chart' ? 'figure' : props.selection.view === 'overview' ? 'interpret' : props.selection.view
}
watch(() => [props.sourceKind, props.sourceId, JSON.stringify(props.selection)], reset, {immediate:true, flush:'sync'})
watch([purpose, question], () => {cancel(); result.value = null; error.value = ''}, {flush:'sync'})
watch([() => JSON.stringify(modelPreferences), apiKey], () => {cancel(); result.value = null; error.value = ''}, {flush:'sync'})
onBeforeUnmount(cancel)
async function load() {
  cancel(); controller = new AbortController(); const current = revision
  loading.value = true; error.value = ''; context.value = null; result.value = null
  try {
    const value = await assistantApi.context(props.sourceKind, props.sourceId, controller.signal, props.selection)
    if (current === revision) context.value = value
  } catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '摘要读取失败'}
  finally {if (current === revision) loading.value = false}
}
async function generate() {
  if (!context.value || !modelReady.value || busy.value) return
  cancel(); controller = new AbortController(); const current = revision
  const snapshot = context.value
  generating.value = true; error.value = ''; result.value = null
  try {
    const value = await assistantApi.interpret(snapshot, purpose.value, modelConnection(), controller.signal, question.value.trim())
    if (current === revision) result.value = value
  } catch (reason) {
    if (current === revision) error.value = reason instanceof ApiError && reason.code === 'EMPTY_COMPLETION'
      ? `模型服务返回了空正文。若启用了思考，${modelPreferences.max_tokens === null ? '服务默认的' : `当前 ${modelPreferences.max_tokens.toLocaleString()} token `}输出预算可能在生成正式解读前用完；请在模型设置中核对推理与输出选项，再重新发送。`
      : reason instanceof Error ? reason.message : '解读生成失败'
  }
  finally {if (current === revision) generating.value = false}
}
function download() {
  if (result.value) downloadBlob(new Blob([JSON.stringify({interpretation:result.value,context:context.value},null,2)],{type:'application/json'}),`celllens-interpretation-${props.sourceId}.json`)
}
</script>
<template>
  <section class="assistant-panel" aria-label="大模型辅助解读">
    <div class="connection-line"><span v-if="modelReady">{{ modelPreferences.model }}</span><span v-else>尚未配置模型</span><RouterLink to="/settings#model-connection">模型设置 →</RouterLink></div>
    <p class="assistant-boundary">{{ measured ? '解释真实对照与扰动观测的表达和代谢评分。' : '结合当前结果解释图表和数值。' }}先预览摘要，再发送给所选模型。</p>
    <label class="field">解读任务<select v-model="purpose" :disabled="busy"><option v-for="(label,key) in availablePurposes" :key="key" :value="key" :disabled="key === 'figure' && selection.view !== 'chart'">{{ label }}</option></select></label>
    <div class="prompt-chips" aria-label="快捷提问"><button v-for="prompt in prompts" :key="prompt" type="button" :disabled="busy" @click="question=prompt">{{ prompt }}</button></div>
    <label class="field">补充问题<textarea v-model="question" rows="3" maxlength="1200" :disabled="busy" :placeholder="measured ? '例如：这个基因的实测变化如何体现？还有哪些解释需要验证？' : '例如：这个基因的变化如何体现？为什么预测与实测不一致？'" /></label><p class="question-count">可选 · {{ question.length }} / 1200</p>
    <div class="btn-row"><button type="button" class="btn" :disabled="busy" @click="load">{{ loading ? '读取摘要…' : context ? '重新预览发送内容' : '预览发送内容' }}</button><button v-if="busy" type="button" class="btn btn-sm" @click="cancel">取消等待</button></div>
    <div v-if="context" class="context-preview">
      <h3>本次将发送</h3><p>{{ context.data.cell_line }} · {{ context.data.perturbation }}</p>
      <template v-if="figure"><p class="preview-feature">{{ figure.embedding_space === 'metabolic' ? '代谢' : '表达' }} {{ figure.method === 'joint-umap' ? 'UMAP' : 'PCA' }} · {{ figure.feature.kind === 'task' ? taskName(figure.feature.id) : figure.feature.id }}</p><p>{{ figure.feature.units }} · 展示 {{ figure.displayed_cells }} / {{ figure.total_cells }} 个细胞</p><dl class="figure-stats"><template v-for="source in groups" :key="source"><template v-if="figure.distributions[source]"><dt>{{ groupLabels[source] }} · n={{ figure.distributions[source]?.n_valid }}</dt><dd>均值 {{ fmtNumber(figure.distributions[source]?.mean) }} · 中位数 {{ fmtNumber(figure.distributions[source]?.median) }}</dd></template></template></dl><p>仅发送方法和统计摘要，AI 无法直接观察点云或曲线形状。</p></template>
      <template v-else><p>{{ measured ? '实测分析：前 20 行基因与代谢任务摘要、来源与覆盖信息，不含模型预测或图表分布。' : selection.view === 'comparison' ? '匹配比较：共同批次评价子集的基因与任务各前 20 行，按预测差值绝对值排序。以下数值不使用原实验全量摘要。' : '前 20 行基因与代谢任务摘要，以及可用的实测比较、来源与覆盖信息。' }}</p><p v-if="measured">表达单位：{{ context.data.expression_units }}</p><details><summary>主要变化摘要</summary><pre>{{ previewRows(context.data.top_genes) }}{{ '\n\n' }}{{ previewRows(context.data.metabolic_tasks) }}</pre></details><template v-if="selectedFeature"><p class="preview-feature">选定指标：{{ selectedFeature.id }} · {{ selectedFeature.units }}</p><pre>{{ previewRows([selectedFeature.row]) }}</pre></template></template>
      <details><summary>完整发送摘要 · 来源与局限</summary><pre class="raw-context">{{ rawContext }}</pre></details>
      <p class="send-note">发送至 {{ modelPreferences.base_url }}，可能消耗服务额度。原始表达矩阵和科研图像不会发送。</p>
      <p v-if="inputEstimate !== null" class="budget-note">输入约 {{ inputEstimate.toLocaleString() }} token · 输出长度：{{ outputLengthLabel }} · 上下文容量：{{ contextLengthLabel }}。按 UTF-8 字节估算，实际用量以服务返回为准。</p>
      <p v-if="modelPreferences.provider === 'deepseek' && modelPreferences.reasoning_effort !== 'none' && modelPreferences.max_tokens !== null && modelPreferences.max_tokens < 8192" class="notice notice-warn">DeepSeek 的思考过程也占用输出预算，手动设置的预算可能在正式解读前用完。可在<RouterLink to="/settings#model-connection">模型设置</RouterLink>中恢复模型默认输出长度。</p>
      <p v-if="inputEstimate !== null && modelPreferences.context_window !== null && inputEstimate + (modelPreferences.max_tokens ?? 0) > modelPreferences.context_window" class="notice notice-warn">当前估算超过手动设置的上下文限制，请在模型设置中核对容量或恢复模型默认。系统会在发送前拦截，不截断科研证据。</p>
      <button type="button" class="btn btn-primary generate-button" :disabled="!modelReady || busy" @click="generate">{{ generating ? '正在生成解读…' : '发送摘要并生成解读' }}</button>
      <RouterLink v-if="!modelReady" to="/settings#model-connection" class="configure-hint">填写模型与 API Key 后即可生成 →</RouterLink>
    </div>
    <div v-if="error" class="notice notice-danger" role="alert"><p>{{ error }}</p><RouterLink v-if="context" to="/settings#model-connection">调整模型设置 →</RouterLink></div><p v-if="busy" class="wait-message" role="status">{{ generating ? '正在等待模型回复。可以取消等待；已发送请求可能仍计入服务额度。' : '正在核验来源并读取当前统计摘要…' }}</p>
    <article v-if="result" class="generated-result"><h3>{{ purposeLabels[purpose] }}</h3><p class="model-label">{{ result.model }} · {{ new Date(result.generated_at).toLocaleString() }}</p><p v-if="result.question" class="result-question">{{ result.question }}</p><p v-if="result.finish_reason === 'length'" class="notice notice-warn">输出达到长度上限，内容可能不完整。可在模型设置中增加输出长度后重试。</p><p v-else-if="result.finish_reason !== 'stop'" class="notice notice-warn">本次生成提前结束，可重试获取完整解读。</p><div class="generated-text">{{ result.text }}</div><button type="button" class="btn btn-sm" @click="download">下载解读与来源 JSON</button></article>
  </section>
</template>
<style scoped>
.connection-line{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);overflow-wrap:anywhere}.connection-line a{flex:none}.assistant-boundary{font-size:12px;line-height:1.8;color:var(--muted);margin:18px 0}.field{display:flex;flex-direction:column;gap:8px;font-size:12px;margin-top:18px}.field select,.field textarea{padding:10px 12px;background:var(--card);border:1px solid var(--border-strong);border-radius:3px;color:var(--ink);font:inherit;min-width:0;width:100%}.field textarea{resize:vertical;line-height:1.7;min-height:80px;max-height:220px}.question-count{font-size:10px;color:var(--muted);text-align:right;margin:6px 0 18px}.prompt-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.prompt-chips button{padding:6px 9px;border:1px solid var(--border);border-radius:3px;background:var(--surface-soft);color:var(--primary);font:11px var(--font);cursor:pointer}.prompt-chips button:hover{border-color:var(--primary)}.context-preview{border:1px solid var(--border);border-left:2px solid var(--primary);padding:16px;margin:20px 0}.context-preview h3,.generated-result h3{font-size:14px;font-weight:500;margin:0 0 12px}.context-preview p{font-size:11px;line-height:1.8;color:var(--muted);overflow-wrap:anywhere}.context-preview .preview-feature{color:var(--primary);font-size:12px}.context-preview details{margin-top:14px}.context-preview summary{cursor:pointer;font-size:11px;color:var(--primary);line-height:1.7}.context-preview pre{max-height:250px;overflow:auto;background:var(--bg);padding:10px;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}.figure-stats{font-size:11px;line-height:1.8;margin:14px 0}.figure-stats dt{color:var(--muted);margin-top:9px}.figure-stats dd{margin:0;font-variant-numeric:tabular-nums}.send-note{border-top:1px solid var(--border);padding-top:14px}.generate-button{width:100%;white-space:normal}.configure-hint{display:block;font-size:11px;margin-top:14px}.generated-result{margin-top:22px;border-top:2px solid var(--primary);padding-top:20px}.model-label,.result-question,.wait-message{font-size:11px;color:var(--muted);line-height:1.8;overflow-wrap:anywhere}.generated-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.95;margin:18px 0 24px}.assistant-panel>.notice{margin-top:18px}.assistant-panel button:focus-visible,.assistant-panel summary:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
</style>
