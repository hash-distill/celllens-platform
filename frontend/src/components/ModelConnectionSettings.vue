<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { assistantApi } from '../api/assistant'
import { activeConnectionId, addConnection, apiKey, clearKey, connectionProfiles, modelPreferences, removeConnection, saveModel, selectConnection } from '../stores/preferences'
import type { DiscoveredModel, ProviderPreset, ReasoningEffort } from '../types/assistant'
import { cleanPreferences, DEFAULT_MODEL, EFFORT_OPTIONS, exportConnectionConfig, normalizeBaseUrl, parseConnectionConfig, type ImportedConnection } from '../utils/modelConfig'
import { downloadBlob } from '../utils/csv'

const form = reactive({...modelPreferences,api_key:apiKey.value,name:connectionProfiles.value.find(item => item.id === activeConnectionId.value)?.name ?? '默认连接'})
const providers = ref<ProviderPreset[]>([]), allowed = ref<string[]>([]), loading = ref(true)
const error = ref(''), message = ref(''), busy = ref<'models'|'test'|''>(''), showKey = ref(false)
const models = ref<DiscoveredModel[]>([]), search = ref(''), truncated = ref(false)
const defaultLengthsSupported = ref(true)
const importOpen = ref(false), importText = ref(''), importError = ref(''), importWarnings = ref<string[]>([])
const imported = ref<ImportedConnection[]>([]), fileInput = ref<HTMLInputElement>()
const activeProvider = computed(() => providers.value.find(item => item.id === form.provider))
const effortOptions = computed(() => activeProvider.value?.reasoning_efforts ?? EFFORT_OPTIONS[form.provider])
const effortNames: Record<ReasoningEffort,string> = {auto:'服务默认',none:'关闭思考（须模型支持）',minimal:'极低 · minimal',low:'低 · low',medium:'中 · medium',high:'高 · high',xhigh:'很高 · xhigh',max:'最高 · max'}
const filteredModels = computed(() => models.value.filter(item => `${item.id} ${item.name}`.toLowerCase().includes(search.value.toLowerCase())))
const selectedModel = computed(() => models.value.find(item => item.id === form.model))
const endpoint = computed(() => {try {return normalizeBaseUrl(form.base_url) + (form.provider === 'anthropic' ? '/messages' : '/chat/completions')} catch {return ''}})
const permitted = computed(() => {try {return allowed.value.includes(new URL(form.base_url).origin)} catch {return false}})
const credentialsReady = computed(() => permitted.value && (form.provider === 'custom' || Boolean(form.api_key.trim())))
const dirty = computed(() => Object.keys(DEFAULT_MODEL).some(key => form[key as keyof typeof DEFAULT_MODEL] !== modelPreferences[key as keyof typeof DEFAULT_MODEL]) || form.name !== connectionProfiles.value.find(item => item.id === activeConnectionId.value)?.name || form.api_key !== apiKey.value)
let controller: AbortController | undefined, revision = 0
function cancel() {revision++; controller?.abort(); busy.value = ''}
function refreshForm() {
  cancel(); Object.assign(form,modelPreferences,{api_key:apiKey.value,name:connectionProfiles.value.find(item => item.id === activeConnectionId.value)?.name ?? '我的 API'})
  models.value = []; search.value = ''; error.value = ''; message.value = ''; showKey.value = false
}
watch(() => [form.provider,form.base_url,form.api_key], () => {cancel(); models.value = []; search.value = ''; message.value = ''; error.value = ''}, {flush:'sync'})
watch(() => [form.model,form.max_tokens,form.context_window,form.reasoning_effort,form.thinking_mode,form.thinking_budget,form.token_parameter], () => {if (busy.value === 'test') cancel(); message.value = ''}, {flush:'sync'})
watch(() => form.thinking_mode, mode => {if (['auto','disabled'].includes(mode)) form.reasoning_effort = 'auto'}, {flush:'sync'})
watch(importText, () => {imported.value = []; importError.value = ''; importWarnings.value = []}, {flush:'sync'})
onMounted(async () => {
  try {const result = await assistantApi.capabilities(); providers.value = result.providers; allowed.value = result.allowed_origins; defaultLengthsSupported.value = result.model_default_lengths === true}
  catch (reason) {error.value = reason instanceof Error ? reason.message : '配置读取失败'}
  finally {loading.value = false}
})
onBeforeUnmount(cancel)
function switchConnection(event: Event) {selectConnection((event.target as HTMLSelectElement).value); refreshForm()}
function createConnection() {try {addConnection('新的连接'); refreshForm()} catch (reason) {error.value = (reason as Error).message}}
function deleteConnection() {try {removeConnection(activeConnectionId.value); refreshForm(); message.value = '已移除连接及其会话密钥。'} catch (reason) {error.value = (reason as Error).message}}
function changeProvider() {
  const provider = activeProvider.value
  if (!provider) return
  cancel(); form.base_url = provider.base_url; form.token_parameter = provider.token_parameter
  form.model = ''; form.api_key = ''; form.reasoning_effort = 'auto'; form.thinking_mode = 'auto'; showKey.value = false
}
function changeLength(field: 'max_tokens' | 'context_window', event: Event) {
  const value = (event.target as HTMLInputElement).value
  form[field] = value === '' ? null : Number(value)
}
function resetLengths() {form.max_tokens = null; form.context_window = null}
function save() {
  cancel(); error.value = ''; message.value = ''
  try {
    const preferences = cleanPreferences(form)
    if (!form.name.trim()) throw new Error('请填写连接名称')
    const stored = saveModel(preferences,form.api_key,form.name)
    Object.assign(form,preferences)
    message.value = stored ? '配置已保存。API Key 仅保存在当前标签页会话。' : '配置已应用；浏览器限制了存储，关闭页面后需要重新填写。'
  } catch (reason) {error.value = (reason as Error).message}
}
function removeKey() {cancel(); clearKey(); form.api_key = ''; showKey.value = false; message.value = '已清除当前连接的会话 API Key。'}
async function discover() {
  cancel(); error.value = ''; message.value = ''
  try {form.base_url = normalizeBaseUrl(form.base_url)} catch (reason) {error.value = (reason as Error).message; return}
  controller = new AbortController(); const current = revision; busy.value = 'models'
  try {
    const result = await assistantApi.models({provider:form.provider,base_url:form.base_url,api_key:form.api_key.trim()},controller.signal)
    if (current !== revision) return
    models.value = result.models; truncated.value = result.truncated
    message.value = result.models.length ? `已获取 ${result.models.length} 个模型。请选择文本对话模型，列表不代表该模型已通过生成测试。` : '服务返回空列表，可以手动填写模型名称。'
  } catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '模型列表读取失败，可以手动填写'}
  finally {if (current === revision) busy.value = ''}
}
async function test() {
  cancel(); error.value = ''; message.value = ''
  let preferences
  try {preferences = cleanPreferences(form); Object.assign(form,preferences)} catch (reason) {error.value = (reason as Error).message; return}
  controller = new AbortController(); const current = revision; busy.value = 'test'
  try {
    const result = await assistantApi.test({...preferences,api_key:form.api_key.trim()},controller.signal)
    if (current === revision) message.value = `服务已返回文本，模型：${result.model}。${result.finish_reason === 'length' ? '测试达到输出上限，请增加输出预算。' : '保存配置后可用于右侧栏 AI 解读。'}`
  } catch (reason) {if (current === revision) error.value = reason instanceof Error ? reason.message : '连接失败'}
  finally {if (current === revision) busy.value = ''}
}
function previewImport() {
  importError.value = ''; imported.value = []
  try {const result = parseConnectionConfig(importText.value); imported.value = result.connections; importWarnings.value = result.warnings}
  catch (reason) {importError.value = (reason as Error).message}
}
async function readFile(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  imported.value = []; importWarnings.value = []; importError.value = ''; importText.value = ''
  if (file.size > 65536) {importError.value = '配置文件不能超过 64 KiB'; input.value = ''; return}
  try {
    const result = parseConnectionConfig(await file.text())
    imported.value = result.connections; importWarnings.value = result.warnings
  } catch (reason) {importError.value = reason instanceof Error ? reason.message : '无法读取配置文件'}
  input.value = ''
}
function applyImport() {
  if (!imported.value.length) return
  if (connectionProfiles.value.length + imported.value.length > 20) {importError.value = '导入后将超过 20 组连接，请先移除不用的连接'; return}
  let stored = true
  for (const entry of imported.value) stored = addConnection(entry.name,entry,entry.api_key) && stored
  refreshForm(); importText.value = ''; imported.value = []; importOpen.value = false
  message.value = stored ? '配置已导入为新连接，已有连接已保留。导入未发起网络请求，请获取模型列表或测试连接。' : '配置已在当前页面导入；浏览器限制了存储。'
}
function exportConfig(all = false) {
  try {
    const entries = all ? connectionProfiles.value : [{...cleanPreferences(form),name:form.name}]
    downloadBlob(new Blob([exportConnectionConfig(entries)],{type:'application/json'}),'celllens-ai-connections.json')
    message.value = '配置已导出，不含 API Key。'
  } catch (reason) {error.value = (reason as Error).message}
}
function downloadTemplate() {downloadBlob(new Blob([exportConnectionConfig([{...DEFAULT_MODEL,name:'我的 API'}])],{type:'application/json'}),'celllens-ai-template.json')}
</script>

<template>
  <section id="model-connection" class="card connection-settings" aria-labelledby="connection-heading">
    <div class="section-heading"><div><span class="eyebrow">MODEL CONNECTIONS</span><h2 id="connection-heading">大模型连接</h2><p>连接云端或本地模型，为科研结果提供辅助解读。</p></div><span class="local-badge">当前浏览器 · {{ connectionProfiles.length }} 组连接</span></div>
    <div class="connection-toolbar">
      <label class="profile-picker">当前解读连接<select :value="activeConnectionId" aria-label="当前解读连接" @change="switchConnection"><option v-for="profile in connectionProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}{{ profile.model ? ' · '+profile.model : '' }}</option></select></label>
      <button type="button" class="btn btn-sm" :disabled="connectionProfiles.length >= 20" @click="createConnection">＋ 新建连接</button>
      <button type="button" class="btn btn-sm" :aria-expanded="importOpen" @click="importOpen=!importOpen">导入配置</button>
      <button type="button" class="btn btn-sm" @click="exportConfig(true)">导出全部</button>
    </div>
    <div v-if="importOpen" class="import-panel">
      <h3>导入通用 API 配置</h3><p class="hint">支持 JSON、.env 文件或粘贴内容，可一次导入多组连接。先核对服务地址，应用后才加入本机连接。</p>
      <input ref="fileInput" type="file" accept=".json,.env,.txt,application/json,text/plain" aria-label="选择 API 配置文件" class="file-input" @change="readFile" />
      <div class="btn-row"><button type="button" class="btn btn-sm" @click="fileInput?.click()">选择配置文件</button><button type="button" class="btn btn-sm" @click="downloadTemplate">下载 JSON 模板</button></div>
      <label>配置内容<textarea v-model="importText" aria-label="配置内容" rows="5" maxlength="65536" autocomplete="off" spellcheck="false" placeholder='{"base_url":"https://api.example.com/v1","api_key":"…","model":"模型 ID"}' /></label>
      <button type="button" class="btn btn-sm" :disabled="!importText.trim()" @click="previewImport">解析并预览</button>
      <div v-if="imported.length" class="import-preview"><h4>待导入 {{ imported.length }} 组连接</h4><ul><li v-for="(entry,index) in imported" :key="index"><strong>{{ entry.name }}</strong><span>{{ entry.base_url }} · {{ entry.model || '模型待填写' }}</span><small>{{ entry.api_key ? '包含密钥，仅存入当前标签页会话' : '未包含密钥' }} · 上下文 {{ entry.context_window?.toLocaleString() ?? '模型默认' }} token</small></li></ul><p v-for="warning in importWarnings" :key="warning" class="hint">{{ warning }}</p><button type="button" class="btn btn-primary" @click="applyImport">导入为新连接</button></div>
      <p v-if="importError" class="notice notice-danger" role="alert">{{ importError }}</p>
    </div>
    <form @submit.prevent="save">
      <div class="config-block"><div class="block-heading"><span>01</span><h3>服务与认证</h3></div>
        <div class="form-grid"><label>连接名称<input v-model="form.name" maxlength="64" required placeholder="例如：科研解读 · 云端" /></label><label>模型提供商<select v-model="form.provider" aria-label="模型提供商" :disabled="loading || !providers.length" @change="changeProvider"><option v-for="provider in providers" :key="provider.id" :value="provider.id">{{ provider.label }}</option></select></label></div>
        <label>服务基础地址<input v-model="form.base_url" type="url" maxlength="512" required placeholder="https://api.example.com/v1" autocomplete="off" spellcheck="false" /></label>
        <p class="hint">可粘贴完整 {{ form.provider === 'anthropic' ? '/messages' : '/chat/completions' }} 地址，系统自动整理基础路径。{{ form.provider === 'custom' ? '支持 OpenAI 兼容网关、Ollama 和 LM Studio 的兼容接口。' : '' }}</p>
        <div v-if="endpoint" class="endpoint-preview"><span>请求地址</span><code>{{ endpoint }}</code></div>
        <p v-if="!loading && form.base_url && !permitted" class="notice notice-warn">该地址尚未加入部署允许列表。可先保存；连接检测和生成前，需由管理员配置 CELLLENS_ASSISTANT_EXTRA_ORIGINS 并重启后台。</p>
        <details class="allowed-origins"><summary>查看部署允许的服务地址</summary><p>{{ allowed.join('、') || '暂未读取' }}</p></details>
        <label>API Key <span class="key-field"><input v-model="form.api_key" aria-label="API Key" :type="showKey ? 'text' : 'password'" maxlength="4096" :placeholder="form.provider === 'custom' ? '本地服务无需认证时可留空' : '输入当前服务的 API Key'" autocomplete="off" spellcheck="false" /><button type="button" :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'" :aria-pressed="showKey" @click="showKey=!showKey">{{ showKey ? '隐藏' : '显示' }}</button></span></label>
        <p class="hint">密钥仅保存在当前标签页会话；刷新后可继续使用，不写入共享数据库或导出文件。离开共享设备前请清除密钥。</p>
      </div>
      <div class="config-block"><div class="block-heading"><span>02</span><h3>选择模型</h3></div>
        <div class="model-controls"><label>模型名称<input v-model="form.model" maxlength="128" placeholder="手动填写准确模型 ID，或从列表选择" autocomplete="off" spellcheck="false" /></label><button type="button" class="btn" :disabled="Boolean(busy) || !credentialsReady || loading" @click="discover">{{ busy === 'models' ? '获取中…' : '获取模型列表' }}</button></div>
        <p class="hint">只查询服务的模型列表，不发送科研数据。不支持列表接口时仍可手动填写；模型可用于对话还需生成测试确认。</p>
        <div v-if="models.length" class="model-browser"><div class="model-browser-heading"><strong>{{ models.length }} 个模型</strong><input v-model="search" type="search" aria-label="搜索模型" placeholder="搜索模型 ID 或名称" /></div><div class="model-list" role="group" aria-label="服务端模型列表"><button v-for="model in filteredModels" :key="model.id" type="button" :class="{selected:form.model===model.id}" :aria-pressed="form.model===model.id" @click="form.model=model.id"><span>{{ model.id }}</span><small>{{ model.name !== model.id ? model.name : (form.model === model.id ? '已选择' : '选择') }}</small></button><p v-if="!filteredModels.length" class="hint">没有匹配的模型，可继续手动填写。</p></div><p v-if="truncated" class="hint">列表已达到分页或数量上限，其余模型可手动填写。</p></div>
        <p v-if="selectedModel?.context_window" class="hint">服务声明此模型上下文为 {{ selectedModel.context_window.toLocaleString() }} token；默认由服务管理。</p>
      </div>
      <div class="config-block"><div class="block-heading"><span>03</span><h3>生成与上下文</h3></div><p v-if="!defaultLengthsSupported" class="notice notice-warn" role="status">后台尚未加载模型默认长度设置，请重启 CellLens 分析服务后再生成解读。</p>
        <div class="form-grid"><label>推理强度<select v-model="form.reasoning_effort" aria-label="推理强度" :disabled="effortOptions.length <= 1 || (form.provider === 'anthropic' && ['auto','disabled'].includes(form.thinking_mode))"><option v-for="effort in effortOptions" :key="effort" :value="effort">{{ effortNames[effort] }}</option></select></label><label>最大输出长度（token）<input :value="form.max_tokens ?? ''" type="number" min="256" max="2000000" step="1" placeholder="模型默认" @input="changeLength('max_tokens', $event)" /></label></div>
        <p class="hint">“服务默认”不发送额外推理参数。强度选项须由具体模型支持；提高强度可能增加耗时和费用。输出预算包含服务计入的思考 token。</p>
        <p class="hint">输出长度与上下文留空时使用模型服务默认值。平台不再指定 2,048 token 输出预算或 32,768 token 上下文限制。<button type="button" class="text-button" @click="resetLengths">恢复模型默认</button></p><p v-if="form.provider === 'anthropic'" class="hint">Claude 接口要求输出上限，默认读取服务声明的模型上限；服务未提供时会提示填写。</p>
        <template v-if="form.provider === 'anthropic'"><div class="form-grid"><label>Claude 思考模式<select v-model="form.thinking_mode" aria-label="Claude 思考模式"><option value="auto">服务默认</option><option value="disabled">关闭思考</option><option value="enabled">预算思考 · Extended</option><option value="adaptive">自适应思考 · Adaptive</option></select></label><label v-if="form.thinking_mode === 'enabled'">思考预算（token）<input v-model.number="form.thinking_budget" type="number" min="1024" :max="Math.min(7168,(form.max_tokens ?? 7169)-1)" step="1" /></label></div><p class="hint">预算思考至少 1024 token 且小于输出预算。自适应模式和 effort 的支持范围取决于 Claude 型号，请按服务文档选择。</p></template>
        <label>上下文窗口（token）<input :value="form.context_window ?? ''" type="number" min="4096" max="2000000" step="1" placeholder="模型默认" @input="changeLength('context_window', $event)" /></label><p class="hint">留空时由模型服务按实际容量校验。仅在需要额外限制时手动填写；不会截断科研摘要。</p>
        <details class="advanced-options"><summary>接口兼容选项</summary><label v-if="form.provider === 'openai' || form.provider === 'custom'">输出长度参数<select v-model="form.token_parameter" aria-label="输出长度参数"><option value="max_completion_tokens">max_completion_tokens</option><option value="max_tokens">max_tokens</option></select></label><p class="hint">{{ form.provider === 'openai' || form.provider === 'custom' ? '按接口文档选择输出预算字段。兼容网关不一定支持所有推理参数，报错时可先恢复服务默认。' : '输出预算字段按提供商协议自动匹配。' }}</p></details>
      </div>
      <p v-if="message" class="notice notice-ok" role="status">{{ message }}</p><p v-if="error" class="notice notice-danger" role="alert">{{ error }}</p>
      <div class="save-bar"><div class="btn-row"><button class="btn btn-primary" type="submit">保存配置</button><button class="btn" type="button" :disabled="Boolean(busy) || !credentialsReady || !form.model.trim()" @click="test">{{ busy === 'test' ? '测试中…' : '测试连接' }}</button><button v-if="busy" class="btn btn-sm" type="button" @click="cancel">取消等待</button><span v-if="dirty" class="unsaved">有未保存的修改</span></div><div class="secondary-actions"><button type="button" @click="exportConfig()">导出当前配置</button><button type="button" @click="removeKey">清除 API Key</button><button type="button" :disabled="connectionProfiles.length <= 1" @click="deleteConnection">移除当前连接</button></div><p class="hint">测试连接会发送一条简短消息，并可能消耗额度。保存配置后，右侧 AI 解读使用当前连接；发送科研摘要前仍可预览。</p></div>
    </form>
  </section>
</template>

<style scoped>
.connection-settings{padding:28px;scroll-margin-top:130px}.section-heading{display:flex;justify-content:space-between;align-items:start;gap:16px}.section-heading h2{font-size:23px;font-weight:500;margin:9px 0 12px}.section-heading p,.hint{font-size:12px;line-height:1.85;color:var(--muted);overflow-wrap:anywhere}.local-badge{font-size:10px;color:var(--primary);border:1px solid var(--border);padding:6px 9px;white-space:nowrap}.connection-toolbar{display:flex;align-items:end;gap:9px;flex-wrap:wrap;padding:20px 0 25px}.profile-picker{flex:1;min-width:180px}.connection-settings label{display:flex;flex-direction:column;gap:8px;font-size:12px;margin:16px 0}.connection-toolbar label{margin:0}.connection-settings input,.connection-settings select,.connection-settings textarea{box-sizing:border-box;width:100%;min-width:0;padding:11px 12px;border:1px solid var(--border-strong);border-radius:4px;background:var(--card);color:var(--ink);font:inherit}.connection-settings textarea{resize:vertical;max-height:300px;line-height:1.7}.connection-settings input:focus,.connection-settings select:focus,.connection-settings textarea:focus{outline:2px solid var(--primary);outline-offset:2px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.config-block{border-top:1px solid var(--border);padding:24px 0 16px}.block-heading{display:flex;align-items:center;gap:10px;margin-bottom:12px}.block-heading>span{font-size:10px;color:var(--primary);letter-spacing:1px}.block-heading h3{font-size:15px;font-weight:500;margin:0}.endpoint-preview{display:flex;gap:14px;padding:10px 12px;background:var(--surface-soft);font-size:10px;line-height:1.7;color:var(--muted)}.endpoint-preview>span{flex:none}.endpoint-preview code{overflow-wrap:anywhere;color:var(--ink)}.allowed-origins,.advanced-options{font-size:11px;color:var(--muted);line-height:1.9;margin:16px 0}.allowed-origins p{overflow-wrap:anywhere}.connection-settings summary{cursor:pointer;color:var(--primary)}.key-field{display:flex;border:1px solid var(--border-strong);border-radius:4px;min-width:0}.key-field input{border:0}.key-field button{background:none;border:0;color:var(--primary);padding:0 13px;font:11px var(--font);cursor:pointer;white-space:nowrap}.model-controls{display:flex;gap:10px;align-items:end}.model-controls label{flex:1}.model-controls>.btn{margin-bottom:16px}.model-browser{border:1px solid var(--border);border-radius:4px;margin:18px 0}.model-browser-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:12px;background:var(--surface-soft);font-size:11px}.model-browser-heading input{max-width:260px;padding:7px 10px}.model-list{max-height:240px;overflow:auto;padding:6px}.model-list button{display:flex;justify-content:space-between;gap:18px;align-items:center;width:100%;padding:11px 10px;text-align:left;background:transparent;color:var(--ink);border:1px solid transparent;border-radius:3px;font:12px var(--font);cursor:pointer;overflow-wrap:anywhere}.model-list button.selected{border-color:var(--primary);background:var(--surface-soft)}.model-list button:hover{background:var(--surface-soft)}.model-list small{font-size:10px;color:var(--muted);flex:none;max-width:40%;overflow-wrap:anywhere}.model-list>.hint{padding:12px}.import-panel{padding:22px;background:var(--surface-soft);border:1px solid var(--border);margin-bottom:24px}.import-panel h3{font-size:15px;font-weight:500;margin:0 0 10px}.import-panel .file-input{display:none}.import-preview{margin-top:20px;border-top:1px solid var(--border);padding-top:14px}.import-preview h4{font-size:12px;font-weight:500}.import-preview ul{padding:0;list-style:none}.import-preview li{display:flex;flex-direction:column;gap:7px;padding:13px 0;border-bottom:1px solid var(--border);font-size:12px;overflow-wrap:anywhere}.import-preview li span,.import-preview li small{font-size:11px;color:var(--muted)}.save-bar{border-top:1px solid var(--border);padding:24px 0 0;margin-top:8px}.btn-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.unsaved{font-size:10px;color:var(--muted)}.secondary-actions{display:flex;gap:22px;flex-wrap:wrap;margin-top:22px}.secondary-actions button,.text-button{border:0;padding:0;background:none;color:var(--primary);font:11px var(--font);cursor:pointer}.secondary-actions button:disabled{opacity:.4;cursor:default}.save-bar>.hint{margin-top:20px}.connection-settings button:focus-visible,.connection-settings summary:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
@media(max-width:760px){.connection-settings{padding:20px}.section-heading{flex-direction:column}.form-grid{grid-template-columns:1fr;gap:0}.model-controls{flex-wrap:wrap}.model-controls label{flex-basis:100%;margin-bottom:0}.model-controls>.btn{margin:0}.model-browser-heading{flex-wrap:wrap;gap:10px}.model-browser-heading input{max-width:none}.endpoint-preview{flex-direction:column;gap:4px}.import-panel{padding:15px}}
</style>
