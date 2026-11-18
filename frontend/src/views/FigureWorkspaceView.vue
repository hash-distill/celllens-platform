<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { apiFetch } from '../api/http'
import { accessSession } from '../stores/access'
import { downloadBlob } from '../utils/csv'

type Chart = 'projection' | 'distribution' | 'pathways'
type Format = 'svg' | 'png' | 'pdf' | 'csv' | 'html' | 'zip'
interface FigureSpec {
  chart: Chart; embedding: 'pca' | 'umap'; gene: string; group: 'all' | 'control' | 'observed' | 'predicted'
  title: string; note: string; direction: 'both' | 'up' | 'down'; limit: number
}
interface FigureContext {
  result: { background: { cell_line: string }; target: { perturbation: string }; provenance: { manifest_sha256: string | null } }
  genes: string[]; availability: Record<Chart, boolean>; reasons: Partial<Record<Chart, string>>
  pathways?: {resource?: {release?: string}; coverage?: {mapped_background_count?:number; tested_count?:number}}
}
interface SavedFigure { id: string; spec: FigureSpec; created_at: string; manifest_sha256: string | null }
const route = useRoute()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const recordKind = computed(() => typeof route.params.recordKind === 'string' ? route.params.recordKind : '')
const recordId = computed(() => typeof route.params.recordId === 'string' ? route.params.recordId : '')
const validIdentity = computed(() => ['measured', 'prediction'].includes(recordKind.value) && Boolean(recordId.value))
const endpoint = computed(() => `/figures/${encodeURIComponent(recordKind.value)}/${encodeURIComponent(recordId.value)}`)
const resultLink = computed(() => validIdentity.value ? (recordKind.value === 'measured' ? `/measured/${encodeURIComponent(recordId.value)}` : `/runs/${encodeURIComponent(recordId.value)}`) : '/records')
const charts: { id: Chart; label: string; description: string }[] = [
  { id: 'projection', label: '细胞投影', description: '查看表达空间中的群体分布' },
  { id: 'distribution', label: '表达分布', description: '比较已保存的基因表达观测' },
  { id: 'pathways', label: '通路证据', description: '整理当前结果中的通路条目' },
]
const defaults = (): FigureSpec => ({ chart: 'projection', embedding: 'pca', gene: '', group: 'all', title: '', note: '', direction: 'both', limit: 10 })
const draft = reactive<FigureSpec>(defaults())
const context = ref<FigureContext | null>(null), saved = ref<SavedFigure[]>([])
const loading = ref(false), rendering = ref(false), saving = ref(false), exporting = ref(false), listLoading = ref(false)
const loadError = ref(''), renderError = ref(''), actionError = ref(''), listError = ref(''), notice = ref('')
const previewUrl = ref(''), renderedSpec = ref<FigureSpec | null>(null), selectedId = ref(''), exportFormat = ref<Format>('svg')
const renderedSavedId = ref(''), failedRestore = ref<SavedFigure | null>(null)
const reportFormat = ref<'html' | 'zip'>('html')
const confirmingRemoval = ref(''), removing = ref('')
const saveUncertain = ref(false)
let contextControl: AbortController | undefined, renderControl: AbortController | undefined
let saveControl: AbortController | undefined, exportControl: AbortController | undefined, listControl: AbortController | undefined
let removeControl: AbortController | undefined
const dirty = computed(() => Boolean(renderedSpec.value) && JSON.stringify(draft) !== JSON.stringify(renderedSpec.value))
const chartTitle = (chart: Chart) => charts.find(item => item.id === chart)?.label ?? chart
const selected = computed(() => saved.value.find(item => item.id === selectedId.value) ?? null)
const reason = computed(() => context.value?.reasons?.[draft.chart] || '当前冻结结果未保存此图所需的数据。')
const validDraft = computed(() => Boolean(context.value?.availability[draft.chart]) && draft.title.length <= 120 && draft.note.length <= 2000
  && Number.isInteger(Number(draft.limit)) && Number(draft.limit) >= 1 && Number(draft.limit) <= 30
  && (draft.chart !== 'distribution' || context.value?.genes.includes(draft.gene)))
function message(error: unknown, fallback: string) { return error instanceof Error ? error.message : fallback }
function clearPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''; renderedSpec.value = null; renderedSavedId.value = ''; failedRestore.value = null
}
function abortAll() {
  for (const controller of [contextControl, renderControl, saveControl, exportControl, listControl, removeControl]) controller?.abort()
  loading.value = false; rendering.value = false; saving.value = false; exporting.value = false; listLoading.value = false
  removing.value = ''; confirmingRemoval.value = ''
}
function fingerprintMatches(item: SavedFigure) { return item.manifest_sha256 === context.value?.result.provenance.manifest_sha256 }
async function checkedBlob(path: string, format: Format, control: AbortController, spec?: FigureSpec) {
  const blob = await apiFetch<Blob>(path, { method: spec ? 'POST' : 'GET', body: spec, responseType: 'blob', query: { format }, signal: control.signal, timeoutMs: 120000 })
  if (control.signal.aborted) throw new Error('请求已取消')
  const mimes: Record<Format, string[]> = { svg: ['image/svg+xml'], png: ['image/png'], pdf: ['application/pdf'], csv: ['text/csv', 'application/csv'], html: ['text/html'], zip: ['application/zip', 'application/x-zip-compressed'] }
  if (!(blob instanceof Blob) || !blob.size || !mimes[format].includes(blob.type.split(';')[0]!.toLowerCase())) throw new Error('返回文件类型与所选格式不符，请重试')
  if (format === 'svg' && !/<svg[\s>]/i.test(await blob.slice(0, 1024).text())) throw new Error('预览文件无有效 SVG 内容')
  if (control.signal.aborted) throw new Error('请求已取消')
  return blob
}
async function loadSaved() {
  if (readOnly.value || !validIdentity.value || !context.value) return
  listControl?.abort(); const control = listControl = new AbortController(), path = endpoint.value
  listLoading.value = true; listError.value = ''
  try {
    const result = await apiFetch<{ items: SavedFigure[]; total: number }>(`${path}/saved`, { signal: control.signal })
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    saved.value = result.items; saveUncertain.value = false
    if (!saved.value.some(item => item.id === selectedId.value)) selectedId.value = ''
  } catch (error) { if (!control.signal.aborted) listError.value = message(error, '图表清单读取失败') }
  finally { if (!control.signal.aborted) listLoading.value = false }
}
async function load() {
  abortAll(); clearPreview(); context.value = null; saved.value = []; selectedId.value = ''
  loadError.value = ''; renderError.value = ''; actionError.value = ''; listError.value = ''; notice.value = ''; saveUncertain.value = false
  Object.assign(draft, defaults())
  if (readOnly.value) return
  if (!validIdentity.value) { loadError.value = '研究标识无效，请从已有结果进入图表工作区。'; return }
  const control = contextControl = new AbortController(), path = endpoint.value
  loading.value = true
  try {
    const result = await apiFetch<FigureContext>(`${path}/context`, { signal: control.signal })
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    context.value = result
    draft.chart = charts.find(item => result.availability[item.id])?.id ?? 'projection'
    draft.gene = ''
    if (draft.chart === 'distribution') draft.gene = result.genes[0] ?? ''
    await Promise.allSettled([loadSaved(), result.availability[draft.chart] ? renderFigure() : Promise.resolve()])
  } catch (error) { if (!control.signal.aborted) loadError.value = message(error, '图表上下文读取失败') }
  finally { if (!control.signal.aborted) loading.value = false }
}
async function renderFigure() {
  if (readOnly.value || !validIdentity.value || !validDraft.value || removing.value) return
  renderControl?.abort(); exportControl?.abort(); exporting.value = false
  clearPreview(); renderError.value = ''; actionError.value = ''; notice.value = ''
  const control = renderControl = new AbortController(), path = endpoint.value, spec: FigureSpec = { ...draft, limit: Number(draft.limit) }
  rendering.value = true
  try {
    const blob = await checkedBlob(`${path}/render`, 'svg', control, spec)
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    previewUrl.value = URL.createObjectURL(blob); renderedSpec.value = spec
  } catch (error) { if (!control.signal.aborted) renderError.value = message(error, '图表生成失败，请调整设置后重试') }
  finally { if (!control.signal.aborted) rendering.value = false }
}
function chooseChart(chart: Chart) {
  draft.chart = chart
  if (chart === 'distribution' && !draft.gene) draft.gene = context.value?.genes[0] ?? ''
  if (chart !== 'distribution') draft.gene = ''
  if (chart === 'pathways') draft.group = 'all'
}
async function restore(item: SavedFigure) {
  if (readOnly.value || !fingerprintMatches(item) || saving.value || removing.value) return
  selectedId.value = item.id; Object.assign(draft, defaults(), item.spec)
  renderControl?.abort(); exportControl?.abort(); exporting.value = false
  clearPreview(); renderError.value = ''; actionError.value = ''; notice.value = ''
  const control = renderControl = new AbortController(), path = endpoint.value, spec = { ...item.spec }
  rendering.value = true
  try {
    // The saved endpoint validates the original manifest AND the prepared figure
    // source fingerprint. Re-rendering the recipe would bypass the latter check.
    const blob = await checkedBlob(`${path}/saved/${encodeURIComponent(item.id)}/export`, 'svg', control)
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    previewUrl.value = URL.createObjectURL(blob); renderedSpec.value = spec; renderedSavedId.value = item.id
  } catch (error) {
    if (!control.signal.aborted) { renderError.value = message(error, '保存图表恢复失败'); failedRestore.value = item }
  } finally { if (!control.signal.aborted) rendering.value = false }
}
async function retryPreview() { if (failedRestore.value) await restore(failedRestore.value); else await renderFigure() }
async function saveFigure() {
  if (readOnly.value || !renderedSpec.value || renderedSavedId.value || saving.value || rendering.value || exporting.value || removing.value || saveUncertain.value) return
  const control = saveControl = new AbortController(), path = endpoint.value, spec = { ...renderedSpec.value }
  saving.value = true; actionError.value = ''; notice.value = ''
  try {
    const item = await apiFetch<SavedFigure>(`${path}/saved`, { method: 'POST', body: spec, signal: control.signal })
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    // A prior list refresh must not overwrite a newly saved item.
    listControl?.abort(); listLoading.value = false
    saved.value = [item, ...saved.value.filter(row => row.id !== item.id)]; selectedId.value = item.id
    notice.value = '当前预览已加入图表清单。'
  } catch (error) {
    if (!control.signal.aborted) { actionError.value = `${message(error, '保存失败')}。请刷新图表清单确认保存状态后再操作。`; saveUncertain.value = true }
  } finally { if (!control.signal.aborted) saving.value = false }
}
async function exportFigure(useSaved = false) {
  const item = selected.value, spec = renderedSpec.value ? { ...renderedSpec.value } : null
  if (readOnly.value || exporting.value || removing.value || (!useSaved && !spec) || (useSaved && (!item || !fingerprintMatches(item)))) return
  const control = exportControl = new AbortController(), path = endpoint.value, format = exportFormat.value
  const savedId = useSaved ? item!.id : renderedSavedId.value
  exporting.value = true; actionError.value = ''; notice.value = ''
  try {
    const blob = await checkedBlob(savedId ? `${path}/saved/${encodeURIComponent(savedId)}/export` : `${path}/render`, format, control, savedId ? undefined : spec!)
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    const label = useSaved ? item!.spec.chart : spec!.chart
    downloadBlob(blob, `CellLens-${label}-${recordId.value.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 64)}.${format}`)
    notice.value = useSaved ? '已导出所选保存图表。' : '已导出当前预览对应的图表。'
  } catch (error) { if (!control.signal.aborted) actionError.value = message(error, '图表导出失败，请重试') }
  finally { if (!control.signal.aborted) exporting.value = false }
}
async function exportReport() {
  if (readOnly.value || !validIdentity.value || !context.value || !saved.value.length || saved.value.length > 20 || exporting.value || saving.value || removing.value || listLoading.value || listError.value || saveUncertain.value) return
  const control = exportControl = new AbortController(), path = endpoint.value, format = reportFormat.value
  exporting.value = true; actionError.value = ''; notice.value = ''
  try {
    const blob = await checkedBlob(`${path}/report`, format, control)
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    downloadBlob(blob, `CellLens-report-${recordId.value.replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 64)}.${format}`)
    notice.value = '已导出完整图表清单报告。'
  } catch (error) { if (!control.signal.aborted) actionError.value = message(error, '整份报告导出失败，请重试') }
  finally { if (!control.signal.aborted) exporting.value = false }
}
function requestRemoval(item: SavedFigure) {
  if (readOnly.value || removing.value || exporting.value || saving.value || rendering.value || listLoading.value) return
  confirmingRemoval.value = item.id
}
async function removeFigure(item: SavedFigure) {
  if (readOnly.value || confirmingRemoval.value !== item.id || removing.value || exporting.value || saving.value || rendering.value || listLoading.value || !saved.value.some(row => row.id === item.id)) return
  const control = removeControl = new AbortController(), path = endpoint.value
  removing.value = item.id; actionError.value = ''; notice.value = ''
  try {
    await apiFetch<null>(`${path}/saved/${encodeURIComponent(item.id)}`, { method: 'DELETE', signal: control.signal })
    if (control.signal.aborted || path !== endpoint.value || readOnly.value) return
    if (renderedSavedId.value === item.id || failedRestore.value?.id === item.id) { clearPreview(); renderError.value = '' }
    saved.value = saved.value.filter(row => row.id !== item.id)
    if (selectedId.value === item.id) selectedId.value = ''
    confirmingRemoval.value = ''
    notice.value = '已移除保存的图表配置，原始分析结果保持不变。'
    await loadSaved()
  } catch (error) { if (!control.signal.aborted) actionError.value = message(error, '移除图表失败，请刷新清单后重试') }
  finally { if (!control.signal.aborted) removing.value = '' }
}
watch(draft, () => {
  if (rendering.value) { renderControl?.abort(); rendering.value = false }
}, { flush: 'sync' })
watch([recordKind, recordId, readOnly], () => { void load() }, { immediate: true, flush: 'sync' })
onBeforeUnmount(() => { abortAll(); clearPreview() })
</script>

<template>
  <div class="figure-workspace national-page">
    <header class="figure-page-heading"><div><span class="eyebrow">FIGURE WORKSPACE</span><h1>图表与报告</h1><p>整理冻结结果中的图表，保留来源与选择条件。</p></div><RouterLink class="btn" :to="readOnly ? '/records' : resultLink">{{ readOnly ? '浏览已发布结果' : '返回研究结果' }} ↗</RouterLink></header>
    <section v-if="readOnly" class="card figure-state"><h2>公开研究展览</h2><p>图表整理在私人工作区内进行。你可以继续浏览已发布的冻结结果。</p><RouterLink class="btn btn-primary" to="/records">浏览已有结果</RouterLink></section>
    <section v-else-if="loadError" class="card figure-state" role="alert"><h2>无法读取研究上下文</h2><p>{{ loadError }}</p><button class="btn" @click="load">重新读取</button></section>
    <section v-else-if="!context" class="card figure-state" role="status">正在读取冻结结果与可用图表…</section>
    <template v-else>
      <div class="figure-context"><div><strong>{{ context.result.background.cell_line }} / {{ context.result.target.perturbation }}</strong><span>{{ recordKind === 'measured' ? '实测研究' : '模型探索' }} · 冻结结果</span></div><details><summary>来源指纹</summary><code>{{ context.result.provenance.manifest_sha256 || '历史结果未提供指纹' }}</code></details></div>
      <div class="figure-layout">
        <main class="figure-main card">
          <div class="figure-types" role="group" aria-label="图表类型"><button v-for="chart in charts" :key="chart.id" :class="{ active: draft.chart === chart.id, unavailable: !context.availability[chart.id] }" :aria-pressed="draft.chart === chart.id" @click="chooseChart(chart.id)"><strong>{{ chart.label }}</strong><small>{{ context.availability[chart.id] ? chart.description : '当前结果不可用' }}</small></button></div>
          <p v-if="!context.availability[draft.chart]" class="figure-unavailable" role="status">{{ reason }} 不会使用模拟数据补齐历史结果。</p>
          <form class="figure-controls" @submit.prevent="renderFigure">
            <label v-if="draft.chart === 'projection'">投影方法<select v-model="draft.embedding"><option value="pca">PCA</option><option value="umap">UMAP</option></select></label>
            <label v-if="draft.chart === 'distribution'" class="gene-field">表达基因<input v-model="draft.gene" list="figure-genes" type="search" placeholder="搜索当前结果中的基因" autocomplete="off" /><datalist id="figure-genes"><option v-for="gene in context.genes" :key="gene" :value="gene" /></datalist></label>
            <label v-if="draft.chart !== 'pathways'">预定义群体<select v-model="draft.group"><option value="all">全部群体</option><option value="control">实测对照</option><option value="observed">扰动实测</option><option v-if="recordKind === 'prediction'" value="predicted">模型预测</option></select></label>
            <template v-if="draft.chart === 'pathways'"><label>变化方向<select v-model="draft.direction"><option value="both">全部方向</option><option value="up">上调</option><option value="down">下调</option></select></label><label>条目数<input v-model.number="draft.limit" type="number" min="1" max="30" step="1" /></label></template>
            <details class="figure-caption-controls"><summary>图题与图注 <span>{{ draft.title || draft.note ? '已填写 · 展开编辑' : '可选 · 展开编辑' }}</span></summary><div>
              <label class="wide">图表标题<input v-model="draft.title" maxlength="120" placeholder="留空使用默认图题" /></label>
              <label class="wide">图注与研究备注<textarea v-model="draft.note" rows="2" maxlength="2000" placeholder="记录本图的发现与解释范围" /></label>
            </div></details>
            <div class="control-footer"><span v-if="draft.gene && !context.genes.includes(draft.gene)" class="field-error">请选择当前结果中已登记的基因。</span><span v-else class="muted">修改设置后应用；保存和导出对应当前预览。</span><button type="submit" class="btn btn-primary" :disabled="!validDraft || rendering || Boolean(removing)">{{ rendering ? '正在生成…' : '应用并预览' }}</button></div>
          </form>
          <div class="figure-preview-heading"><div><h2>{{ renderedSpec?.title || (renderedSpec ? chartTitle(renderedSpec.chart) : '图表预览') }}</h2><span v-if="renderedSpec">{{ chartTitle(renderedSpec.chart) }}<template v-if="renderedSpec.gene"> · {{ renderedSpec.gene }}</template> · {{ renderedSpec.group === 'all' ? '全部群体' : renderedSpec.group === 'control' ? '实测对照' : renderedSpec.group === 'observed' ? '扰动实测' : '模型预测' }}</span></div><span v-if="dirty" class="draft-badge">有未应用修改</span></div>
          <p v-if="dirty" class="draft-explanation">当前预览、保存与导出仍使用上次成功应用的设置。</p>
          <p v-if="renderedSpec?.chart==='pathways'" class="pathway-context">Reactome {{ context.pathways?.resource?.release || '冻结版本' }}<template v-if="context.pathways?.coverage"> · {{ context.pathways.coverage.mapped_background_count?.toLocaleString() }} 个实际背景基因 · {{ context.pathways.coverage.tested_count?.toLocaleString() }} 项检验</template><br>按表达变化选取方向一致的前 5% 候选，双方向共同 BH 校正；这是探索性富集，不代表差异表达显著性。</p>
          <div class="figure-preview" :aria-busy="rendering"><div v-if="rendering" class="preview-placeholder" role="status">正在生成图表…</div><div v-else-if="renderError" class="preview-placeholder" role="alert"><strong>图表暂不可用</strong><p>{{ renderError }}</p><button class="btn" :disabled="!failedRestore && !validDraft" @click="retryPreview">重试预览</button></div><img v-else-if="previewUrl" :src="previewUrl" :alt="renderedSpec?.title || chartTitle(renderedSpec?.chart || 'projection')" /><div v-else class="preview-placeholder">{{ context.availability[draft.chart] ? '选择设置并应用，生成当前图表。' : reason }}</div></div>
          <p v-if="renderedSpec?.note" class="rendered-note">{{ renderedSpec.note }}</p>
          <div class="figure-toolbar"><label>导出格式<select v-model="exportFormat" aria-label="图表导出格式"><option value="svg">SVG · 矢量图</option><option value="png">PNG · 图片</option><option value="pdf">PDF · 图稿</option><option value="csv">CSV · 对应数据</option><option value="html">HTML · 图文报告</option><option value="zip">ZIP · 研究图表包</option></select></label><button class="btn" :disabled="!renderedSpec || rendering || exporting || Boolean(removing)" @click="exportFigure()">{{ exporting ? '正在导出…' : '导出当前预览' }}</button><button class="btn btn-primary" :disabled="!renderedSpec || Boolean(renderedSavedId) || rendering || saving || exporting || Boolean(removing) || saveUncertain" @click="saveFigure">{{ saving ? '正在保存…' : renderedSavedId ? '已在图表清单' : '加入图表清单' }}</button></div>
          <p v-if="actionError" class="notice notice-danger" role="alert">{{ actionError }} <button v-if="saveUncertain" class="btn btn-sm" :disabled="listLoading" @click="loadSaved">刷新清单确认</button></p><p v-if="notice" class="figure-success" role="status">{{ notice }}</p>
        </main>
        <aside class="saved-figures card" aria-labelledby="saved-figures-title"><header><div><span class="eyebrow">SAVED FIGURES</span><h2 id="saved-figures-title">图表清单 <span>{{ saved.length }}</span></h2></div><button class="source-button" :disabled="listLoading || saving || Boolean(removing)" @click="loadSaved">{{ listLoading ? '读取中…' : '刷新' }}</button></header><p class="saved-intro">保存已应用的设置与结果指纹，恢复后可继续整理。</p><p v-if="listError" class="notice notice-danger" role="alert">{{ listError }} <button class="source-button" @click="loadSaved">重试</button></p><p v-else-if="!saved.length" class="saved-empty">尚未保存图表。<br />完成预览后加入清单。</p><ol v-else class="saved-list"><li v-for="(item, index) in saved" :key="item.id" :class="{ selected: selectedId === item.id }"><label class="saved-select"><input v-model="selectedId" type="radio" name="saved-figure" :value="item.id" /><span class="figure-number">{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ item.spec.title || chartTitle(item.spec.chart) }}</strong></label><p>{{ chartTitle(item.spec.chart) }}<template v-if="item.spec.gene"> · {{ item.spec.gene }}</template></p><small>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</small><span v-if="!fingerprintMatches(item)" class="saved-mismatch">来源指纹不同，无法恢复或导出</span><button class="source-button" :disabled="!fingerprintMatches(item) || saving || Boolean(removing)" @click="restore(item)">恢复设置与预览 ↗</button><div class="saved-remove"><template v-if="confirmingRemoval === item.id"><p>仅移除这张保存图表，保留原始分析。</p><button class="source-button remove-confirm" :disabled="Boolean(removing) || exporting || saving || rendering || listLoading" @click="removeFigure(item)">{{ removing === item.id ? '正在移除…' : '确认移除' }}</button><button class="source-button" :disabled="Boolean(removing)" @click="confirmingRemoval = ''">取消</button></template><button v-else class="source-button" :disabled="Boolean(removing) || exporting || saving || rendering || listLoading" :aria-label="`移除图表 ${item.spec.title || chartTitle(item.spec.chart)}`" @click="requestRemoval(item)">移除图表</button></div></li></ol><div class="saved-export"><button class="btn" :disabled="!selected || !fingerprintMatches(selected) || exporting || Boolean(removing)" @click="exportFigure(true)">导出所选图表 · {{ exportFormat.toUpperCase() }}</button><small>导出使用所选保存版本，不受左侧未保存修改影响。</small><div class="report-export"><label>整份报告格式<select v-model="reportFormat" aria-label="整份报告格式" :disabled="exporting"><option value="html">HTML · 图文报告</option><option value="zip">ZIP · 图表、数据与配置</option></select></label><button class="btn btn-primary" :disabled="!saved.length || saved.length > 20 || exporting || saving || Boolean(removing) || listLoading || Boolean(listError) || saveUncertain" @click="exportReport">{{ exporting ? '正在导出…' : '导出整份报告' }}</button><small>汇总全部已保存图表、完整图注和对应数据；左侧草稿不计入报告。</small><small v-if="saved.length > 20" class="field-error">整份报告最多包含 20 张图表，请先移除不需要的保存图表。</small></div></div></aside>
      </div>
      <p class="figure-boundary">图表引用原始冻结结果，不重算正式统计。投影表示表达空间分布，不是真实空间或细胞形态。不同历史结果的可用图表以实际保存数据为准。</p>
    </template>
  </div>
</template>

<style scoped>
.pathway-context{font-size:11px;line-height:1.8;color:var(--muted);padding:11px 14px;border-left:2px solid var(--primary);background:var(--surface-soft);margin:0 0 16px}
.figure-workspace{max-width:1500px;margin:0 auto}.figure-page-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:27px}.eyebrow{font-size:10px;letter-spacing:1.8px;color:var(--primary)}.figure-page-heading h1{font-size:30px;font-weight:500;margin:10px 0}.figure-page-heading p{color:var(--muted);font-size:13px;line-height:1.8;margin:0}.figure-context{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:17px 22px;background:var(--primary-weak);border:1px solid var(--border-strong);border-radius:10px;margin-bottom:20px;font-size:13px}.figure-context strong{font-weight:550}.figure-context span{margin-left:17px;color:var(--muted);font-size:12px}.figure-context summary{cursor:pointer;color:var(--primary);font-size:11px}.figure-context code{display:block;max-width:300px;overflow-wrap:anywhere;font-size:10px;line-height:1.7;margin-top:9px}.figure-layout{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:20px;align-items:start}.figure-main{padding:23px;min-width:0;border-radius:12px}.figure-types{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:20px}.figure-types button{font:inherit;text-align:left;padding:13px 14px;border:1px solid var(--border);border-radius:7px;background:var(--card);color:var(--ink);cursor:pointer}.figure-types button.active{border-color:var(--primary);background:var(--primary-weak)}.figure-types strong{display:block;font-weight:550;font-size:13px}.figure-types small{display:block;font-size:10px;color:var(--muted);margin-top:7px;line-height:1.6}.figure-types .unavailable small{font-style:italic}.figure-controls{display:flex;flex-wrap:wrap;gap:13px;padding:18px;background:var(--surface-soft);border:1px solid var(--border);border-radius:8px}.figure-controls label{display:flex;flex:1;flex-direction:column;gap:8px;min-width:110px;color:var(--muted);font-size:11px}.figure-controls .gene-field{flex:1.6;min-width:170px}.figure-controls label.wide{flex-basis:100%}input,select,textarea{min-width:0;width:100%;border:1px solid var(--border);background:var(--field-bg);color:var(--ink);padding:9px 10px;border-radius:5px;font:inherit;font-size:12px}textarea{resize:vertical;line-height:1.8}.control-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-basis:100%;font-size:11px;line-height:1.7}.control-footer .btn{white-space:nowrap}.field-error{color:var(--danger)}.figure-preview-heading{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:24px 0 15px}.figure-preview-heading h2{font-size:17px;font-weight:550;line-height:1.6;margin:0;overflow-wrap:anywhere}.figure-preview-heading span{font-size:11px;color:var(--muted);display:block;margin-top:6px}.figure-preview-heading .draft-badge{white-space:nowrap;padding:5px 8px;border:1px solid var(--border);border-radius:5px;color:var(--primary)}.draft-explanation{font-size:11px;color:var(--muted);line-height:1.8;margin-top:-7px}.figure-preview{display:flex;align-items:center;justify-content:center;min-height:350px;background:#fff;border:1px solid var(--border);border-radius:8px;overflow:hidden}.figure-preview img{display:block;max-width:100%;height:auto;width:100%}.preview-placeholder{padding:50px 25px;text-align:center;font-size:13px;color:#63756c;line-height:1.9;max-width:550px}.preview-placeholder strong{font-weight:550;color:#234b39}.rendered-note{white-space:pre-wrap;overflow-wrap:anywhere;color:var(--muted);font-size:12px;line-height:1.9;padding:13px 0;margin:0}.figure-toolbar{display:flex;align-items:end;gap:9px;flex-wrap:wrap;margin-top:17px}.figure-toolbar label{display:flex;flex-direction:column;gap:7px;min-width:155px;font-size:11px;color:var(--muted);margin-right:auto}.figure-toolbar select{font-size:11px}.figure-toolbar .btn{font-size:12px;min-height:36px}.saved-figures{padding:20px;border-radius:12px;min-width:0}.saved-figures header{display:flex;align-items:center;justify-content:space-between;gap:12px}.saved-figures h2{font-size:18px;font-weight:550;margin:9px 0 0}.saved-figures h2 span{font:18px Georgia,serif;color:var(--primary);margin-left:7px}.source-button{border:0;background:none;color:var(--primary);font:inherit;font-size:11px;cursor:pointer;padding:0;line-height:1.8}.source-button:disabled{opacity:.45;cursor:default}.saved-intro,.saved-empty{font-size:11px;color:var(--muted);line-height:1.9}.saved-intro{margin:17px 0 20px}.saved-empty{padding:32px 10px;text-align:center;border:1px dashed var(--border);border-radius:7px}.saved-list{list-style:none;padding:0;margin:0;display:grid;gap:11px}.saved-list li{padding:14px;border:1px solid var(--border);border-radius:8px;min-width:0}.saved-list li.selected{border-color:var(--primary);background:var(--primary-weak)}.saved-select{display:flex;align-items:center;gap:8px;cursor:pointer;min-width:0}.saved-select input{width:13px;height:13px;accent-color:var(--primary);flex:none}.saved-select strong{font-size:12px;font-weight:550;overflow-wrap:anywhere;min-width:0}.figure-number{font:12px Georgia,serif;color:var(--muted)}.saved-list li p{font-size:11px;color:var(--muted);margin:11px 0 7px}.saved-list li small{font-size:10px;color:var(--muted);display:block;line-height:1.7}.saved-list .source-button{margin-top:12px}.saved-mismatch{display:block;color:var(--danger);font-size:10px;line-height:1.7;margin-top:7px}.saved-export{border-top:1px solid var(--border);margin-top:20px;padding-top:18px}.saved-export .btn{width:100%;font-size:11px}.saved-export small{display:block;font-size:10px;line-height:1.8;color:var(--muted);margin-top:10px}.figure-boundary{font-size:11px;color:var(--muted);line-height:1.9;margin:20px 0}.figure-unavailable{background:var(--surface-soft);padding:12px 15px;border-left:3px solid var(--gold);font-size:12px;color:var(--muted);line-height:1.8}.figure-success{font-size:12px;color:var(--primary);margin:15px 0 0}.figure-state{padding:45px 25px;line-height:1.9;text-align:center;font-size:13px;color:var(--muted)}.figure-state h2{color:var(--ink);font-size:20px;font-weight:500}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
@media(max-width:1150px){.figure-layout{grid-template-columns:minmax(0,1fr) 250px}.figure-main{padding:18px}.saved-figures{padding:17px}.figure-types{gap:7px}.figure-types button{padding:11px}.figure-types small{font-size:10px}.figure-toolbar .btn{font-size:11px}}
@media(max-width:900px){.figure-layout{grid-template-columns:1fr}.saved-list{grid-template-columns:repeat(2,minmax(0,1fr))}.figure-context{flex-wrap:wrap}.figure-context span{display:block;margin:7px 0 0}}
@media(max-width:550px){.figure-page-heading{align-items:start;flex-wrap:wrap;gap:13px}.figure-page-heading h1{font-size:26px}.figure-context{padding:15px}.figure-context code{max-width:100%}.figure-main{padding:14px}.figure-types{gap:5px}.figure-types button{padding:11px 8px}.figure-types strong{font-size:12px}.figure-types small{display:none}.figure-controls{padding:13px}.figure-controls label,.figure-controls .gene-field{min-width:100%}.control-footer{align-items:start;flex-direction:column}.control-footer .btn{width:100%}.figure-preview{min-height:240px}.figure-toolbar{gap:10px}.figure-toolbar label{width:100%}.figure-toolbar .btn{flex:1}.saved-list{grid-template-columns:1fr}.figure-preview-heading{align-items:start}.figure-preview-heading .draft-badge{font-size:10px}.figure-boundary{font-size:10px}}
</style>
<style scoped>.figure-caption-controls{flex-basis:100%;border-top:1px solid var(--border);padding-top:11px}.figure-caption-controls summary{font-size:12px;color:var(--primary);cursor:pointer;line-height:1.8}.figure-caption-controls summary span{font-size:10px;margin-left:8px;color:var(--muted)}.figure-caption-controls>div{display:grid;gap:12px;padding-top:13px}</style>
<style scoped>.report-export{border-top:1px solid var(--border);padding-top:16px;margin-top:16px}.report-export label{display:grid;gap:7px;font-size:11px;color:var(--muted);margin-bottom:10px}.report-export select{font-size:11px}</style>
<style scoped>.saved-remove{margin-top:9px;border-top:1px solid var(--border);padding-top:8px}.saved-remove .source-button{margin-top:0;margin-right:13px;color:var(--muted)}.saved-remove .remove-confirm{color:var(--danger)}.saved-remove p{font-size:10px!important;line-height:1.7;margin:0 0 8px!important}</style>
