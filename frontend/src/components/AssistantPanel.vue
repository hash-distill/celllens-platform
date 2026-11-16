<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { assistantApi, purposeLabels, type AssistantContext, type AssistantHistoryTurn, type AssistantResult, type AssistantSelection, type AssistantSourceKind, type Purpose } from '../api/assistant'
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
interface ConversationTurn { id: number; question: string; purpose: Purpose; context: AssistantContext; sentHistory: AssistantHistoryTurn[]; historyContextSha256?: string; result: AssistantResult | null; state: 'waiting'|'complete'|'error'|'cancelled'; error: string }
const turns = ref<ConversationTurn[]>([]), conversationBody = ref<HTMLElement | null>(null), copied = ref<number | null>(null)
const sessions = new Map<string, ConversationTurn[]>()
let sessionKey = '', turnSequence = 0
const history = computed(() => turns.value.filter(turn => turn.state === 'complete' && turn.result && turn.context.context_sha256 === context.value?.context_sha256).slice(-6).map(turn => ({question:turn.question, purpose:turn.purpose, answer:turn.result!.text})))
const historyBytes = computed(() => new TextEncoder().encode(JSON.stringify(history.value)).length)
const historyOverBudget = computed(() => {
  if (historyBytes.value > 64000 || history.value.some(turn => turn.answer.length > 16000)) return true
  if (!context.value) return false
  const payload = {...modelConnection(),source_kind:props.sourceKind,source_id:props.sourceId,context_sha256:context.value.context_sha256,...context.value.selection,purpose:purpose.value,question:question.value.trim(),...(history.value.length ? {history:history.value,history_context_sha256:context.value.context_sha256} : {})}
  return new TextEncoder().encode(JSON.stringify(payload)).length > 65536
})
const budgetExceeded = computed(() => inputEstimate.value !== null && modelPreferences.context_window !== null && modelPreferences.context_window !== undefined && inputEstimate.value + (modelPreferences.max_tokens ?? 0) > modelPreferences.context_window)
const lastFailed = computed(() => [...turns.value].reverse().find(turn => turn.state === 'error' || turn.state === 'cancelled'))
const standaloneError = computed(() => Boolean(error.value && (!lastFailed.value || lastFailed.value.state !== 'error' || error.value !== lastFailed.value.error)))
async function scrollConversation() {await nextTick(); conversationBody.value?.scrollTo?.({top:conversationBody.value.scrollHeight, behavior:'smooth'})}
function newConversation() {cancel(); turns.value = []; result.value = null; question.value = ''; error.value = ''; copied.value = null}
function markdownBlocks(text: string) {
  const blocks: {kind:string; text:string; rows?:string[][]}[] = []
  let code = false, codeLines: string[] = []
  const lines = text.split('\n')
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const line = lines[lineIndex] ?? ''
    if (!code && line.includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[lineIndex + 1] ?? '')) {
      const cells = (row:string) => row.trim().replace(/^\||\|$/g,'').split('|').map(cell => cell.trim())
      const rows = [cells(line)]
      lineIndex += 2
      while (lineIndex < lines.length && lines[lineIndex]?.includes('|')) {rows.push(cells(lines[lineIndex]!));lineIndex++}
      lineIndex--;blocks.push({kind:'table',text:'',rows});continue
    }
    if (/^\s*```/.test(line)) {if (code) {blocks.push({kind:'code',text:codeLines.join('\n')}); codeLines=[]} code=!code; continue}
    if (code) {codeLines.push(line);continue}
    if (!line.trim()) {blocks.push({kind:'space',text:''});continue}
    if (/^#{1,6}\s/.test(line)) blocks.push({kind:'heading',text:line.replace(/^#{1,6}\s+/, '')})
    else if (/^\s*[-*+]\s+/.test(line)) blocks.push({kind:'list',text:line.replace(/^\s*[-*+]\s+/, '')})
    else blocks.push({kind:'paragraph',text:line})
  }
  if (codeLines.length) blocks.push({kind:'code',text:codeLines.join('\n')})
  return blocks
}
function inlineParts(text: string) {return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map(part => ({kind:part.startsWith('**') && part.endsWith('**') ? 'strong' : part.startsWith('`') && part.endsWith('`') ? 'code' : 'text',text:part.startsWith('**') && part.endsWith('**') ? part.slice(2,-2) : part.startsWith('`') && part.endsWith('`') ? part.slice(1,-1) : part}))}
async function copyTurn(turn: ConversationTurn) {
  if (!turn.result) return
  try {await navigator.clipboard.writeText(turn.result.text); copied.value = turn.id}
  catch {error.value = '复制失败，请使用下载保存正文。'}
}
function downloadTurn(turn: ConversationTurn) {
  if (turn.result) downloadBlob(new Blob([JSON.stringify({interpretation:turn.result,context:turn.context,conversation_history:turn.sentHistory,history_context_sha256:turn.historyContextSha256 ?? null},null,2)],{type:'application/json'}),`celllens-interpretation-${props.sourceId}-${turn.id}.json`)
}
async function retryTurn(turn: ConversationTurn) {
  if (busy.value || turn.context.context_sha256 !== context.value?.context_sha256) return
  const position = turns.value.findIndex(item => item.id === turn.id)
  if (position !== turns.value.length - 1) return
  turns.value = turns.value.slice(0, position)
  question.value = turn.question; purpose.value = turn.purpose
  await generate()
}
function onComposerKey(event: KeyboardEvent) {if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) {event.preventDefault();void generate()}}
const inputEstimate = computed(() => {
  const budget = context.value?.request_budget, userBytes = budget?.user_bytes[purpose.value]
  if (!budget || userBytes === undefined) return null
  const questionBytes = new TextEncoder().encode(JSON.stringify(question.value.trim())).length
  return Math.ceil(budget.system_bytes / 3) + Math.ceil((userBytes - 2 + questionBytes) / 3) + 16 + Math.ceil(historyBytes.value / 3) + history.value.length * 8
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
function cancel() {revision++; controller?.abort(); for (const turn of turns.value) if (turn.state === 'waiting') turn.state = 'cancelled'; loading.value = false; generating.value = false}
function reset() {
  cancel(); if (sessionKey) sessions.set(sessionKey, turns.value)
  sessionKey = `${props.sourceKind}:${props.sourceId}:${JSON.stringify(props.selection)}`
  turns.value = sessions.get(sessionKey) ?? []
  context.value = null; result.value = null; error.value = ''; question.value = ''; copied.value = null
  purpose.value = measured.value && ['chart','comparison'].includes(props.selection.view) ? 'interpret' : props.selection.view === 'chart' ? 'figure' : props.selection.view === 'overview' ? 'interpret' : props.selection.view
}
watch(() => [props.sourceKind, props.sourceId, JSON.stringify(props.selection)], reset, {immediate:true, flush:'sync'})
watch([purpose, question], () => {if (!generating.value) error.value = ''}, {flush:'sync'})
watch([() => JSON.stringify(modelPreferences), apiKey], () => {cancel(); result.value = null; error.value = ''}, {flush:'sync'})
onBeforeUnmount(cancel)
async function load() {
  cancel(); controller = new AbortController(); const current = revision
  loading.value = true; error.value = ''; context.value = null; result.value = null
  try {
    const value = await assistantApi.context(props.sourceKind, props.sourceId, controller.signal, props.selection)
    if (current === revision) {
      if (turns.value.some(turn => turn.context.context_sha256 !== value.context_sha256)) turns.value = []
      context.value = value
    }
  } catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '摘要读取失败'}
  finally {if (current === revision) loading.value = false}
}
async function generate() {
  if (!context.value || !modelReady.value || busy.value || historyOverBudget.value || budgetExceeded.value) return
  cancel(); controller = new AbortController(); const current = revision
  const snapshot = context.value
  const sentHistory = history.value.map(previous => ({...previous})), sentQuestion = question.value.trim(), sentPurpose = purpose.value
  const turn: ConversationTurn = {id:++turnSequence,question:sentQuestion,purpose:sentPurpose,context:snapshot,sentHistory,historyContextSha256:sentHistory.length ? snapshot.context_sha256 : undefined,result:null,state:'waiting',error:''}
  turns.value.push(turn)
  void scrollConversation()
  generating.value = true; error.value = ''; result.value = null
  try {
    const value = await assistantApi.interpret(snapshot, sentPurpose, modelConnection(), controller.signal, sentQuestion, sentHistory, sentHistory.length ? snapshot.context_sha256 : undefined)
    if (current === revision) {result.value = value; const saved = turns.value.find(item => item.id === turn.id); if (saved) {saved.result = value;saved.state = 'complete'} question.value = ''; void scrollConversation()}
  } catch (reason) {
    if (current === revision) error.value = reason instanceof ApiError && reason.code === 'EMPTY_COMPLETION'
      ? `模型服务返回了空正文。若启用了思考，${modelPreferences.max_tokens === null ? '服务默认的' : `当前 ${modelPreferences.max_tokens.toLocaleString()} token `}输出预算可能在生成正式解读前用完；请在模型设置中核对推理与输出选项，再重新发送。`
      : reason instanceof Error ? reason.message : '解读生成失败'
  }
  finally {if (current === revision) {generating.value = false; const saved = turns.value.find(item => item.id === turn.id); if (saved && error.value) {saved.state = 'error';saved.error = error.value} void scrollConversation()}}
}
</script>
<template>
  <section class="assistant-panel" aria-label="大模型辅助解读">
    <div class="conversation-toolbar"><span :class="['connection-label',{ready:modelReady}]"><span class="status-dot"/>{{ modelReady ? modelPreferences.model : '尚未连接模型' }}</span><RouterLink to="/settings#model-connection">模型设置 ↗</RouterLink><button :disabled="busy || !turns.length" @click="newConversation">新对话 ＋</button></div>
    <div ref="conversationBody" class="conversation-body">
      <div v-if="!turns.length" class="conversation-intro"><span class="intro-mark">✧</span><h3>从这份结果，深入一步</h3><p>{{ measured ? '围绕真实对照与扰动观测，解读表达和代谢评分。' : '结合当前实验与图表，分析变化、比较和证据边界。' }}</p><div class="prompt-cards"><button v-for="(prompt,index) in prompts" :key="prompt" type="button" :disabled="busy" @click="question=prompt"><span>{{ ['01','02','03'][index] }}</span>{{ prompt }}<span>↗</span></button></div></div>
      <div class="evidence-card" :class="{reviewed:context}"><div class="evidence-heading"><span class="evidence-icon">▤</span><div><strong>{{ context ? '研究摘要已就绪' : '先核对本次研究摘要' }}</strong><small>{{ context ? '来源已关联 · 可展开核对发送内容' : '先预览，再将摘要发送至所选模型' }}</small></div><button :disabled="busy" @click="load">{{ loading ? '读取中…' : context ? '刷新' : '预览摘要' }}</button></div>
      <details v-if="context" class="context-preview"><summary>查看发送内容与来源 <span>{{ inputEstimate === null ? '' : '约 ' + inputEstimate.toLocaleString() + ' token' }}</span></summary><div class="context-detail"><h3>{{ context.data.cell_line }} · {{ context.data.perturbation }}</h3>
      <template v-if="figure"><p class="preview-feature">{{ figure.embedding_space === 'metabolic' ? '代谢' : '表达' }} {{ figure.method === 'joint-umap' ? 'UMAP' : 'PCA' }} · {{ figure.feature.kind === 'task' ? taskName(figure.feature.id) : figure.feature.id }}</p><p>{{ figure.feature.units }} · 展示 {{ figure.displayed_cells }} / {{ figure.total_cells }} 个细胞</p><dl class="figure-stats"><template v-for="source in groups" :key="source"><template v-if="figure.distributions[source]"><dt>{{ groupLabels[source] }} · n={{ figure.distributions[source]?.n_valid }}</dt><dd>均值 {{ fmtNumber(figure.distributions[source]?.mean) }} · 中位数 {{ fmtNumber(figure.distributions[source]?.median) }}</dd></template></template></dl><p>仅发送方法和统计摘要，AI 无法直接观察点云或曲线形状。</p></template>
      <template v-else><p>{{ measured ? '实测分析：前 20 行基因与代谢任务摘要、来源与覆盖信息，不含模型预测或图表分布。' : selection.view === 'comparison' ? '匹配比较：共同批次评价子集的基因与任务各前 20 行，按预测差值绝对值排序。以下数值不使用原实验全量摘要。' : '前 20 行基因与代谢任务摘要，以及可用的实测比较、来源与覆盖信息。' }}</p><p v-if="measured">表达单位：{{ context.data.expression_units }}</p><details><summary>主要变化摘要</summary><pre>{{ previewRows(context.data.top_genes) }}{{ '\n\n' }}{{ previewRows(context.data.metabolic_tasks) }}</pre></details><template v-if="selectedFeature"><p class="preview-feature">选定指标：{{ selectedFeature.id }} · {{ selectedFeature.units }}</p><pre>{{ previewRows([selectedFeature.row]) }}</pre></template></template>
      <details><summary>完整发送摘要 · 来源与局限</summary><pre class="raw-context">{{ rawContext }}</pre></details>
      <p class="send-note">发送至 {{ modelPreferences.base_url }}，可能消耗服务额度。原始表达矩阵和科研图像不会发送。</p>
      <p v-if="inputEstimate !== null" class="budget-note">输入约 {{ inputEstimate.toLocaleString() }} token · 输出长度：{{ outputLengthLabel }} · 上下文容量：{{ contextLengthLabel }}。按 UTF-8 字节估算，实际用量以服务返回为准。</p>
      <p v-if="modelPreferences.provider === 'deepseek' && modelPreferences.reasoning_effort !== 'none' && modelPreferences.max_tokens !== null && modelPreferences.max_tokens < 8192" class="notice notice-warn">DeepSeek 的思考过程也占用输出预算，手动设置的预算可能在正式解读前用完。可在<RouterLink to="/settings#model-connection">模型设置</RouterLink>中恢复模型默认输出长度。</p>
      <p v-if="inputEstimate !== null && modelPreferences.context_window !== null && inputEstimate + (modelPreferences.max_tokens ?? 0) > modelPreferences.context_window" class="notice notice-warn">当前估算超过手动设置的上下文限制，请在模型设置中核对容量或恢复模型默认。系统会在发送前拦截，不截断科研证据。</p>
</div></details></div>
      <p v-if="turns.length" class="history-note">当前会话 · 连续提问会携带最近 6 轮同一摘要的完整问答</p>
      <div class="conversation-log" aria-label="解读对话记录" aria-live="polite" aria-relevant="additions text">
        <article v-for="turn in turns" :key="turn.id" class="conversation-turn"><div class="user-message"><span>你 · {{ purposeLabels[turn.purpose] }}</span><p>{{ turn.question || purposeLabels[turn.purpose] }}</p></div><div class="assistant-message"><div class="answer-heading"><span class="answer-avatar">✧</span><strong>科研解读</strong><small>{{ turn.result?.model ?? (turn.state === 'waiting' ? '正在整理解释' : '') }}</small></div><template v-if="turn.result"><p v-if="turn.result.finish_reason === 'length'" class="notice notice-warn">输出达到长度上限，内容可能不完整。可调整输出长度后重试。</p><p v-else-if="turn.result.finish_reason !== 'stop'" class="notice notice-warn">本次生成提前结束，可重试获取完整解读。</p><div class="generated-text"><template v-for="(block,index) in markdownBlocks(turn.result.text)" :key="index"><div v-if="block.kind === 'table'" class="answer-table"><table><tbody><tr v-for="(row,rowIndex) in block.rows" :key="rowIndex"><component :is="rowIndex === 0 ? 'th' : 'td'" v-for="(cell,cellIndex) in row" :key="cellIndex">{{ cell }}</component></tr></tbody></table></div><pre v-else-if="block.kind === 'code'">{{ block.text }}</pre><div v-else-if="block.kind === 'space'" class="answer-space"/><component :is="block.kind === 'heading' ? 'h4' : 'p'" v-else :class="{'answer-list':block.kind === 'list'}"><template v-for="(part,partIndex) in inlineParts(block.text)" :key="partIndex"><strong v-if="part.kind === 'strong'">{{ part.text }}</strong><code v-else-if="part.kind === 'code'">{{ part.text }}</code><template v-else>{{ part.text }}</template></template></component></template></div><div class="answer-actions"><button @click="copyTurn(turn)">{{ copied === turn.id ? '已复制' : '复制正文' }}</button><button @click="downloadTurn(turn)">下载解读与来源</button><button v-if="turn.id === turns[turns.length - 1]?.id" :disabled="busy || turn.context.context_sha256 !== context?.context_sha256" @click="retryTurn(turn)">重新生成</button><time>{{ new Date(turn.result.generated_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) }}</time></div></template><p v-else-if="turn.state === 'waiting'" class="thinking" role="status"><span/><span/><span/> 正在等待模型回复…</p><div v-else class="turn-error"><p>{{ turn.state === 'cancelled' ? '已停止等待。已发送的请求可能仍计入服务额度。' : turn.error }}</p><button v-if="turn.id === turns[turns.length - 1]?.id" :disabled="busy || turn.context.context_sha256 !== context?.context_sha256" @click="retryTurn(turn)">重新发送</button></div></div></article>
      </div>
      <div v-if="standaloneError" class="notice notice-danger" role="alert">{{ error }}<button v-if="!context" :disabled="busy" @click="load">重试摘要</button></div>
      <p v-if="loading" class="wait-message" role="status">正在核验来源并读取统计摘要…</p>
    </div>
    <form class="composer" @submit.prevent="generate"><div class="composer-options"><label>任务 <select v-model="purpose" :disabled="busy" aria-label="解读任务"><option v-for="(label,key) in availablePurposes" :key="key" :value="key" :disabled="key === 'figure' && selection.view !== 'chart'">{{ label }}</option></select></label><span>{{ history.length ? '携带 ' + history.length + ' 轮问答' : '当前结果摘要' }}</span></div><div class="composer-input"><label class="sr-only" for="assistant-question">向科研助手提问</label><textarea id="assistant-question" v-model="question" rows="2" maxlength="1200" :disabled="busy" placeholder="围绕这份结果提问，或选择上方建议…" @keydown="onComposerKey"/><div class="composer-bottom"><span>{{ question.length }} / 1200 <span class="keyboard-hint">· Ctrl / ⌘ + Enter</span></span><button v-if="busy" type="button" class="stop-button" @click="cancel">■ 停止等待</button><button v-else type="submit" class="send-button" :disabled="!context || !modelReady || historyOverBudget || budgetExceeded" aria-label="发送摘要并生成解读" title="发送摘要并生成解读">发送 <span>↑</span></button></div></div><p v-if="historyOverBudget" class="composer-warning">历史问答超过发送上限，请开始新对话；已有记录可先复制或下载。</p><p v-else-if="budgetExceeded" class="composer-warning">摘要与问答超过设置的上下文容量，请调整模型设置或新建对话。</p><p v-else-if="!modelReady" class="composer-note"><RouterLink to="/settings#model-connection">配置模型与 API Key →</RouterLink><span>凭据不会写入解读导出</span></p><p v-else class="composer-note"><span>{{ context ? '发送摘要和同源问答 · 不发送原始矩阵或图像' : '预览摘要后即可发送' }}</span><span>{{ inputEstimate === null ? '' : '输入约 ' + inputEstimate.toLocaleString() + ' token' }}</span></p></form>
  </section>
</template>
<style scoped>
.assistant-panel{display:flex;flex-direction:column;min-height:0}.conversation-toolbar{display:flex;align-items:center;gap:14px;padding:14px 23px;border-bottom:1px solid var(--border);font-size:12px;flex:none}.connection-label{display:flex;align-items:center;gap:6px;color:var(--muted);min-width:0;flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.connection-label.ready{color:var(--primary)}.status-dot{width:5px;height:5px;border-radius:50%;background:currentColor;flex:none}.conversation-toolbar a{white-space:nowrap;text-decoration:none;font-size:12px}.conversation-toolbar button{border:0;background:transparent;color:var(--muted);font:12px var(--font);padding:0;white-space:nowrap;cursor:pointer}.conversation-body{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:23px}.conversation-intro{padding:0 1px 20px}.intro-mark{display:grid;place-items:center;width:39px;height:39px;border:1px solid var(--surface-tint-border);border-radius:14px;background:var(--surface-tint);font-size:25px;color:var(--primary);margin-bottom:14px}.conversation-intro h3{font-size:21px;font-weight:500;margin:0 0 11px;letter-spacing:-.02em}.conversation-intro>p{font-size:14px;line-height:1.9;color:var(--muted);margin:0 0 18px}.prompt-cards{display:grid;gap:7px}.prompt-cards button{display:flex;align-items:center;gap:13px;text-align:left;padding:13px 14px;border:1px solid var(--border);border-radius:11px;background:var(--card);color:var(--ink);font:13px var(--font);cursor:pointer;transition:border-color .15s,background .15s}.prompt-cards button:hover{border-color:var(--surface-tint-border-strong);background:var(--surface-tint)}.prompt-cards button>span:first-child{font:12px Bahnschrift,sans-serif;color:var(--primary);opacity:.7}.prompt-cards button>span:last-child{margin-left:auto;color:var(--primary)}.evidence-card{border:1px solid var(--border);border-radius:12px;background:var(--surface-soft);overflow:hidden}.evidence-card.reviewed{border-color:var(--surface-tint-border)}.evidence-heading{display:flex;align-items:center;gap:12px;padding:14px}.evidence-icon{font-size:23px;color:var(--primary)}.evidence-heading>div{flex:1;min-width:0}.evidence-heading strong{font-size:13px;font-weight:500;display:block}.evidence-heading small{font-size:11px;color:var(--muted);display:block;line-height:1.7;margin-top:3px}.evidence-heading button{flex:none;border:1px solid var(--surface-tint-border);border-radius:7px;background:var(--card);color:var(--primary);padding:7px 12px;font:12px var(--font);cursor:pointer}.context-preview{border-top:1px solid var(--border);background:var(--card)}.context-preview>summary{padding:12px 14px;font-size:12px;color:var(--primary);cursor:pointer}.context-preview>summary>span{float:right;color:var(--muted);font-size:11px}.context-detail{padding:0 13px 14px}.context-detail h3{font-size:14px;font-weight:500;margin:11px 0}.context-detail p{font-size:12px;line-height:1.9;color:var(--muted);overflow-wrap:anywhere}.context-detail details{margin-top:14px}.context-detail summary{font-size:12px;color:var(--primary);cursor:pointer}.context-detail pre{max-height:230px;overflow:auto;padding:12px;background:var(--surface-soft);white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;line-height:1.8}.figure-stats{font-size:12px;line-height:1.8}.figure-stats dt{margin-top:11px;color:var(--muted)}.figure-stats dd{margin:0;font-variant-numeric:tabular-nums}.send-note{border-top:1px solid var(--border);padding-top:12px}.history-note{font-size:11px;color:var(--muted);text-align:center;margin:22px 0 16px;line-height:1.8}.conversation-turn{margin:0 0 26px}.user-message{margin-left:34px;padding:13px 15px;border:1px solid var(--surface-tint-border);border-radius:14px 14px 3px 14px;background:var(--surface-tint)}.user-message>span{font-size:11px;color:var(--primary)}.user-message p{font-size:14px;line-height:1.8;margin:6px 0 0;white-space:pre-wrap;overflow-wrap:anywhere}.assistant-message{padding:18px 0 0}.answer-heading{display:flex;align-items:center;gap:11px}.answer-avatar{display:grid;place-items:center;width:26px;height:26px;background:var(--primary);color:var(--on-primary,#fff);font-size:20px;border-radius:11px}.answer-heading strong{font-size:13px;font-weight:500}.answer-heading small{margin-left:auto;color:var(--muted);font-size:11px;overflow-wrap:anywhere;max-width:50%;text-align:right}.generated-text{font-size:14px;line-height:1.95;overflow-wrap:anywhere;padding:13px 0 6px;color:var(--ink)}.generated-text p{margin:5px 0;white-space:pre-wrap}.generated-text h4{font-size:13px;font-weight:600;line-height:1.8;margin:15px 0 7px;color:var(--primary-strong,var(--primary))}.generated-text strong{font-weight:600}.generated-text pre{background:var(--surface-soft);border:1px solid var(--border);border-radius:11px;padding:14px;white-space:pre-wrap;overflow:auto;font-size:13px}.generated-text code{background:var(--surface-tint);padding:1px 4px;border-radius:4px;font-size:13px}.answer-table{max-width:100%;overflow:auto;margin:12px 0}.answer-table table{border-collapse:collapse;min-width:100%;font-size:12px}.answer-table th,.answer-table td{border:1px solid var(--border);padding:8px 10px;text-align:left;min-width:80px;white-space:pre-wrap}.answer-table th{background:var(--surface-tint);font-weight:500;color:var(--primary)}.answer-space{height:6px}.answer-list{padding-left:15px;position:relative}.answer-list:before{content:'•';position:absolute;left:2px;color:var(--primary)}.answer-actions{display:flex;align-items:center;gap:14px;padding-top:12px;border-top:1px solid var(--border);margin-top:12px}.answer-actions button,.turn-error button{font:11px var(--font);padding:0;border:0;background:transparent;color:var(--muted);cursor:pointer}.answer-actions button:hover,.turn-error button{color:var(--primary)}.answer-actions time{margin-left:auto;font-size:11px;color:var(--faint,var(--muted))}.turn-error{font-size:13px;color:var(--muted);line-height:1.9;padding:12px 0;overflow-wrap:anywhere}.turn-error button{font-size:12px}.thinking,.wait-message{font-size:13px;color:var(--muted);line-height:1.9;margin:14px 0}.thinking>span{display:inline-block;width:4px;height:4px;border-radius:50%;background:var(--primary);animation:assistant-pulse 1.4s infinite;margin-right:3px}.thinking>span:nth-child(2){animation-delay:.2s}.thinking>span:nth-child(3){animation-delay:.4s}.composer{padding:14px 22px;border-top:1px solid var(--border);background:var(--card);flex:none}.composer-options{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);margin-bottom:11px}.composer-options label{display:flex;align-items:center;gap:7px;min-width:0}.composer-options select{border:0;background:var(--surface-tint);border-radius:5px;padding:5px 6px;color:var(--primary);font:12px var(--font);max-width:190px}.composer-input{border:1px solid var(--border-strong);border-radius:14px;overflow:hidden;background:var(--card);transition:box-shadow .15s}.composer-input:focus-within{border-color:var(--primary);box-shadow:0 0 0 3px var(--surface-tint)}.composer-input textarea{display:block;border:0;outline:none;padding:13px 14px 4px;width:100%;resize:vertical;min-height:64px;max-height:150px;background:transparent;color:var(--ink);font:14px var(--font);line-height:1.8;box-sizing:border-box}.composer-input textarea::placeholder{color:var(--faint,var(--muted))}.composer-bottom{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:7px 11px 11px 14px}.composer-bottom>span{font-size:11px;color:var(--muted)}.send-button,.stop-button{padding:7px 13px;border:0;border-radius:11px;background:var(--primary);color:var(--on-primary,#fff);font:13px var(--font);cursor:pointer;display:flex;align-items:center;gap:14px}.send-button>span{font-size:16px;line-height:1}.stop-button{background:var(--surface-tint);color:var(--primary);border:1px solid var(--surface-tint-border)}.composer-note{display:flex;justify-content:space-between;gap:12px;font-size:11px;color:var(--muted);margin:11px 1px 0;line-height:1.7}.composer-note a{text-decoration:none}.composer-warning{font-size:12px;color:var(--danger);line-height:1.8;margin:11px 0 0}.notice{font-size:13px;line-height:1.8}.notice button{border:0;background:transparent;color:var(--primary);cursor:pointer}.assistant-panel button:disabled{opacity:.45;cursor:default}.assistant-panel button:focus-visible,.assistant-panel a:focus-visible,.assistant-panel summary:focus-visible,.assistant-panel select:focus-visible{outline:2px solid var(--primary);outline-offset:3px}@keyframes assistant-pulse{0%,80%,100%{opacity:.3}40%{opacity:1}}@media(prefers-reduced-motion:reduce){.thinking>span{animation:none}.prompt-cards button,.composer-input{transition:none}}@media(max-width:700px){.conversation-toolbar{padding:12px 17px;gap:11px}.conversation-body{padding:18px 17px}.composer{padding:14px 16px}.composer-options select{max-width:165px}.keyboard-hint{display:none}.composer-note{font-size:11px}.conversation-intro h3{font-size:20px}.answer-actions{gap:13px}}
</style>
