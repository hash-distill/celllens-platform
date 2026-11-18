<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { accessSession } from '../stores/access'
import { dataCatalogApi, type Availability, type CatalogPair, type CatalogResponse } from '../api/dataCatalog'
import TablePager from '../components/TablePager.vue'
import UiIcon from '../components/UiIcon.vue'
import MethodsPageHeader from '../components/MethodsPageHeader.vue'
import { downloadBlob } from '../utils/csv'

type CatalogMode = 'measured' | 'prediction' | 'all'
const route = useRoute()
const allContexts = ['HepG2', 'Jurkat', 'K562', 'RPE1']
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const data = ref<CatalogResponse | null>(null), loading = ref(false), error = ref('')
const contexts = computed(() => readOnly.value ? data.value?.summary.contexts.map(row => row.cell_line) ?? [] : allContexts)
const sourceTotalCells = computed(() => {
  const rows = data.value?.summary.contexts
  return rows?.length && rows.every(row => typeof row.source_total_cells === 'number')
    ? rows.reduce((total, row) => total + (row.source_total_cells ?? 0), 0) : null
})
const cellLine = ref(allContexts.includes(String(route.query.cell_line)) ? String(route.query.cell_line) : '')
const term = ref(typeof route.query.perturbation === 'string' ? route.query.perturbation : '')
const mode = ref<CatalogMode>('measured')
const availability = ref<Availability>('all'), support = ref('all')
const page = ref(1), pageSize = ref(10)
const downloading = ref(false), downloadError = ref('')
const detail = ref<CatalogPair | null>(null), sourceDialog = ref<HTMLDialogElement | null>(null)
let controller: AbortController | undefined, downloadController: AbortController | undefined
let timer: ReturnType<typeof setTimeout> | undefined
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / pageSize.value)))
const modeDescription = computed(() => readOnly.value
  ? '仅展示已发布案例涉及的研究条件；统计与入口均限定在公开白名单内。'
  : mode.value === 'measured'
    ? '从当前固定来源中确有实测细胞的条件开始。进入工作台后核对输入，必要时按需准备数据。'
    : mode.value === 'prediction'
      ? 'STATE · 当前模型词表支持的背景与目标。支持表示能够编码条件，不代表预测准确性或泛化效果已验证。'
      : '检索完整背景—基因查询空间，包括当前来源未收录和来源状态未知的组合。组合数不等于实测实验数。')
function filters() {
  return { cell_line: cellLine.value || undefined, query: term.value.trim(),
    availability: readOnly.value ? availability.value : mode.value === 'measured' ? 'measured' as const : availability.value,
    model_supported: !readOnly.value && mode.value === 'prediction' ? true : support.value === 'all' ? undefined : support.value === 'yes' }
}
async function load() {
  clearTimeout(timer)
  controller?.abort()
  const current = controller = new AbortController()
  loading.value = true; error.value = ''
  try {
    const result = await dataCatalogApi.query({ ...filters(), limit: pageSize.value, offset: (page.value - 1) * pageSize.value }, current.signal)
    if (current.signal.aborted) return
    const last = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > last) { page.value = last; return }
    data.value = result
  } catch (reason) {
    if (!current.signal.aborted) { data.value = null; error.value = reason instanceof Error ? reason.message : '数据目录读取失败' }
  } finally { if (!current.signal.aborted) loading.value = false }
}
function invalidate() {
  controller?.abort(); downloadController?.abort(); clearTimeout(timer)
  loading.value = true; downloading.value = false; downloadError.value = ''; error.value = ''
  sourceDialog.value?.close(); detail.value = null
}
watch([cellLine, term, mode, availability, support], () => {
  invalidate(); page.value = 1
}, { flush: 'sync' })
watch([cellLine, term, mode, availability, support, page, pageSize], () => {
  invalidate()
  timer = setTimeout(() => { void load() }, 180)
})
watch(readOnly, () => {
  invalidate(); data.value = null; cellLine.value = ''; term.value = ''; mode.value = 'measured'
  availability.value = 'all'; support.value = 'all'; page.value = 1
  void load()
}, { flush: 'sync' })
void load()
onBeforeUnmount(() => { clearTimeout(timer); controller?.abort(); downloadController?.abort(); sourceDialog.value?.close() })
function destination(row: CatalogPair, path: string) {
  return { path: '/research', query: { type: path === '/measured' ? 'measured' : 'prediction', cell_line: row.cell_line, perturbation: row.perturbation } }
}
function chooseMode(value: CatalogMode) {
  mode.value = value; availability.value = 'all'; support.value = 'all'
}
function resetFilters() {
  cellLine.value = ''; term.value = ''; availability.value = 'all'; support.value = 'all'; page.value = 1
}
function showMissing() {
  mode.value = 'all'; availability.value = 'missing'; support.value = 'yes'
}
function chooseContext(value: string) { cellLine.value = cellLine.value === value ? '' : value }
watch(() => [route.query.cell_line, route.query.perturbation], ([context, perturbation]) => {
  cellLine.value = typeof context === 'string' && allContexts.includes(context) ? context : ''
  term.value = typeof perturbation === 'string' ? perturbation : ''
})
function splitName(value: string) {
  return value === 'test' ? '上游 test 候选' : value === 'val' ? '上游 val 候选' : value === 'unknown' ? '未核验' : '未声明留出'
}
async function openSource(row: CatalogPair | null = null) {
  detail.value = row; await nextTick(); sourceDialog.value?.showModal()
}
async function download() {
  if (readOnly.value || loading.value || !data.value || error.value || downloading.value) return
  downloading.value = true; downloadError.value = ''
  const current = downloadController = new AbortController()
  try {
    const result = await dataCatalogApi.download(filters(), current.signal)
    if (!current.signal.aborted && !readOnly.value) downloadBlob(result.blob, result.filename)
  } catch (reason) {
    if (!current.signal.aborted) downloadError.value = reason instanceof Error ? reason.message : '目录下载失败，请重试'
  } finally { if (!current.signal.aborted) downloading.value = false }
}
</script>

<template>
  <div class="data-catalog-page national-page">
    <MethodsPageHeader eyebrow="DATA ATLAS / RESEARCH CONDITIONS" :index="readOnly ? undefined : '01'" :title="readOnly ? '案例数据目录' : '数据与扰动'" :description="readOnly ? '从公开案例中的真实条件，追溯冻结结果与数据来源。' : '从真实观测开始，选择研究条件，核对来源并进入分析。'">
      <RouterLink class="btn btn-primary" :to="readOnly ? '/records?status=completed' : '/research'">{{ readOnly ? '浏览案例' : '新建研究' }} <UiIcon name="arrow" :size="15" /></RouterLink>
    </MethodsPageHeader>

    <section v-if="data" class="catalog-source" aria-label="当前已登记来源">
      <div class="catalog-source-intro"><span class="eyebrow">{{ readOnly ? 'PUBLIC CASES' : 'REGISTERED SOURCE' }}</span><h2>{{ readOnly ? '公开案例 · 冻结结果子集' : 'Replogle 基因扰动研究' }}</h2><p>{{ readOnly ? '仅包含已发布背景与扰动，不代表完整源覆盖。' : 'State-Replogle-Filtered · 基因扰动 RNA 数据' }}</p><button class="source-link" @click="openSource()">版本与来源详情 <span aria-hidden="true">↗</span></button></div>
      <dl class="source-counts"><div><dt>{{ readOnly ? '案例中的实测组合' : '有实测记录的条件' }}</dt><dd>{{ data.source_verified ? data.summary.measured_pairs?.toLocaleString() : '未知' }}</dd></div><div><dt>{{ readOnly ? '案例涉及背景' : '已登记细胞背景' }}</dt><dd>{{ data.summary.contexts.length }}</dd></div><div><dt>{{ readOnly ? '已发布案例组合' : '本源细胞 · 含对照' }}</dt><dd>{{ readOnly ? data.summary.pairs?.toLocaleString() : sourceTotalCells?.toLocaleString() ?? '未知' }}</dd></div></dl>
    </section>

    <section class="card catalog-table-card" id="coverage-lookup" aria-labelledby="coverage-lookup-title">
      <div class="catalog-section-heading"><div><span class="eyebrow">FIND YOUR DATA</span><h2 id="coverage-lookup-title">{{ readOnly ? '查询案例条件' : '查询研究组合' }}</h2></div><span class="catalog-scope">{{ readOnly ? '公开白名单' : '固定版本 · 基因扰动' }}</span></div>
      <div v-if="!readOnly" class="catalog-modes" role="group" aria-label="目录模式"><button :class="{ active: mode === 'measured' }" :aria-pressed="mode === 'measured'" @click="chooseMode('measured')">实测研究</button><button :class="{ active: mode === 'prediction' }" :aria-pressed="mode === 'prediction'" @click="chooseMode('prediction')">模型探索</button><button :class="{ active: mode === 'all' }" :aria-pressed="mode === 'all'" @click="chooseMode('all')">完整目录</button></div>
      <p class="catalog-mode-description">{{ modeDescription }}</p>
      <RouterLink v-if="!readOnly && mode === 'measured'" class="catalog-datasets-link" to="/datasets">药物扰动数据 <span>浏览已登记的药物研究与条件 ↗</span></RouterLink>
      <p v-if="data && !data.source_verified" class="notice notice-warning" role="status">源索引缺失或核验未通过：实测状态未知，不能按零细胞判断。<button v-if="!readOnly" class="source-link" @click="chooseMode('all')">查看完整目录</button></p>
      <div v-if="data?.summary.contexts.length" class="context-filters" role="group" aria-label="细胞背景与覆盖"><button :class="{ active: !cellLine }" :aria-pressed="!cellLine" @click="cellLine = ''">全部背景</button><button v-for="context in data.summary.contexts" :key="context.cell_line" :class="{ active: cellLine === context.cell_line }" :aria-pressed="cellLine === context.cell_line" @click="chooseContext(context.cell_line)">{{ context.cell_line }} <span>{{ data.source_verified ? context.measured_pairs?.toLocaleString() : '未知' }}</span></button><small>数字为有实测记录的条件数</small></div>
      <form class="catalog-filters" @submit.prevent="load">
        <label class="catalog-search">搜索扰动基因<input v-model="term" type="search" maxlength="64" placeholder="输入目标基因，如 ALDOA" aria-label="搜索扰动基因" /></label>
        <label>细胞背景<select v-model="cellLine" aria-label="数据目录细胞背景"><option value="">{{ readOnly ? '全部案例背景' : '全部背景' }}</option><option v-for="context in contexts" :key="context">{{ context }}</option></select></label>
        <label v-if="readOnly || mode !== 'measured'">实测状态<select v-model="availability" aria-label="实测状态"><option value="all">全部状态</option><option value="measured">本源有实测</option><option value="missing">本源无记录</option><option value="unknown">源状态未知</option></select></label>
        <label v-if="readOnly || mode === 'all'">{{ readOnly ? '冻结模型结果' : '模型词表' }}<select v-model="support" aria-label="模型词表支持"><option value="all">全部</option><option value="yes">{{ readOnly ? '已发布' : '支持' }}</option><option value="no">{{ readOnly ? '未发布' : '不支持' }}</option></select></label>
        <div class="filter-actions"><button class="btn btn-primary" type="submit" :disabled="loading">查询</button><button class="btn" type="button" @click="resetFilters">重置</button></div>
      </form>
      <div class="catalog-results-bar"><span role="status">{{ loading ? '正在读取研究条件…' : error ? '查询暂不可用' : data ? `匹配 ${data.total.toLocaleString()} 个条件` : '尚未读取目录' }}</span><button v-if="!readOnly" class="btn btn-sm" :disabled="downloading || !data || !!error || loading" @click="download">{{ downloading ? '正在导出…' : '导出当前筛选 CSV' }}</button></div>
      <p v-if="downloadError" class="notice notice-danger" role="alert">{{ downloadError }} <button class="btn btn-sm" @click="download">重试导出</button></p>
      <div v-if="error" class="catalog-empty" role="alert"><strong>目录读取失败</strong><p>{{ error }}</p><p>请重新读取目录后继续查询。</p><button class="btn" @click="load">重试</button></div>
      <div v-else-if="loading" class="catalog-loading" role="status" aria-live="polite"><span class="loading-dot"></span> 正在核对当前筛选…</div>
      <template v-else-if="data">
        <div v-if="data.items.length" class="catalog-scroll"><table class="table catalog-pairs"><thead><tr><th>研究条件</th><th>细胞背景</th><th>实测细胞</th><th>{{ readOnly ? '已发布结果' : '可用分析' }}</th><th>操作</th></tr></thead><tbody><tr v-for="row in data.items" :key="`${row.cell_line}-${row.perturbation}`"><td data-label="研究条件"><strong class="mono">{{ row.perturbation }}</strong><small>基因扰动</small></td><td data-label="细胞背景">{{ row.cell_line }}</td><td data-label="实测细胞"><span :class="{ 'catalog-measured': row.source_status === 'measured' }">{{ row.source_status === 'unknown' ? '状态未知' : row.source_status === 'not_in_source' ? '本源未收录' : row.source_cell_count?.toLocaleString() }}</span></td><td data-label="可用分析"><template v-if="readOnly"><span>{{ row.model_supported ? '含冻结模型结果' : '查看冻结案例' }}</span></template><template v-else><span v-if="row.source_status === 'measured'" class="analysis-tag">实测分析</span><span v-if="row.model_supported" class="analysis-tag secondary">模型探索</span><span v-if="row.source_status !== 'measured' && !row.model_supported" class="muted">需核对来源</span></template></td><td class="catalog-actions" data-label="操作"><RouterLink v-if="readOnly" class="btn btn-sm" :to="{ path: '/records', query: { q: row.perturbation } }">浏览相关案例</RouterLink><template v-else><RouterLink v-if="row.recommended_action === 'measured' && mode !== 'prediction'" class="btn btn-sm btn-primary" :to="destination(row, '/measured')">核对并分析</RouterLink><RouterLink v-else-if="row.model_supported && row.source_status !== 'unknown'" class="btn btn-sm btn-primary" :to="destination(row, '/workbench')">探索预测</RouterLink><span v-else class="muted">先核验来源</span></template><button class="source-link" :aria-label="`查看 ${row.cell_line} ${row.perturbation} 来源`" @click="openSource(row)">来源详情</button></td></tr></tbody></table></div>
        <div v-else class="catalog-empty"><strong>没有匹配的组合</strong><p>{{ readOnly ? '请调整筛选；未列出的条件不代表源数据缺失。' : mode === 'measured' ? '当前固定来源中未找到匹配的实测条件，可调整筛选或查看完整目录。' : '请调整基因、背景或实测状态后重试。' }}</p><div><button class="btn" @click="resetFilters">重置筛选</button><button v-if="!readOnly && mode !== 'all'" class="btn" @click="chooseMode('all')">在完整目录中查询</button><RouterLink v-if="!readOnly" class="btn" to="/research?type=import">使用自有 H5AD</RouterLink></div></div>
        <TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="data.total" />
      </template>
      <div class="catalog-table-note"><span>{{ readOnly ? '白名单中的案例条件不等于完整源覆盖。' : '实测细胞数来自固定源索引；本地准备情况请查看来源详情。' }}</span><button v-if="!readOnly" class="source-link" @click="showMissing">查找模型支持但本源未收录的条件 ↗</button></div>
    </section>
    <nav v-if="!readOnly" class="atlas-next" aria-label="继续了解数据图谱"><RouterLink to="/methods/backgrounds">细胞与样本 <span>对照与表达面板 ↗</span></RouterLink><RouterLink to="/methods/models">模型与方法 <span>适用范围与证据 ↗</span></RouterLink><RouterLink to="/methods/coverage">代谢覆盖 <span>基因与功能任务 ↗</span></RouterLink></nav>
    <p class="catalog-boundary">{{ readOnly ? '公开目录不提供完整源细胞总数、私有下载状态或全库 CSV。案例数据以冻结记录为准。' : '“本源未收录”仅指当前固定 filtered 版本，不代表其他研究中没有实测。模型词表支持不等于预测效果已验证。' }}</p>

    <dialog ref="sourceDialog" class="catalog-dialog" aria-labelledby="catalog-source-title" @close="detail = null">
      <header><div><span class="eyebrow">SOURCE & PROVENANCE</span><h2 id="catalog-source-title">{{ detail ? `${detail.cell_line} / ${detail.perturbation}` : '数据版本与来源' }}</h2></div><button class="btn btn-sm" autofocus @click="sourceDialog?.close()" aria-label="关闭来源详情">关闭 ×</button></header>
      <div v-if="data" class="catalog-dialog-body">
        <template v-if="detail"><h3>研究条件</h3><dl class="source-details"><div><dt>本源实测细胞</dt><dd>{{ detail.source_status === 'unknown' ? '未知，不能按零细胞判断' : detail.source_status === 'not_in_source' ? '当前固定源未收录' : detail.source_cell_count?.toLocaleString() }}</dd></div><div v-if="!readOnly"><dt>本地准备情况</dt><dd>{{ detail.local_verified ? `已核验 ${detail.local_measured_cells.toLocaleString()} 个扰动细胞` : '尚未下载或未通过本地核验；来源有记录时，可进入工作台核对并按需准备。' }}</dd></div><div><dt>{{ readOnly ? '冻结模型结果' : '模型词表支持' }}</dt><dd>{{ detail.model_supported ? (readOnly ? '已发布' : '支持当前背景与目标编码') : (readOnly ? '未发布' : '不支持') }}</dd></div><div><dt>上游划分声明</dt><dd>{{ splitName(detail.official_split) }}</dd></div></dl><p class="source-explanation">上游 test / val 仅为公开配置中的候选声明。本项目尚未独立核实 checkpoint 训练排除与泛化效果；匹配实测对照不等于独立留出验证。</p></template>
        <h3>{{ readOnly ? '案例引用的来源' : '固定数据版本' }}</h3><dl class="source-details"><div><dt>来源仓库</dt><dd>{{ data.source.repo }}</dd></div><div><dt>固定版本</dt><dd class="mono">{{ data.source.revision }}</dd></div><div><dt>目录范围</dt><dd>{{ data.source.scope }}</dd></div><div><dt>源索引核验</dt><dd>{{ data.source_verified ? '已通过' : '未通过或缺失' }}</dd></div></dl>
        <p class="source-explanation">本页来源接口未提供论文 DOI 与许可登记字段，请沿固定来源核对原研究及使用条款。{{ readOnly ? '案例细胞数以冻结结果为准。' : '源细胞数与本地缓存量不同；本地已核验也不等于当前运行环境已经就绪。' }}</p>
        <a class="btn" :href="data.source.url" target="_blank" rel="noopener">查看固定公开来源 ↗</a>
        <template v-if="!readOnly && !detail"><h3>背景与来源统计</h3><p class="source-explanation">当前本地已核验 {{ data.summary.local_verified_pairs }} 个组合。该数量表示本地准备情况，不等于公共来源可分析条件总数。</p><div class="source-contexts" v-for="context in data.summary.contexts" :key="context.cell_line"><strong>{{ context.cell_line }}</strong><span>本源细胞 {{ context.source_total_cells?.toLocaleString() ?? '未知' }} · 含对照</span><span>有实测条件 {{ data.source_verified ? context.measured_pairs.toLocaleString() : '未知' }}</span></div><p class="source-explanation">这些是固定源元数据总量，不是当前本地缓存量、分析量或独立样本数。</p></template>
      </div>
    </dialog>
  </div>
</template>

<style scoped>
.data-catalog-page{max-width:1440px;margin:0 auto}.catalog-source{display:grid;grid-template-columns:1fr 1.2fr;gap:30px;align-items:center;padding:23px 27px;margin:0 0 25px;border:1px solid var(--border-strong);border-radius:12px;background:var(--primary-weak)}.catalog-source h2{font-size:20px;font-weight:550;margin:8px 0}.catalog-source p{font-size:12px;color:var(--muted);margin:8px 0 12px}.eyebrow{font-size:10px;letter-spacing:1.5px;color:var(--primary)}.source-link{border:0;background:none;padding:0;font:inherit;font-size:12px;color:var(--primary);cursor:pointer;text-decoration:none;line-height:1.7}.source-link:hover{text-decoration:underline}.source-counts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin:0}.source-counts>div{padding:4px 17px;border-left:1px solid var(--border-strong)}.source-counts dt{font-size:12px;color:var(--muted);line-height:1.7}.source-counts dd{font:32px Georgia,serif;color:var(--primary-strong);margin:10px 0 0;font-variant-numeric:tabular-nums}.catalog-table-card{padding:25px;border-radius:12px;min-width:0}.catalog-section-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:21px}.catalog-section-heading h2{font-size:19px;font-weight:550;margin:7px 0 0}.catalog-scope{font-size:12px;color:var(--muted)}.catalog-modes{display:flex;gap:24px;border-bottom:1px solid var(--border)}.catalog-modes button{position:relative;border:0;background:none;padding:0 4px 13px;font:inherit;font-size:14px;color:var(--muted);cursor:pointer}.catalog-modes button.active{color:var(--primary-strong);font-weight:600}.catalog-modes button.active:after{content:'';position:absolute;height:3px;background:var(--primary);bottom:-1px;left:0;right:0;border-radius:3px}.catalog-mode-description{font-size:13px;line-height:1.8;color:var(--muted);margin:16px 0 20px;max-width:900px}.context-filters{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:17px}.context-filters button{border:1px solid var(--border);border-radius:6px;background:var(--card);padding:7px 11px;font:inherit;font-size:12px;color:var(--ink);cursor:pointer}.context-filters button.active{border-color:var(--primary);background:var(--primary-weak);color:var(--primary-strong)}.context-filters button span{margin-left:8px;color:var(--muted);font-variant-numeric:tabular-nums}.context-filters small{font-size:11px;color:var(--muted);margin-left:5px}.catalog-filters{display:flex;flex-wrap:wrap;align-items:end;gap:12px;padding:16px;background:var(--surface-soft);border:1px solid var(--border);border-radius:8px}.catalog-filters label{display:flex;flex:1;min-width:130px;flex-direction:column;gap:8px;font-size:12px;color:var(--muted)}.catalog-filters .catalog-search{flex:2;min-width:220px}.catalog-filters input,.catalog-filters select{min-width:0;width:100%;min-height:42px;border:1px solid var(--border);border-radius:6px;padding:9px 11px;color:var(--ink);background:var(--field-bg);font:inherit;font-size:13px}.filter-actions{display:flex;gap:7px}.filter-actions .btn{min-height:42px}.catalog-results-bar{display:flex;align-items:center;justify-content:space-between;gap:15px;margin:20px 0 13px;font-size:12px;color:var(--muted)}.catalog-scroll{overflow-x:auto;border:1px solid var(--border);border-radius:8px}.catalog-pairs{margin:0;min-width:650px;width:100%}.catalog-pairs th{white-space:nowrap;background:var(--table-head-bg);font-size:12px}.catalog-pairs td{vertical-align:middle;font-size:13px;padding-top:14px;padding-bottom:14px}.catalog-pairs tr:last-child td{border-bottom:0}.catalog-pairs td small{display:block;font-size:11px;margin-top:5px;color:var(--muted)}.catalog-pairs td strong{font-size:14px}.catalog-measured{color:var(--primary);font-variant-numeric:tabular-nums}.analysis-tag{display:inline-block;padding:4px 7px;border-radius:4px;background:var(--primary-weak);color:var(--primary-strong);font-size:11px;margin:2px 5px 2px 0;white-space:nowrap}.analysis-tag.secondary{background:var(--surface-soft);color:var(--muted)}.catalog-actions .source-link{display:block;margin-top:7px}.catalog-actions{width:150px}.catalog-table-note{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap;font-size:11px;line-height:1.8;color:var(--muted);border-top:1px solid var(--border);margin-top:17px;padding-top:14px}.catalog-table-note .source-link{font-size:11px}.catalog-empty,.catalog-loading{padding:45px 20px;text-align:center;color:var(--muted);font-size:13px;line-height:1.8}.catalog-empty strong{color:var(--ink);font-weight:550}.catalog-empty>div{display:flex;flex-wrap:wrap;gap:9px;justify-content:center;margin-top:16px}.catalog-loading{min-height:230px;display:flex;align-items:center;justify-content:center;gap:10px}.loading-dot{width:7px;height:7px;background:var(--primary);border-radius:50%}.atlas-next{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;padding:25px 0 17px}.atlas-next a{border-left:2px solid var(--border-strong);padding-left:14px;text-decoration:none;color:var(--ink);font-size:13px}.atlas-next span{display:block;font-size:11px;color:var(--muted);margin-top:7px}.catalog-boundary{font-size:11px;line-height:1.9;color:var(--muted);margin:9px 0}.catalog-dialog{width:min(640px,calc(100vw - 30px));max-height:85vh;border:1px solid var(--border-strong);border-radius:12px;background:var(--card);color:var(--ink);padding:0;box-shadow:0 24px 80px #102e2533}.catalog-dialog::backdrop{background:#102e2570}.catalog-dialog header{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:23px 25px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--card);z-index:1}.catalog-dialog h2{font-size:20px;margin:8px 0 0}.catalog-dialog-body{padding:0 25px 25px}.catalog-dialog h3{font-size:14px;margin:25px 0 15px}.source-details{margin:0}.source-details>div{display:grid;grid-template-columns:115px minmax(0,1fr);gap:15px;padding:11px 0;border-bottom:1px solid var(--border);font-size:12px;line-height:1.8}.source-details dt{color:var(--muted)}.source-details dd{margin:0;overflow-wrap:anywhere}.source-explanation{font-size:12px;line-height:1.9;color:var(--muted);padding:12px 14px;background:var(--surface-soft);border-radius:6px;margin:17px 0}.source-contexts{display:flex;gap:15px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding:10px 0;font-size:12px;color:var(--muted)}.source-contexts strong{color:var(--ink);min-width:55px}button:focus-visible,a:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
@media(max-width:1000px){.catalog-source{grid-template-columns:1fr;gap:20px}.source-counts>div:first-child{padding-left:0;border:0}.catalog-filters .catalog-search{min-width:180px}.context-filters small{width:100%;margin:3px 0 0}}
@media(max-width:650px){.catalog-source{padding:20px}.source-counts>div{padding:3px 12px}.source-counts dt{font-size:11px}.source-counts dd{font-size:27px}.catalog-table-card{padding:17px}.catalog-scope{display:none}.catalog-filters{padding:12px}.catalog-filters label,.catalog-filters .catalog-search{min-width:100%;flex:1}.filter-actions{width:100%}.filter-actions .btn{flex:1}.catalog-modes{gap:21px}.catalog-modes button{font-size:13px}.catalog-pairs{min-width:0}.catalog-pairs thead{display:none}.catalog-pairs tbody,.catalog-pairs tr,.catalog-pairs td{display:block}.catalog-pairs tr{padding:14px;border-bottom:1px solid var(--border)}.catalog-pairs tr:last-child{border:0}.catalog-pairs td{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:7px;border:0;padding:6px 0!important;text-align:right;width:auto}.catalog-pairs td:before{content:attr(data-label);font-size:11px;color:var(--muted);margin-right:auto}.catalog-pairs td small{display:none}.catalog-pairs .catalog-actions{justify-content:flex-end;padding-top:12px!important}.catalog-actions .source-link{margin:0 0 0 7px}.catalog-pairs td .analysis-tag{margin:0}.catalog-dialog header{padding:20px}.catalog-dialog-body{padding:0 20px 20px}.source-details>div{grid-template-columns:1fr;gap:4px}.atlas-next{gap:13px}.atlas-next a{padding-left:9px;font-size:12px}.atlas-next span{line-height:1.7;font-size:10px}.catalog-boundary{font-size:11px}}
</style>
<style scoped>.catalog-datasets-link{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:11px 14px;margin:-3px 0 18px;border-left:3px solid var(--primary-soft);background:var(--primary-weak);font-size:13px;color:var(--primary-strong);text-decoration:none}.catalog-datasets-link span{font-size:11px;color:var(--muted)}</style>
