<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { apiKey, clearKey, modelPreferences, saveModel, setTheme, theme, type ThemePreference } from '../stores/preferences'
import { assistantApi } from '../api/assistant'
import { userDataApi } from '../api/userData'
import type { DataCapabilities } from '../types/userData'
const form = reactive({...modelPreferences, api_key: apiKey.value})
const allowed = ref<string[]>([]), data = ref<DataCapabilities | null>(null)
const message = ref(''), error = ref(''), testing = ref(false), loading = ref(true)
let controller: AbortController | undefined
onMounted(async () => {
  try {const results = await Promise.all([assistantApi.capabilities(), userDataApi.capabilities()]); allowed.value = results[0].allowed_origins; data.value = results[1]}
  catch (reason) {error.value = reason instanceof Error ? reason.message : '配置读取失败'}
  finally {loading.value = false}
})
onBeforeUnmount(() => controller?.abort())
function save() {
  error.value = ''; message.value = ''
  if (!form.base_url.trim() || form.max_tokens < 256 || form.max_tokens > 8192) {error.value = '请填写服务地址，输出预算范围为 256–8192'; return}
  const stored = saveModel({base_url: form.base_url.trim(), model: form.model.trim(), max_tokens: form.max_tokens, token_parameter: form.token_parameter}, form.api_key)
  message.value = stored ? '配置已保存。API Key 仅保存在当前标签页会话。' : '当前页面已应用配置；浏览器限制了存储，关闭页面后需要重新填写。'
}
function removeKey() {clearKey(); form.api_key = ''; message.value = '已清除当前标签页的 API Key。'}
function preset(url: string, parameter: 'max_completion_tokens' | 'max_tokens') {form.base_url = url; form.token_parameter = parameter; message.value = ''; error.value = ''}
async function test() {
  testing.value = true; error.value = ''; message.value = ''; controller = new AbortController()
  try {const result = await assistantApi.test({...form, api_key: form.api_key.trim()}, controller.signal); message.value = `服务已返回文本，模型：${result.model}。请保存配置后前往结果页面生成解读。`}
  catch (reason) {error.value = reason instanceof Error ? reason.message : '连接失败'}
  finally {testing.value = false}
}
function changeTheme(event: Event) {if (!setTheme((event.target as HTMLSelectElement).value as ThemePreference)) message.value = '外观已应用；当前浏览器无法保存偏好。'}
</script>
<template>
  <div class="page settings-page">
    <header class="page-heading"><div><span class="eyebrow">WORKSPACE PREFERENCES</span><h1>系统设置</h1><p>管理当前浏览器的外观和大模型连接。</p></div><RouterLink to="/workbench" class="btn">返回工作台</RouterLink></header>
    <div class="settings-layout"><nav class="settings-nav" aria-label="设置分类"><a href="#appearance">外观</a><a href="#model-connection">大模型连接</a><a href="#workspace-limits">分析服务</a></nav><div>
      <section id="appearance" class="card settings-section"><span class="eyebrow">APPEARANCE</span><h2>外观</h2><div class="setting-line"><div><h3>页面主题</h3><p>跟随系统时，随设备的外观设置自动切换。</p></div><select aria-label="页面主题" :value="theme" @change="changeTheme"><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div></section>
      <form id="model-connection" class="card settings-section" @submit.prevent="save"><span class="eyebrow">OPENAI COMPATIBLE API</span><h2>大模型连接</h2><p class="section-intro">用于结果解读、覆盖说明和后续验证建议。生成内容单独展示，不改动分析数据。每次发送前可预览结果摘要。</p>
        <div class="provider-presets"><button type="button" class="btn btn-sm" @click="preset('https://api.openai.com/v1','max_completion_tokens')">OpenAI</button><button type="button" class="btn btn-sm" @click="preset('https://api.deepseek.com','max_tokens')">DeepSeek</button><button type="button" class="btn btn-sm" @click="preset('https://api.siliconflow.cn/v1','max_tokens')">硅基流动</button></div>
        <label>服务基础地址<input v-model="form.base_url" type="url" required maxlength="512" placeholder="https://api.example.com/v1" autocomplete="off" /></label><p class="field-hint">基础地址无需填写 /chat/completions。部署允许的服务：{{ allowed.join('、') || (loading ? '读取中…' : '暂未读取') }}。自定义或本机地址由管理员加入允许列表。</p>
        <label>模型名称<input v-model="form.model" maxlength="128" placeholder="填写服务提供的准确模型名称" autocomplete="off" /></label>
        <label>API Key<input v-model="form.api_key" type="password" maxlength="4096" placeholder="输入当前服务的 API Key" autocomplete="off" spellcheck="false" /></label><p class="field-hint">密钥仅保存在当前标签页 sessionStorage，刷新页面仍可用；不写入共享数据库。关闭标签页结束会话，浏览器恢复会话可能保留，请在离开共享设备前清除。服务地址、模型名与输出预算保存在本机浏览器。</p>
        <div class="form-grid"><label>最大输出预算<input v-model.number="form.max_tokens" type="number" min="256" max="8192" required /></label><label>输出预算字段<select v-model="form.token_parameter"><option value="max_completion_tokens">max_completion_tokens（OpenAI）</option><option value="max_tokens">max_tokens（兼容服务）</option></select></label></div><p class="field-hint">推理模型的预算可能包含思考 token；具体字段和额度以服务提供商为准。</p>
        <div class="btn-row"><button class="btn btn-primary" type="submit">保存配置</button><button class="btn" type="button" :disabled="testing || !form.model.trim() || !form.api_key.trim()" @click="test">{{ testing ? '连接中…' : '测试连接' }}</button><button class="btn" type="button" @click="removeKey">清除 API Key</button></div><p class="field-hint">测试连接会发送一条简短消息，并可能消耗服务额度。只有点击生成解读时，才会发送所选结果摘要。</p>
      </form>
      <p v-if="message" class="notice notice-ok" role="status">{{ message }}</p><p v-if="error" class="notice notice-danger" role="alert">{{ error }}</p>
      <section id="workspace-limits" class="card settings-section"><span class="eyebrow">ANALYSIS SERVICE</span><h2>分析服务</h2><p class="section-intro">当前部署的资源限制由管理员配置，供上传与分析时参考。</p><dl v-if="data"><dt>CPU 上传分析</dt><dd>{{ data.worker_enabled ? '已启用' : '未启用' }}</dd><dt>单文件上限</dt><dd>{{ (data.max_upload_bytes / 1024 / 1024).toFixed(0) }} MB</dd><dt>工作区源文件配额</dt><dd>{{ (data.max_workspace_storage_bytes / 1024 / 1024 / 1024).toFixed(1) }} GB</dd><dt>矩阵规模上限</dt><dd>{{ data.max_cells.toLocaleString() }} 细胞 × {{ data.max_genes.toLocaleString() }} 基因（最多 {{ data.max_matrix_values.toLocaleString() }} 元素）</dd></dl><p v-else class="muted">{{ loading ? '读取服务配置…' : '服务配置暂不可用' }}</p></section>
    </div></div>
  </div>
</template>
<style scoped>
.settings-layout{display:grid;grid-template-columns:170px minmax(0,1fr);gap:36px;max-width:1050px}.settings-nav{display:flex;flex-direction:column;gap:20px;align-self:start;position:sticky;top:140px;font-size:12px;border-left:1px solid var(--border);padding:8px 18px}.settings-section{scroll-margin-top:140px;padding:28px;margin-bottom:20px}.settings-section h2{font-size:22px;font-weight:500;margin:8px 0 22px}.settings-section h3{font-size:13px;font-weight:500}.section-intro,.setting-line p{font-size:12px;color:var(--muted);line-height:1.9}.setting-line{display:flex;justify-content:space-between;gap:24px;align-items:center}.setting-line select{width:160px;flex:none}.settings-section label{display:flex;flex-direction:column;gap:8px;font-size:12px;margin:20px 0 0}.settings-section input,.settings-section select{width:100%;padding:10px 12px;border:1px solid var(--border-strong);background:var(--card);color:var(--ink);border-radius:3px;font:inherit}.settings-section .field-hint{font-size:11px;color:var(--muted);line-height:1.9;overflow-wrap:anywhere;margin:9px 0 16px}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.provider-presets{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}.settings-section .btn-row{margin-top:24px}.settings-section dl{display:grid;grid-template-columns:150px 1fr;gap:16px;font-size:12px}.settings-section dt{color:var(--muted)}.settings-section dd{margin:0}.settings-layout>.notice{margin:20px 0}@media(max-width:760px){.settings-layout{grid-template-columns:1fr;gap:22px}.settings-nav{position:static;flex-direction:row;border-left:0;border-bottom:1px solid var(--border);padding:0 0 16px}.settings-section{padding:22px 18px}.form-grid{grid-template-columns:1fr;gap:0}.settings-section dl{grid-template-columns:1fr;gap:7px}.settings-section dd{margin-bottom:10px}}
</style>
<style scoped>
.settings-layout>div,.settings-section label,.settings-section select{min-width:0}.settings-section .setting-line select{width:160px;max-width:45%}
@media(max-width:600px){.setting-line{align-items:start;flex-direction:column;gap:10px}.settings-section .setting-line select{width:100%;max-width:none}}
</style>
