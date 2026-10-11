<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { assistantApi, purposeLabels, type AssistantContext, type AssistantResult, type Purpose } from '../api/assistant'
import { modelConnection, modelPreferences, modelReady } from '../stores/preferences'
import { downloadBlob } from '../utils/csv'
import UiIcon from './UiIcon.vue'
const props = defineProps<{sourceKind: 'run' | 'analysis'; sourceId: string}>()
const context = ref<AssistantContext | null>(null), result = ref<AssistantResult | null>(null)
const purpose = ref<Purpose>('interpret'), error = ref(''), loading = ref(false), generating = ref(false)
const preview = computed(() => JSON.stringify(context.value, null, 2))
let controller: AbortController | undefined, revision = 0
function reset() {revision++; controller?.abort(); context.value = null; result.value = null; error.value = ''; loading.value = false; generating.value = false}
watch(() => [props.sourceKind, props.sourceId], reset)
onBeforeUnmount(reset)
async function load() {
  controller?.abort(); controller = new AbortController(); const current = ++revision
  loading.value = true; error.value = ''; context.value = null; result.value = null
  try {const value = await assistantApi.context(props.sourceKind, props.sourceId, controller.signal); if (current === revision) context.value = value}
  catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '摘要读取失败'}
  finally {if (current === revision) loading.value = false}
}
async function generate() {
  if (!context.value || !modelReady.value || generating.value) return
  controller = new AbortController(); const current = ++revision
  generating.value = true; error.value = ''; result.value = null
  try {const value = await assistantApi.interpret(context.value, purpose.value, modelConnection(), controller.signal); if (current === revision) result.value = value}
  catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '解读生成失败'}
  finally {if (current === revision) generating.value = false}
}
function download() {if (result.value) downloadBlob(new Blob([JSON.stringify({interpretation: result.value, context: context.value}, null, 2)], {type:'application/json'}), `celllens-interpretation-${props.sourceId}.json`)}
</script>
<template>
  <section class="card assistant-panel" aria-label="大模型辅助解读">
    <header><div><span class="eyebrow">ASSISTED INTERPRETATION</span><h2><UiIcon name="sparkle" />大模型辅助解读</h2><p>基于本次已保存结果，辅助解释变化、数据覆盖和后续验证工作。</p></div><RouterLink to="/settings" class="btn btn-sm">配置大模型</RouterLink></header>
    <p class="assistant-boundary">生成内容属于科研辅助文本，需核对原始证据。系统只发送摘要，不发送逐细胞表达矩阵或完整上传文件。解读仅保留在当前页面，可下载保存。</p>
    <div class="assistant-controls"><label>解读任务<select v-model="purpose" :disabled="generating"><option v-for="(label, key) in purposeLabels" :key="key" :value="key">{{ label }}</option></select></label><button type="button" class="btn" :disabled="loading || generating" @click="load">{{ loading ? '读取摘要…' : context ? '重新读取摘要' : '预览发送内容' }}</button><span v-if="modelReady" class="model-label">{{ modelPreferences.model }}</span><RouterLink v-else to="/settings" class="model-label">请在设置中填写模型和 API Key →</RouterLink></div>
    <template v-if="context"><details class="context-preview" open><summary>发送内容预览 · {{ context.source_id }}</summary><p>{{ context.scope }}</p><p>解读任务：{{ purposeLabels[purpose] }} · 摘要 SHA-256：<code>{{ context.context_sha256 }}</code></p><pre>{{ preview }}</pre></details><p class="send-note">点击下方按钮会将以上摘要发送至 {{ modelPreferences.base_url }}，可能消耗服务额度。</p><button type="button" class="btn btn-primary" :disabled="!modelReady || generating" @click="generate">{{ generating ? '正在生成解读…' : '发送摘要并生成解读' }}</button></template>
    <p v-if="error" class="notice notice-danger" role="alert">{{ error }}</p><p v-if="generating" class="muted" role="status">正在等待大模型服务返回。原始分析结果仍可查看。</p>
    <article v-if="result" class="generated-result"><div class="generated-heading"><h3>辅助解读文本</h3><button type="button" class="btn btn-sm" @click="download">下载解读与来源 JSON</button></div><p class="model-label">{{ result.model }} · {{ new Date(result.generated_at).toLocaleString() }}<span v-if="result.usage.total_tokens"> · {{ result.usage.total_tokens }} token</span> · 来源 {{ result.source_id }}</p><p v-if="result.finish_reason === 'length'" class="notice notice-warn">输出达到预算上限，内容可能不完整。可在设置中增加输出预算后重新生成。</p><p v-else-if="result.finish_reason !== 'stop'" class="notice notice-warn">服务返回的结束原因：{{ result.finish_reason }}。请检查文本是否完整。</p><div class="generated-text">{{ result.text }}</div><p class="model-label">摘要 SHA-256：<code>{{ result.context_sha256 }}</code></p></article>
  </section>
</template>
<style scoped>
.assistant-panel{margin-top:24px;padding:26px}.assistant-panel header{display:flex;justify-content:space-between;align-items:center;gap:20px}.assistant-panel h2{display:flex;gap:10px;align-items:center;font-size:21px;font-weight:500;margin:10px 0}.assistant-panel header p,.assistant-boundary{font-size:12px;color:var(--muted);line-height:1.9}.assistant-boundary{border-left:2px solid var(--border-strong);padding-left:14px;margin:22px 0}.assistant-controls{display:flex;align-items:end;gap:16px;flex-wrap:wrap}.assistant-controls label{display:flex;flex-direction:column;gap:7px;font-size:11px}.assistant-controls select{background:var(--card);color:var(--ink);border:1px solid var(--border-strong);padding:9px;font:inherit}.model-label{font-size:10px;color:var(--muted);overflow-wrap:anywhere}.assistant-controls .model-label{padding-bottom:9px}.context-preview{border:1px solid var(--border);padding:15px;margin:20px 0}.context-preview summary{cursor:pointer;font-size:12px;color:var(--primary);overflow-wrap:anywhere}.context-preview p{font-size:11px;color:var(--muted)}.context-preview code{overflow-wrap:anywhere}.context-preview pre{max-height:300px;overflow:auto;background:var(--bg);padding:14px;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}.send-note{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.assistant-panel .notice{margin-top:18px}.generated-result{margin-top:24px;padding:22px;background:var(--surface-soft);border-top:2px solid var(--primary)}.generated-heading{display:flex;justify-content:space-between;gap:14px;align-items:center}.generated-heading h3{font-size:15px;font-weight:500}.generated-text{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:2;margin:24px 0}.generated-text+p{margin-bottom:0}@media(max-width:600px){.assistant-panel{padding:18px}.assistant-panel header,.generated-heading{align-items:start;flex-direction:column}.generated-result{padding:18px 14px}.assistant-panel h2{font-size:19px}}
</style>
