<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { coverageCatalog } from '../api/coverage'
import { coverageSourceKey, type CoverageSource } from '../utils/coverageCache'
import { filterCoverageTasks, summarizeCoverage, type TaskCoverageFilter } from '../utils/coverageSummary'
import type { CoverageCatalogue } from '../types/coverage'
import { downloadBlob, downloadCsv } from '../utils/csv'
import { usePagedRows } from '../utils/pagination'
import TablePager from '../components/TablePager.vue'
import GeneCategoryGuide from '../components/GeneCategoryGuide.vue'
import TaskCoverageOverview from '../components/TaskCoverageOverview.vue'
import MethodsPageHeader from '../components/MethodsPageHeader.vue'
import { buildCoverageExport } from '../utils/exportArtifacts'

const route = useRoute()
const data = shallowRef<CoverageCatalogue | null>(null), loading = ref(false), error = ref('')
const fetchedAt = ref(0), fromCache = ref(false), cancelled = ref(false), elapsed = ref(0)
const sourceError = computed(() => {
  const run = route.query.run, cellLine = route.query.cell_line
  if (run !== undefined && cellLine !== undefined) return '请只选择一种覆盖来源：实验结果或细胞背景。'
  if (run !== undefined && (typeof run !== 'string' || !run.trim())) return '实验来源参数无效，请从实验结果重新打开代谢覆盖。'
  if (cellLine !== undefined && (typeof cellLine !== 'string' || !cellLine.trim())) return '细胞背景参数无效，请重新选择一个背景。'
  return ''
})
const source = computed<CoverageSource>(() => typeof route.query.run === 'string' && route.query.run
  ? {kind:'run', runId:route.query.run} : {kind:'model', cellLine:typeof route.query.cell_line === 'string' ? route.query.cell_line : undefined})
const sourceLabel = computed(() => source.value.kind === 'run' ? '此实验保存的输入面板' : `${source.value.cellLine || '当前模型'}表达面板`)
const readTime = computed(() => fetchedAt.value ? new Date(fetchedAt.value).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '')
const summary = computed(() => data.value ? summarizeCoverage(data.value) : null)
const tab = ref<'genes' | 'tasks'>('genes'), geneQuery = ref(''), taskQuery = ref('')
const taskCoverage = ref<TaskCoverageFilter>('all')
const geneCategory = ref(''), geneId = ref(''), taskId = ref('')
let controller: AbortController | undefined, elapsedTimer: ReturnType<typeof setInterval> | undefined
let requestVersion = 0, displayedKey = ''
const coveredGenes = computed(() => (data.value?.genes ?? []).filter(gene => gene.in_panel))
const coveredTasks = computed(() => (data.value?.tasks ?? []).filter(task => task.coverage_status === 'full'))
const availableTasks = computed(() => (data.value?.tasks ?? []).filter(task => task.n_present_all > 0 && (task.coverage_status === 'full' || task.coverage_status === 'partial')))
const partialTasks = computed(() => availableTasks.value.filter(task => task.coverage_status === 'partial'))
const coveredReactions = computed(() => (data.value?.reactions ?? []).filter(reaction => reaction.n_genes_all > 0 && reaction.n_missing_all === 0))
const categories = computed(() => data.value?.gene_categories ?? [])
const genes = computed(() => coveredGenes.value.filter(gene =>
  (!geneCategory.value || gene.category_ids.includes(geneCategory.value)) &&
  `${gene.symbol} ${gene.approved_symbol} ${gene.hgnc_id ?? ''} ${gene.name_zh ?? ''} ${gene.name_en}`.toLowerCase().includes(geneQuery.value.trim().toLowerCase())))
const tasks = computed(() => filterCoverageTasks(data.value?.tasks ?? [], taskCoverage.value, taskQuery.value))
const {page: genePage, pageSize: geneSize, pages: genePages, visible: geneRows} = usePagedRows(genes)
const {page: taskPage, pageSize: taskSize, pages: taskPages, visible: taskRows} = usePagedRows(tasks)
geneSize.value = 10
taskSize.value = 10
const selectedGene = computed(() => coveredGenes.value.find(gene => gene.symbol === geneId.value))
const selectedTask = computed(() => tasks.value.find(task => task.id === taskId.value))
watch(genes, rows => {
  if (!rows.some(gene => gene.symbol === geneId.value)) geneId.value = rows[0]?.symbol ?? ''
})
watch(tasks, rows => {
  if (!rows.some(task => task.id === taskId.value)) taskId.value = rows[0]?.id ?? ''
})
function taskStatus(status: 'full' | 'partial' | 'absent' | 'unmapped'): string {
  return {full:'完整覆盖', partial:'部分覆盖', absent:'未覆盖', unmapped:'未登记关联基因'}[status]
}
const selectedGeneCategories = computed(() => categories.value.filter(item => selectedGene.value?.category_ids.includes(item.id)))
const returnTarget = computed(() => data.value?.source.kind === 'run' ? {path:`/runs/${encodeURIComponent(data.value.source.id)}`} : {path:'/methods/backgrounds', query:{cell_line:data.value?.source.cell_line}})
function splitGenes(value: string) {return value ? value.split(';').filter(Boolean) : []}
function categoryName(ids: string[]) {return categories.value.filter(item => ids.includes(item.id)).map(item => item.name_zh).join('、')}
function stopTimer() { clearInterval(elapsedTimer); elapsedTimer = undefined }
async function load(force = false) {
  const version = ++requestVersion
  controller?.abort(); stopTimer()
  if (sourceError.value) { data.value = null; fetchedAt.value = 0; displayedKey = ''; error.value = sourceError.value; loading.value = false; cancelled.value = false; return }
  const current = controller = new AbortController(), requestSource = source.value
  const key = coverageSourceKey(requestSource), changedSource = displayedKey !== key
  if (changedSource) { data.value = null; fetchedAt.value = 0; geneId.value = ''; taskId.value = ''; geneCategory.value = ''; geneQuery.value = ''; taskQuery.value = '' }
  error.value = ''; cancelled.value = false; elapsed.value = 0
  const cached = force ? null : coverageCatalog.peek(requestSource)
  fromCache.value = Boolean(cached)
  loading.value = !cached
  if (!cached) elapsedTimer = setInterval(() => { elapsed.value++ }, 1000)
  try {
    const result = cached ?? await coverageCatalog.load(requestSource, current.signal, force)
    if (current.signal.aborted || version !== requestVersion) return
    data.value = result.data; fetchedAt.value = result.fetchedAt; displayedKey = key
    applyTaskLink()
  } catch(reason) {
    if (!current.signal.aborted && version === requestVersion) error.value = reason instanceof Error ? reason.message : '覆盖目录读取失败'
  } finally {
    if (version === requestVersion) { loading.value = false; stopTimer() }
  }
}
function cancelLoad() {
  requestVersion++; controller?.abort(); stopTimer(); loading.value = false; cancelled.value = true
}
function applyTaskLink() {
  const chosen = typeof route.query.task === 'string' ? route.query.task : ''
  if (chosen && data.value?.tasks.some(task => task.id === chosen)) {tab.value = 'tasks'; taskCoverage.value = 'all'; taskQuery.value = ''; void chooseTask(chosen)}
}
watch(() => JSON.stringify([route.query.cell_line, route.query.run]), () => { void load() }, {immediate:true})
watch(() => route.query.task, applyTaskLink)
onBeforeUnmount(() => { requestVersion++; controller?.abort(); stopTimer() })
function openGene(symbol: string) {if (!coveredGenes.value.some(gene => gene.symbol === symbol)) return; tab.value = 'genes'; geneCategory.value = ''; geneQuery.value = symbol; geneId.value = symbol}
function openTask(id: string) {tab.value = 'tasks'; taskCoverage.value = 'all'; taskQuery.value = ''; void chooseTask(id)}
async function chooseTask(id: string) {
  await nextTick()
  const index = tasks.value.findIndex(task => task.id === id)
  if (index < 0) return
  taskPage.value = Math.floor(index / taskSize.value) + 1
  taskId.value = id
}
function exportGenes() {
  if (!data.value) return
  downloadCsv(`${data.value.source.id}-covered-metabolic-genes.csv`, ['symbol','approved_symbol','hgnc_id','name_zh','name_en','category_zh','category_en'], coveredGenes.value.map(gene => [gene.symbol,gene.approved_symbol,gene.hgnc_id ?? '',gene.name_zh ?? '',gene.name_en,categoryName(gene.category_ids),categories.value.filter(item => gene.category_ids.includes(item.id)).map(item => item.name_en).join(';')]))
}
function exportCatalogue() {
  if (!data.value) return
  const output = buildCoverageExport(data.value)
  downloadBlob(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}),`${data.value.source.id}-covered-catalogue.json`)
}
</script>

<template>
  <div class="coverage-page">
    <MethodsPageHeader eyebrow="DATA ATLAS / METABOLIC COVERAGE" index="04" title="代谢覆盖" description="沿着基因、反应与任务，查看表达面板能够支持哪些代谢功能分析。覆盖说明输入范围，不代表预测准确率。" />
    <header v-if="data?.source.kind === 'run'" class="coverage-context">
      <div><strong>输入覆盖范围</strong><p>{{ data.source.title }} · 保存的输入面板</p></div>
      <div class="coverage-context-actions">
        <RouterLink class="btn btn-sm" to="/methods/coverage">查看当前模型范围</RouterLink><RouterLink :to="returnTarget" class="btn btn-sm">返回实验</RouterLink>
      </div>
    </header>
    <div v-if="data" class="coverage-cache-note" role="status"><span>{{ loading ? '正在刷新；下方暂为上次读取的目录。' : error ? '刷新失败；下方保留上次读取的目录。' : cancelled ? '刷新已取消；下方保留上次读取的目录。' : fromCache ? '已复用本次浏览的内存目录' : '目录已读取' }} · {{ readTime }}</span><small>仅内存保存 · 5 分钟内复用</small><button v-if="loading" class="btn btn-sm" @click="cancelLoad">取消刷新</button></div>
    <section v-if="loading && !data" class="card coverage-loading" aria-busy="true" aria-label="代谢覆盖加载状态">
      <div class="coverage-loading-heading"><div><span class="eyebrow">METABOLIC CATALOGUE</span><h2>正在读取代谢覆盖目录</h2><p role="status">{{ sourceLabel }} · 已等待 {{ elapsed }} 秒。{{ elapsed < 8 ? '请求已发出，等待目录响应。' : '服务端仍在准备或传输目录；首次读取可能较慢。' }}</p></div><button class="btn btn-sm" @click="cancelLoad">取消等待</button></div>
      <div class="coverage-loading-stages"><span>基因面板</span><i aria-hidden="true">→</i><span>关联反应</span><i aria-hidden="true">→</i><span>代谢任务</span></div>
      <div class="coverage-skeleton" aria-hidden="true"><div v-for="item in 4" :key="item"><i/><b/><i/></div></div><p class="loading-explanation">首次准备可能需要片刻；可先浏览其他栏目，稍后返回。</p>
    </section>
    <div v-if="error" class="notice notice-danger" role="alert">{{ error }} <button class="btn btn-sm" @click="load(true)">重新读取</button></div>
    <div v-if="cancelled && !data" class="card coverage-loading"><h2>已取消等待</h2><p>尚未显示此来源的覆盖目录；重新读取后继续浏览。</p><button class="btn btn-primary" @click="load()">重新读取目录</button></div>
    <template v-if="data && summary">
      <section class="coverage-metrics" aria-label="当前覆盖数量">
        <div><span>表达面板基因</span><strong>{{ data.panel_gene_count.toLocaleString() }}</strong><p>模型 / 保存结果的实际输入面板</p></div>
        <div><span>已覆盖的代谢基因</span><strong>{{ coveredGenes.length }}</strong><p>知识库登记 {{ summary.totalGenes }} 个 · 未纳入 {{ summary.totalGenes - coveredGenes.length }} 个</p></div>
        <div><span>有覆盖的代谢任务</span><strong>{{ availableTasks.length }}</strong><p>共 {{ summary.totalTasks }} 项 · 完整 {{ coveredTasks.length }} · 部分 {{ partialTasks.length }}</p></div>
        <div><span>完整覆盖的关联反应</span><strong>{{ coveredReactions.length }}</strong><p>共 {{ summary.totalReactions }} 条 · 部分覆盖 {{ summary.reactions.partial }} 条</p></div>
      </section>
      <details class="metabolic-explanation"><summary><strong>表达基因 <i aria-hidden="true">→</i> 关联反应 <i aria-hidden="true">→</i> 代谢任务</strong><span>覆盖不等于活性或实测通量 · 查看说明</span></summary><section class="metabolic-chain" aria-label="基因、反应与代谢任务的关系"><div><span>01 / GENES</span><h2>表达面板提供基因信息</h2><p>{{ coveredGenes.length }} 个代谢关联基因被纳入输入；没有纳入面板不等于不表达。</p></div><i aria-hidden="true">→</i><div><span>02 / REACTIONS</span><h2>基因规则连接关联反应</h2><p>scCellFie 按知识库的基因—反应规则计算支持分数；关联基因缺失会限制解读。</p></div><i aria-hidden="true">→</i><div><span>03 / TASKS</span><h2>关联反应组成代谢任务</h2><p>当前目录共 {{ summary.totalTasks }} 项任务。覆盖是输入范围，不是任务活性、预测准确率或实测代谢通量。</p></div></section></details>
      <nav class="coverage-tabs" aria-label="覆盖目录"><button :class="{active:tab==='genes'}" :aria-pressed="tab==='genes'" @click="tab='genes'">已覆盖代谢基因 <small>{{ coveredGenes.length }}</small></button><button :class="{active:tab==='tasks'}" :aria-pressed="tab==='tasks'" @click="tab='tasks'">全部代谢任务 <small>{{ summary.totalTasks }}</small></button></nav>
      <div v-if="tab==='genes'" class="catalogue-layout">
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>已覆盖的代谢基因</h2><p>按蛋白功能类别浏览，点击基因查看分类与关联任务。</p></div><button class="btn btn-sm" @click="exportGenes">下载已覆盖基因</button></div>
          <div class="catalogue-filters"><label class="gene-class-filter">功能类别<select v-model="geneCategory" aria-label="代谢基因功能分类"><option value="">全部已覆盖类别</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name_zh }} · {{ item.name_en }}（{{ item.count }}）</option></select></label><label class="catalogue-search">搜索基因<input v-model="geneQuery" type="search" placeholder="基因符号、中文、English 或 HGNC ID" /></label></div>
          <GeneCategoryGuide :categories="categories" :selected="geneCategory" />
          <p v-if="!data.classification.available" class="muted small">功能分类注释暂不可用，当前基因列为“暂无分类注释”。</p>
          <p class="catalogue-count" role="status">匹配 {{ genes.length }} 个已覆盖基因</p>
          <div class="table-wrap"><table class="table"><thead><tr><th>基因</th><th>蛋白功能类别</th><th>HGNC 身份</th></tr></thead><tbody><tr v-for="gene in geneRows" :key="gene.symbol" :class="{chosen:geneId===gene.symbol}"><td><button class="catalogue-link mono" @click="geneId=gene.symbol">{{ gene.symbol }}</button><small class="gene-name-zh" lang="zh-CN">{{ gene.name_zh || '暂无中文释名' }}</small><small v-if="gene.approved_symbol!==gene.symbol" class="symbol-alias">现用名 {{ gene.approved_symbol }}</small></td><td><span>{{ categoryName(gene.category_ids) }}</span><small class="class-english" lang="en">{{ categories.filter(item=>gene.category_ids.includes(item.id)).map(item=>item.name_en).join('; ') }}</small></td><td class="mono">{{ gene.hgnc_id || '暂无信息' }}</td></tr></tbody></table></div>
          <p v-if="!genes.length" class="empty-result">没有匹配的已覆盖基因。</p><TablePager v-model:page="genePage" v-model:page-size="geneSize" :pages="genePages" :total="genes.length" />
        </section>
        <aside class="card catalogue-detail" aria-label="基因范围详情"><span class="eyebrow">GENE / FUNCTION CLASS</span><template v-if="selectedGene"><h2>{{ selectedGene.symbol }}</h2><p class="gene-name-zh" lang="zh-CN">{{ selectedGene.name_zh || '暂无中文释名' }}</p><p lang="en">{{ selectedGene.name_en }}</p><p>{{ selectedGene.approved_symbol }} · {{ selectedGene.hgnc_id || '无 HGNC 身份记录' }}</p><strong class="coverage-state covered">已包含在输入面板中</strong><section v-for="item in selectedGeneCategories" :key="item.id" class="gene-class-explanation"><h3>{{ item.name_zh }}</h3><small lang="en">{{ item.name_en }}</small><p>{{ item.description_zh }}</p><p lang="en">{{ item.description_en }}</p></section><h3>关联的代谢任务</h3><button v-for="task in availableTasks.filter(item=>selectedGene?.tasks.includes(item.id))" :key="task.id" class="association-link" @click="openTask(task.id)">{{ task.guide?.name_zh || task.label }} ↗</button><p v-if="!availableTasks.some(item=>selectedGene?.tasks.includes(item.id))">当前知识库暂无与此基因关联且已有输入覆盖的任务。</p><a v-if="selectedGene.hgnc_id" :href="'https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/'+selectedGene.hgnc_id" target="_blank" rel="noopener">HGNC 基因信息 ↗</a></template><template v-else><h2>从基因认识功能类别</h2><p>点击基因名称，查看类别的中英文说明及知识库中的关联任务。</p></template></aside>
      </div>
      <div v-else class="catalogue-layout">
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>代谢任务与关联基因</h2><p>浏览知识库全部任务，区分输入覆盖与尚未登记的关联关系。</p></div></div>
          <p class="scope-explanation">关联基因以当前 scCellFie 知识库的反应规则为依据，覆盖率表示这些基因在输入中的可用比例；相关生物过程涉及的基因不限于此。</p>
          <div class="task-status-overview" aria-label="全部任务状态统计"><button v-for="status in (['full','partial','absent','unmapped'] as const)" :key="status" :class="{active:taskCoverage===status}" @click="taskCoverage=status"><span>{{ taskStatus(status) }}</span><strong>{{ summary.tasks[status] }}</strong></button></div>
          <label class="task-search-label">任务覆盖范围<select v-model="taskCoverage" aria-label="任务覆盖范围"><option value="all">全部知识库任务（{{ summary.totalTasks }}）</option><option value="covered">有输入覆盖的任务（{{ availableTasks.length }}）</option><option value="full">完整覆盖（{{ coveredTasks.length }}）</option><option value="partial">部分覆盖（{{ partialTasks.length }}）</option><option value="absent">未覆盖（{{ summary.tasks.absent }}）</option><option value="unmapped">未登记关联基因（{{ summary.tasks.unmapped }}）</option></select></label>
          <label class="task-search-label">搜索任务<input v-model="taskQuery" type="search" placeholder="中文、English 或关联基因" /></label><p class="catalogue-count" role="status">匹配 {{ tasks.length }} 项任务</p>
          <TaskCoverageOverview :tasks="tasks" :selected-id="taskId" @select="chooseTask" />
          <div class="task-guide-list">
            <button v-for="task in taskRows" :key="task.id" class="task-guide-card" :class="{chosen:taskId===task.id}" :aria-pressed="taskId===task.id" @click="taskId=task.id">
              <span class="task-guide-title">{{ task.guide?.name_zh || task.label }}</span>
              <small lang="en">{{ task.guide?.name_en || task.label }}</small>
              <p>{{ task.guide?.description_zh || '请结合知识库为此任务登记的关联基因及其缺失情况解读。' }}</p>
              <p v-if="task.guide" lang="en">{{ task.guide.description_en }}</p>
              <span class="coverage-state" :class="{covered:task.coverage_status==='full'}">{{ taskStatus(task.coverage_status) }}<template v-if="task.coverage_status !== 'unmapped'"> · {{ task.n_present_all }} / {{ task.n_genes_all }} 个关联基因</template></span>
              <span class="task-guide-genes">关联基因 · {{ splitGenes(task.present_genes_all).join(' · ') || '暂无' }}</span>
              <p class="task-guide-scope">{{ task.coverage_status === 'unmapped' ? '知识库未登记关联基因，不能按零覆盖率或零功能解释。' : task.coverage_status === 'absent' ? '输入未包含已登记的关联基因，不能据此判定功能不存在。' : '列出当前输入中的知识库关联基因。' }}</p>
            </button>
          </div>
          <p v-if="!tasks.length" class="empty-result">没有匹配的任务。</p><TablePager v-model:page="taskPage" v-model:page-size="taskSize" :pages="taskPages" :total="tasks.length" />
        </section>
        <aside class="card catalogue-detail" aria-label="任务范围详情"><span class="eyebrow">TASK / BIOLOGICAL MEANING</span><template v-if="selectedTask"><h2>{{ selectedTask.guide?.name_zh || selectedTask.label }}</h2><p lang="en">{{ selectedTask.guide?.name_en || selectedTask.label }}</p><strong class="coverage-state" :class="{covered:selectedTask.coverage_status==='full'}">{{ taskStatus(selectedTask.coverage_status) }}</strong><h3>功能说明 · Function</h3><p>{{ selectedTask.guide?.description_zh || '查看该代谢任务的功能说明、关联基因与输入范围。' }}</p><p v-if="selectedTask.guide" lang="en">{{ selectedTask.guide.description_en }}</p><h3>关联范围</h3><p v-if="selectedTask.coverage_status === 'unmapped'" class="task-scoring-scope">此任务尚无已登记的基因关联，无法计算输入覆盖比例；未登记不等于无代谢功能。</p><p v-else class="task-scoring-scope">当前知识库登记 {{ selectedTask.n_genes_all }} 个关联基因，输入中已包含 {{ selectedTask.n_present_all }} 个。这里的完整覆盖仅指知识库关联范围，相关生物过程还涉及其他基因与调控机制。</p><h3>已纳入输入的关联基因</h3><div class="gene-chips"><button v-for="gene in splitGenes(selectedTask.present_genes_all)" :key="gene" @click="openGene(gene)">{{ gene }}</button></div><p v-if="selectedTask.coverage_status === 'unmapped'">知识库尚未登记此任务的关联基因；覆盖比例没有可用分母。</p><p v-else-if="!selectedTask.n_present_all">当前输入尚未包含此任务的知识库关联基因，不能据此判断该功能不存在。</p><details v-if="selectedTask.n_missing_all"><summary>输入中缺失的关联基因</summary><p class="mono">{{ selectedTask.missing_genes_all }}</p></details><a v-if="selectedTask.guide" :href="selectedTask.guide.source_url" target="_blank" rel="noopener">{{ selectedTask.guide.source_label }} · 功能说明来源 ↗</a><details><summary>知识库任务名称</summary><p lang="en">{{ selectedTask.id }}</p></details></template></aside>
      </div>
      <details class="coverage-method"><summary>分类方法、版本与来源</summary><p>{{ data.classification.provenance?.annotation_version || '功能分类注释未提供' }} · {{ data.database_version }}</p><p>基因功能分类采用 PANTHER Protein Class，基因身份与英文名称对应 HGNC，代谢任务来自 scCellFie human Recon2 知识库。中文名称为界面释名，保留标准基因符号和英文原名供核对。</p><div class="btn-row"><button class="btn btn-sm" @click="exportCatalogue">下载有覆盖的基因与任务 JSON</button><a class="btn btn-sm" :href="data.classification.provenance?.source_url || 'https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0'" target="_blank" rel="noopener">PANTHER 分类来源 ↗</a></div></details>
    </template>
  </div>
</template>

<style scoped>

.coverage-page{max-width:1500px}.coverage-context{display:flex;justify-content:space-between;align-items:center;gap:24px;border-top:1px solid var(--border);padding:24px 0 14px}.coverage-context h2{font-size:22px;font-weight:500;margin:10px 0}.coverage-context p,.scope-explanation{font-size:12px;color:var(--muted);line-height:1.9}.coverage-context label{min-width:150px;font-size:11px;color:var(--muted)}select,input{display:block;width:100%;min-width:0;border:1px solid var(--border-strong);background:var(--card);color:var(--ink);padding:10px 12px;margin-top:8px;font:12px var(--font)}.scope-explanation{max-width:1000px;margin:10px 0 24px}.coverage-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));background:var(--card);border:1px solid var(--border);margin:24px 0 32px}.coverage-metrics>div{padding:25px 28px;border-right:1px solid var(--border)}.coverage-metrics>div:last-child{border:0}.coverage-metrics span{font-size:11px;color:var(--muted)}.coverage-metrics strong{display:block;font:38px Georgia,serif;margin:16px 0 8px;color:var(--primary-strong)}.coverage-metrics small{font-size:21px;color:var(--muted)}.coverage-metrics p{margin:0;font-size:11px;color:var(--muted)}.coverage-tabs{display:flex;gap:32px;border-bottom:1px solid var(--border);margin-bottom:24px}.coverage-tabs button{border:0;background:transparent;border-bottom:2px solid transparent;color:var(--muted);font:14px var(--font);padding:14px 0;cursor:pointer}.coverage-tabs button.active{color:var(--primary);border-bottom-color:var(--primary)}.coverage-tabs small{font-size:11px;margin-left:8px}.catalogue-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px;align-items:start}.catalogue-list,.catalogue-detail{min-width:0;padding:24px}.catalogue-title{display:flex;align-items:start;justify-content:space-between;gap:16px}.catalogue-title h2,.catalogue-detail h2{font-size:19px;font-weight:500;margin:0 0 10px;overflow-wrap:anywhere}.catalogue-title p,.catalogue-detail p{font-size:11px;color:var(--muted);line-height:1.9}.catalogue-title .btn{flex:none}.catalogue-filters{display:flex;gap:16px;margin-top:24px}.catalogue-filters label{font-size:11px;color:var(--muted);flex:0 1 170px;min-width:0}.catalogue-filters .catalogue-search{flex:1}.catalogue-count{font-size:11px;color:var(--muted);margin:18px 0 10px}.table th{font-size:11px}.table td{font-size:12px}.table td:first-child{min-width:140px}.table-wrap{overflow-x:auto}.catalogue-link{background:transparent;border:0;padding:0;color:var(--primary);font:inherit;text-align:left;text-decoration:underline;text-underline-offset:3px;cursor:pointer;line-height:1.8}.symbol-alias{display:block;color:var(--muted);font-size:10px;margin-top:5px}.chosen{background:var(--primary-weak)}.coverage-state{display:inline-block;color:var(--muted);font-size:11px;padding:4px 7px;background:var(--surface-soft);font-weight:400;white-space:nowrap}.coverage-state.covered{color:var(--primary);background:var(--primary-weak)}.catalogue-detail{position:sticky;top:100px}.catalogue-detail>.eyebrow{display:block;margin-bottom:18px}.catalogue-detail h3{font-size:12px;font-weight:500;border-top:1px solid var(--border);padding-top:18px;margin:24px 0 12px}.association-link{display:block;width:100%;border:0;border-bottom:1px solid var(--border);padding:10px 0;background:transparent;color:var(--primary);font:11px var(--font);text-align:left;line-height:1.9;cursor:pointer}.catalogue-detail details{margin-top:20px;font-size:11px}.catalogue-detail summary,.coverage-method summary{cursor:pointer;color:var(--primary)}.gene-chips{display:flex;gap:6px;flex-wrap:wrap;font-size:11px;color:var(--muted)}.gene-chips button{border:1px solid var(--border);background:var(--primary-weak);color:var(--primary);font:11px Consolas,monospace;padding:5px 8px;cursor:pointer}.gene-chips.missing button{background:var(--surface-soft);color:var(--muted)}.coverage-method{margin-top:32px;padding:20px 0;border-top:1px solid var(--border);font-size:12px}.coverage-method p{color:var(--muted);line-height:1.9}.coverage-method code,.catalogue-detail .mono{overflow-wrap:anywhere}.coverage-loading{padding:45px}.coverage-loading h2{font-size:21px;font-weight:500}.coverage-loading p,.empty-result{font-size:12px;color:var(--muted)}

.catalogue-filters .gene-class-filter{flex:1 1 300px}.gene-name-zh{display:block;font-size:11px;line-height:1.8;color:var(--ink);margin-top:5px}.class-english{display:block;font-size:10px;color:var(--muted);margin-top:5px;line-height:1.6}.task-search-label{display:block;font-size:11px;color:var(--muted);margin-top:24px}.task-guide-list{display:grid;gap:12px}.task-guide-card{display:block;width:100%;text-align:left;background:var(--card);border:1px solid var(--border);padding:18px 20px;cursor:pointer;color:var(--ink);font:12px var(--font)}.task-guide-card.chosen{border-color:var(--primary);background:var(--primary-weak)}.task-guide-card:hover{border-color:var(--primary)}.task-guide-title{display:block;font-size:16px;line-height:1.6}.task-guide-card>small{display:block;color:var(--primary);font-size:11px;line-height:1.8;margin:6px 0 12px}.task-guide-card p{font-size:12px;line-height:1.9;margin:8px 0}.task-guide-card p[lang=en]{font-size:11px;color:var(--muted)}.task-guide-genes{display:block;font:11px Consolas,monospace;color:var(--primary);margin-top:16px}.gene-class-explanation small{color:var(--primary);font-size:11px}.catalogue-detail>a{display:block;font-size:11px;line-height:1.9;margin-top:18px}.scope-explanation{max-width:1100px}.coverage-metrics strong{margin-bottom:12px}
</style>

<style scoped>
.coverage-page>.page-heading h2{font-size:25px;font-weight:500;margin:10px 0}.coverage-metrics>div{padding:24px 20px}.coverage-metrics strong{font-size:34px}.task-guide-card>.coverage-state{margin-top:8px}
.task-guide-card>.task-guide-scope{font-size:11px;color:var(--muted);margin-top:10px}.task-guide-genes{line-height:1.8;overflow-wrap:anywhere}.coverage-state{white-space:normal;line-height:1.8}
.coverage-page>.coverage-context{border-top:0;padding:0 0 18px;margin-bottom:0;align-items:center}.coverage-context-actions{display:flex;align-items:center;gap:14px;flex:none}.coverage-context-actions>label{min-width:200px}.coverage-page>.coverage-context h2{margin:10px 0 8px}.coverage-context p{margin:0}.coverage-metrics{margin-top:10px}.scope-explanation{margin:12px 0 16px}.task-guide-card>.task-guide-scope{margin-bottom:0}.coverage-context-actions>.btn{flex:none}
</style>

<style scoped>
.coverage-page>.coverage-context{padding:17px 20px;background:var(--surface-soft);border:1px solid var(--border);border-radius:9px;margin-bottom:19px}.coverage-context strong{font-size:13px;font-weight:500;color:var(--primary)}.coverage-context .shared-backgrounds{font-size:12px;margin-top:5px}.coverage-context-actions{gap:12px}.coverage-context-actions>label{font-size:11px}.coverage-metrics{border:0;border-radius:11px;background:var(--primary-weak);overflow:hidden;margin:0 0 25px}.coverage-metrics>div{padding:21px;border-color:var(--border-strong)}.coverage-metrics strong{font-size:33px;margin:12px 0 10px}.coverage-metrics p{line-height:1.8}.coverage-tabs{display:flex;gap:7px;margin:0 0 20px;padding:5px;background:var(--surface-soft);border:1px solid var(--border);border-radius:8px;width:fit-content;max-width:100%}.coverage-tabs button{padding:10px 17px;border:0;border-radius:5px;font-size:13px}.coverage-tabs button.active{background:var(--primary-strong);color:var(--card);box-shadow:var(--shadow)}.coverage-tabs small{display:inline-block;font:11px Consolas,monospace;margin-left:9px;opacity:.85}.catalogue-layout{grid-template-columns:minmax(0,1fr) minmax(270px,30%);gap:20px}.catalogue-list,.catalogue-detail{border-radius:11px;border:1px solid var(--border);padding:23px;box-shadow:var(--shadow)}.catalogue-detail{background:var(--surface-soft);top:95px;max-height:calc(100vh - 115px);overflow:auto}.catalogue-detail>.eyebrow{color:var(--primary);font-size:10px;letter-spacing:.08em}.catalogue-detail h2{font:26px Georgia,'Microsoft YaHei',serif;line-height:1.5}.catalogue-detail p{font-size:12px}.catalogue-title h2{font-size:19px}.catalogue-title p{font-size:12px;margin-bottom:0}.catalogue-filters{gap:12px;padding:15px;margin-top:20px;background:var(--surface-soft);border:1px solid var(--border);border-radius:7px}.catalogue-filters label{font-size:12px}.catalogue-filters select,.catalogue-filters input{border-radius:5px;min-height:41px;font-size:12px}.catalogue-list .table-wrap{border:1px solid var(--border);border-radius:7px}.catalogue-list .table{margin:0}.catalogue-list .table th{background:var(--table-head-bg)}.catalogue-list .table td{padding-top:14px;padding-bottom:14px}.catalogue-link{font-size:14px;font-weight:500;text-decoration:none;border-bottom:1px solid var(--primary-soft)}.catalogue-count{font-size:12px;color:var(--primary);margin:18px 0 12px}.coverage-state{border-radius:5px;padding:6px 9px;font-size:11px}.task-guide-card{border-radius:9px;padding:18px 20px}.task-guide-card.chosen{box-shadow:inset 3px 0 var(--primary)}.task-guide-title{font-size:16px}.task-guide-card p[lang=en]{font-size:11px;line-height:1.8}.task-search-label{font-size:12px}.task-search-label select,.task-search-label input{border-radius:5px}.coverage-method{padding:18px 21px;border:1px solid var(--border);background:var(--surface-soft);border-radius:8px;margin-top:23px}.coverage-method summary{font-size:13px}.gene-chips button{border-radius:4px;line-height:1.6}.catalogue-detail .association-link{font-size:12px;padding:12px 0}
@media(max-width:1100px){.coverage-context{flex-wrap:wrap}.coverage-context-actions{flex-wrap:wrap}.coverage-metrics>div{padding:17px}.catalogue-layout{grid-template-columns:minmax(0,1fr) 270px;gap:15px}.catalogue-list,.catalogue-detail{padding:18px}.catalogue-filters{flex-wrap:wrap}.catalogue-filters .gene-class-filter,.catalogue-filters .catalogue-search{flex-basis:100%}.catalogue-title{flex-wrap:wrap}}
@media(max-width:850px){.catalogue-layout{grid-template-columns:1fr}.catalogue-detail{position:static;max-height:none}.coverage-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.coverage-metrics>div:nth-child(2){border-right:0}.coverage-metrics>div:nth-child(-n+2){border-bottom:1px solid var(--border-strong)}.coverage-context-actions{width:100%;justify-content:space-between}.coverage-metrics strong{font-size:30px}}
@media(max-width:500px){.coverage-metrics>div{padding:16px}.coverage-metrics span,.coverage-metrics p{font-size:11px}.coverage-tabs{width:100%}.coverage-tabs button{flex:1;padding:10px 9px;font-size:12px}.coverage-tabs small{margin-left:5px}.coverage-context-actions{align-items:flex-start;flex-direction:column}.coverage-context-actions>label{width:100%}.catalogue-list,.catalogue-detail{padding:16px}.catalogue-title h2{font-size:18px}.catalogue-filters{padding:12px}.coverage-page>.coverage-context{padding:16px}}
</style>

<style scoped>
.coverage-cache-note{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 16px;font-size:11px;color:var(--muted);margin:-7px 0 18px}.coverage-cache-note small{font-size:10px;color:var(--faint)}.coverage-loading{padding:28px;border-radius:12px}.coverage-loading-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.coverage-loading-heading h2{font-size:22px;margin:10px 0}.coverage-loading-heading p{line-height:1.9;margin:10px 0 0}.coverage-loading-heading>.btn{flex:none}.coverage-loading-stages{display:flex;align-items:center;gap:16px;margin:25px 0 18px;color:var(--primary);font-size:12px}.coverage-loading-stages i{font-style:normal;color:var(--faint)}.coverage-skeleton{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.coverage-skeleton>div{display:grid;gap:17px;padding:22px;background:var(--surface-soft);border-radius:8px}.coverage-skeleton i,.coverage-skeleton b{display:block;height:9px;width:74%;border-radius:4px;background:var(--border);animation:coverage-pulse 1.6s ease-in-out infinite}.coverage-skeleton b{height:29px;width:54%}.coverage-skeleton i:last-child{width:95%}.loading-explanation{font-size:11px;margin-top:18px}.metabolic-chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr;align-items:center;gap:19px;padding:21px 24px;border:1px solid var(--border);border-radius:10px;background:var(--card);margin:0 0 24px}.metabolic-chain>div{min-width:0}.metabolic-chain>div>span{font:10px Consolas,monospace;letter-spacing:.1em;color:var(--primary)}.metabolic-chain h2{font-size:14px;font-weight:500;margin:10px 0}.metabolic-chain p{font-size:12px;line-height:1.85;color:var(--muted);margin:0}.metabolic-chain>i{font:22px Georgia,serif;color:var(--primary-soft)}.task-status-overview{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:17px 0}.task-status-overview button{display:flex;align-items:flex-start;flex-direction:column;gap:11px;border:1px solid var(--border);border-radius:7px;background:var(--surface-soft);padding:14px;text-align:left;cursor:pointer;color:var(--muted);font:11px var(--font)}.task-status-overview strong{font:25px Georgia,serif;color:var(--primary)}.task-status-overview button.active{border-color:var(--primary);background:var(--primary-weak)}
@keyframes coverage-pulse{50%{opacity:.45}}
@media(max-width:900px){.metabolic-chain{gap:13px;padding:18px}.metabolic-chain h2{font-size:13px}.coverage-skeleton>div{padding:17px}.task-status-overview{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.metabolic-chain{grid-template-columns:1fr;gap:15px}.metabolic-chain>i{display:none}.metabolic-chain>div:not(:first-child){border-top:1px solid var(--border);padding-top:15px}.coverage-skeleton{grid-template-columns:repeat(2,minmax(0,1fr))}.coverage-loading{padding:20px}.coverage-loading-heading{align-items:flex-start;flex-direction:column;gap:14px}.coverage-loading-heading h2{font-size:20px}.coverage-loading-stages{gap:12px;font-size:11px}.coverage-cache-note{line-height:1.7;margin-top:0}.metabolic-chain p{font-size:12px}}
@media(prefers-reduced-motion:reduce){.coverage-skeleton i,.coverage-skeleton b{animation:none}}
</style>

<style scoped>
.metabolic-explanation{border:1px solid var(--border);border-radius:8px;background:var(--card);margin:0 0 20px}.metabolic-explanation>summary{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:9px 20px;cursor:pointer;padding:14px 20px;color:var(--primary)}.metabolic-explanation>summary strong{font-size:12px;font-weight:500}.metabolic-explanation>summary i{font-style:normal;color:var(--faint);margin:0 12px}.metabolic-explanation>summary>span{font-size:11px;color:var(--muted)}.metabolic-explanation .metabolic-chain{border:0;border-top:1px solid var(--border);border-radius:0;margin:0;padding:18px 20px;background:transparent}@media(max-width:650px){.metabolic-explanation>summary{padding:13px 16px}.metabolic-explanation>summary i{margin:0 7px}.metabolic-explanation>summary>span{font-size:10px}}
</style>
