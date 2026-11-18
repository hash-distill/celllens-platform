<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { assistantOpen, assistantSelection, assistantSource, type AssistantSource } from '../stores/assistantSource'
import { listResearchRecords } from '../api/researchRecords'
import { selectRecords, type ResearchRecord } from '../utils/researchRecords'
import { taskName } from '../utils/biologyLocale'
import AssistantPanel from './AssistantPanel.vue'
import UiIcon from './UiIcon.vue'

const route = useRoute()
const closeButton = ref<HTMLButtonElement | null>(null)
const pickedSource = ref<AssistantSource | null>(null)
const activeSource = computed(() => pickedSource.value ?? assistantSource.value)
const selection = computed(() => pickedSource.value ? {view:'overview' as const} : assistantSelection.value)
const records = ref<ResearchRecord[]>([]), recordsLoading = ref(false), recordsError = ref(''), search = ref('')
const pickerOpen = ref(false)
const available = computed(() => selectRecords(records.value.filter(record => record.sourceLabel !== '合成示例'), {category:'all', status:'completed', resultsOnly:true, query:search.value}))
let returnFocus: HTMLElement | null = null, recordsController: AbortController | undefined
const focusLabel = computed(() => {
  const focus = selection.value
  if(focus.view === 'chart' && focus.chart_type && focus.chart_type !== 'projection') return `${{distribution:'单基因表达分布',heatmap:'单细胞表达热图',dotplot:'群体表达气泡图'}[focus.chart_type]} · ${focus.feature_id ?? ''}`
  if (activeSource.value?.kind === 'measured') {
    const label = focus.view === 'genes' ? '实测基因表达变化' : focus.view === 'metabolism' ? '实测表达派生代谢评分' : '实测结果摘要'
    return focus.feature_id ? `${label} · ${focus.feature_kind === 'task' ? taskName(focus.feature_id) : focus.feature_id}` : label
  }
  if (focus.view === 'chart') return `${focus.space === 'metabolic' ? '代谢' : '表达'} ${(focus.embedding ?? 'pca').toUpperCase()} · ${focus.feature_kind === 'task' ? taskName(focus.feature_id ?? '') : focus.feature_id}`
  return {overview:'预测结果摘要', genes:'基因表达变化', metabolism:'代谢任务变化', comparison:'预测与实测比较'}[focus.view]
})
async function loadRecords() {
  recordsController?.abort()
  const current = recordsController = new AbortController()
  recordsLoading.value = true; recordsError.value = ''
  try {const value = await listResearchRecords(current.signal); if (!current.signal.aborted) records.value = value}
  catch (reason) {if (!current.signal.aborted) recordsError.value = reason instanceof Error ? reason.message : '结果列表读取失败'}
  finally {if (!current.signal.aborted) recordsLoading.value = false}
}
function choose(record: ResearchRecord) {
  pickedSource.value = {kind:record.category === 'measured' ? 'measured' : 'run', id:record.id, title:record.title, completed:true, view:'overview'}
  pickerOpen.value = false; search.value = ''
}
watch(assistantSource, source => {if (source) {pickedSource.value = null; pickerOpen.value = false}})
watch(assistantOpen, async open => {
  if (open) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (!activeSource.value) pickerOpen.value = true
    void loadRecords()
    await nextTick(); if (assistantOpen.value) closeButton.value?.focus()
  }
})
function close() {
  assistantOpen.value = false
  if (returnFocus?.isConnected) returnFocus.focus()
  else document.querySelector<HTMLButtonElement>('.utility-rail button[aria-controls="assistant-dialog"]')?.focus()
}
function onKey(event: KeyboardEvent) {
  if (assistantOpen.value && event.key === 'Escape' && !event.defaultPrevented) {event.preventDefault(); close()}
}
watch(() => route.path, path => {if (path === '/settings' && assistantOpen.value) close()})
document.addEventListener('keydown', onKey)
onBeforeUnmount(() => {document.removeEventListener('keydown', onKey); recordsController?.abort()})
</script>
<template>
  <section v-show="assistantOpen" id="assistant-dialog" class="assistant-dialog" role="dialog" aria-modal="false" aria-label="AI 科研解读">
    <header class="floating-heading"><span class="assistant-emblem"><UiIcon name="sparkle" :size="23" /></span><div><span class="eyebrow">CELLLENS · RESEARCH ASSISTANT</span><h2>AI 科研解读</h2></div><button ref="closeButton" class="close-assistant" type="button" aria-label="收起 AI 解读" title="收起 AI 解读 · Esc" @click="close">×</button></header>
    <div class="source-toolbar"><button class="source-toggle" :aria-expanded="pickerOpen" aria-controls="assistant-source-picker" @click="pickerOpen = !pickerOpen"><UiIcon name="layers" :size="16"/><span><small>{{ activeSource ? (activeSource.kind === 'measured' ? '实测分析' : '模型预测') : '研究上下文' }}</small><strong>{{ activeSource?.title ?? '选择一份已完成结果' }}</strong></span><span class="source-change">{{ pickerOpen ? '收起' : '切换' }}⌄</span></button><p v-if="activeSource" class="focus-label"><span class="context-dot"/>{{ focusLabel }}<span v-if="!pickedSource"> · 跟随当前视图</span></p></div>
    <div v-if="pickerOpen" id="assistant-source-picker" class="source-picker">
      <div class="picker-heading"><strong>选择研究结果</strong><button type="button" :disabled="recordsLoading" @click="loadRecords">{{ recordsLoading ? '读取中…' : '刷新' }}</button></div>
      <label class="source-search"><UiIcon name="search" :size="15"/><input v-model="search" maxlength="128" placeholder="搜索细胞、扰动基因或编号" aria-label="搜索解读来源" /></label>
      <p v-if="recordsLoading" class="picker-status" role="status">正在读取已完成研究…</p>
      <p v-else-if="recordsError" class="picker-status picker-error" role="alert">{{ recordsError }}<button @click="loadRecords">重试</button></p>
      <div v-else-if="available.length" class="source-options"><button v-for="record in available" :key="record.key" class="source-option" :class="{selected:activeSource?.id === record.id && activeSource?.kind === (record.category === 'measured' ? 'measured' : 'run')}" @click="choose(record)"><span class="record-symbol"><UiIcon :name="record.category === 'measured' ? 'chart' : 'cube'" :size="17"/></span><span><strong>{{ record.title }}</strong><small>{{ record.sourceLabel }} · {{ record.id }}</small></span><UiIcon name="arrow" :size="14"/></button></div>
      <div v-else class="picker-status"><p>{{ search ? '没有匹配的已完成结果，试试其他关键词。' : '还没有可解读的已完成结果。' }}</p><RouterLink to="/records" @click="close">查看实验记录 →</RouterLink></div>
      <p class="picker-note">仅列出已完成的真实研究；选择后可预览将发送的摘要。</p>
    </div>
    <AssistantPanel v-if="activeSource?.completed" class="floating-panel" :source-kind="activeSource.kind" :source-id="activeSource.id" :selection="selection" />
    <template v-else>
      <div class="assistant-welcome">
        <div class="welcome-symbol" aria-hidden="true"><UiIcon name="sparkle" :size="29"/></div><span class="eyebrow">YOUR RESEARCH, IN CONTEXT</span><h3>{{ activeSource ? '等待分析完成，继续探索' : '读懂变化，形成下一步问题' }}</h3><p>{{ activeSource ? '完整结果保存后，即可核对统计摘要并交给所选模型解读。' : '从一份研究结果出发，结合表达、代谢与来源证据，整理值得关注的发现。' }}</p>
        <div class="welcome-prompts"><div><UiIcon name="chart" :size="17"/><strong>梳理关键变化</strong><span>哪些基因与代谢任务值得关注</span></div><div><UiIcon name="compare" :size="17"/><strong>厘清证据边界</strong><span>区分实测、预测与待验证解释</span></div><div><UiIcon name="layers" :size="17"/><strong>构思验证方向</strong><span>从当前结果提出可检验的问题</span></div></div>
      </div>
      <div class="empty-composer"><div><UiIcon name="file" :size="15"/><span>先选择研究结果，再开始提问</span><button disabled aria-label="选择结果后发送">↑</button></div><RouterLink to="/settings#model-connection" @click="close"><UiIcon name="settings" :size="12"/> 配置模型连接</RouterLink></div>
    </template>
  </section>
</template>
<style scoped>
.assistant-dialog{position:fixed;right:66px;top:84px;bottom:20px;width:520px;max-width:calc(100vw - 88px);max-height:calc(100dvh - 104px);z-index:64;display:flex;flex-direction:column;background:var(--card);color:var(--ink);border:1px solid var(--surface-tint-border-strong,var(--border-strong));border-radius:18px;box-shadow:0 18px 65px #163b2b25,0 3px 14px #163b2b12;overflow:hidden}.floating-heading{display:flex;align-items:center;gap:13px;padding:21px 24px 18px;flex:none;background:linear-gradient(110deg,var(--surface-tint),var(--card))}.assistant-emblem{display:grid;place-items:center;width:43px;height:43px;border-radius:13px;background:var(--primary);color:var(--on-primary,#fff);box-shadow:0 5px 14px #135c3520}.eyebrow{font-size:11px;letter-spacing:.12em;color:var(--primary)}.floating-heading h2{font-size:20px;font-weight:600;letter-spacing:.02em;margin:5px 0 0}.close-assistant{margin-left:auto;flex:none;width:31px;height:31px;border:1px solid var(--border);border-radius:11px;background:var(--card);color:var(--muted);font-size:22px;cursor:pointer}.source-toolbar{padding:0 22px 15px;border-bottom:1px solid var(--border);flex:none;background:var(--card)}.source-toggle{width:100%;display:flex;align-items:center;gap:12px;text-align:left;padding:12px 14px;border:1px solid var(--surface-tint-border,var(--border));border-radius:12px;background:var(--surface-tint);color:var(--primary);font:inherit;cursor:pointer}.source-toggle>span:nth-child(2){flex:1;min-width:0}.source-toggle small{font-size:11px;display:block;color:var(--muted);margin-bottom:4px}.source-toggle strong{font-size:14px;font-weight:500;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-change{font-size:12px;flex:none}.focus-label{margin:12px 2px 0;font-size:12px;line-height:1.6;color:var(--muted);overflow-wrap:anywhere}.context-dot{display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--primary);margin-right:5px;flex:none}.source-picker{flex:none;max-height:42%;overflow:auto;border-bottom:1px solid var(--border);padding:15px 22px;background:var(--surface-soft);overscroll-behavior:contain}.picker-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}.picker-heading strong{font-size:14px;font-weight:500}.picker-heading button,.picker-status button{border:0;background:none;font:13px var(--font);color:var(--primary);cursor:pointer}.source-search{display:flex;align-items:center;gap:11px;border:1px solid var(--border);background:var(--card);border-radius:11px;padding:11px 12px;color:var(--muted)}.source-search input{border:0;outline:none;background:transparent;font:13px var(--font);color:var(--ink);width:100%;min-width:0}.source-search:focus-within{outline:2px solid var(--primary);outline-offset:2px}.source-options{margin-top:11px;max-height:180px;overflow:auto}.source-option{display:flex;gap:12px;align-items:center;text-align:left;width:100%;border:1px solid transparent;border-radius:11px;padding:11px 11px;background:transparent;color:var(--ink);cursor:pointer}.source-option:hover,.source-option.selected{background:var(--card);border-color:var(--surface-tint-border)}.source-option>span:nth-child(2){min-width:0;flex:1}.source-option strong{display:block;font:500 14px var(--font);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-option small{display:block;font:11px var(--font);color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-top:5px}.record-symbol{display:grid;place-items:center;width:31px;height:31px;background:var(--primary-weak);border:1px solid var(--surface-tint-border);border-radius:11px;color:var(--primary);flex:none}.source-option>svg{color:var(--primary);flex:none}.picker-note{font-size:11px;color:var(--muted);line-height:1.7;margin:12px 0 0}.picker-status{font-size:14px;line-height:1.8;color:var(--muted);padding:12px 0;overflow-wrap:anywhere}.picker-error{color:var(--danger)}.floating-panel{min-height:0;flex:1}.assistant-welcome{flex:1;min-height:100px;overflow:auto;padding:25px 28px 22px;overscroll-behavior:contain}.welcome-symbol{display:grid;place-items:center;color:var(--primary);background:var(--surface-tint);border:1px solid var(--surface-tint-border);border-radius:14px;width:51px;height:51px;margin-bottom:19px}.assistant-welcome>.eyebrow{font-size:11px}.assistant-welcome h3{font-size:23px;line-height:1.5;letter-spacing:-.02em;font-weight:500;margin:11px 0 12px}.assistant-welcome>p{font-size:14px;line-height:1.9;color:var(--muted);margin:0 0 23px}.welcome-prompts{display:grid;gap:11px}.welcome-prompts>div{display:grid;grid-template-columns:22px 1fr;gap:5px 11px;border:1px solid var(--border);border-radius:12px;padding:14px 14px}.welcome-prompts svg{grid-row:span 2;color:var(--primary);margin-top:2px}.welcome-prompts strong{font-size:14px;font-weight:500}.welcome-prompts span{font-size:12px;color:var(--muted)}.empty-composer{padding:16px 22px 14px;border-top:1px solid var(--border);flex:none}.empty-composer>div{display:flex;align-items:center;gap:11px;border:1px solid var(--border);border-radius:14px;padding:14px;background:var(--surface-soft);font-size:13px;color:var(--muted)}.empty-composer button{margin-left:auto;border:0;border-radius:11px;width:28px;height:28px;background:var(--surface-tint-border);color:var(--muted);font-size:18px}.empty-composer>a{display:flex;align-items:center;gap:4px;font-size:12px;color:var(--muted);margin-top:13px;text-decoration:none}.assistant-dialog button:focus-visible,.assistant-dialog a:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.assistant-dialog button:disabled{cursor:default;opacity:.6}@media(max-width:700px){.assistant-dialog{right:14px;left:14px;top:74px;bottom:14px;width:auto;max-width:none;max-height:calc(100dvh - 86px);border-radius:14px}.floating-heading{padding:17px 18px}.source-toolbar{padding:0 16px 14px}.source-picker{padding:14px 16px;max-height:38%}.assistant-welcome{padding:20px}.assistant-welcome h3{font-size:21px}.empty-composer{padding:14px 16px}.assistant-welcome>p{margin-bottom:16px}.welcome-symbol{margin-bottom:13px}}@media(max-height:720px){.assistant-welcome{padding-top:17px}.welcome-symbol{display:none}.welcome-prompts{gap:6px}.welcome-prompts>div{padding:11px 14px}.source-options{max-height:120px}}
</style>
