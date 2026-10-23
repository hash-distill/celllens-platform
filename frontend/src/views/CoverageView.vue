<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api/http'
import type { CoverageCatalogue } from '../types/coverage'
import { downloadBlob, downloadCsv } from '../utils/csv'
import { usePagedRows } from '../utils/pagination'
import TablePager from '../components/TablePager.vue'
import GeneCategoryGuide from '../components/GeneCategoryGuide.vue'
import TaskCoverageOverview from '../components/TaskCoverageOverview.vue'
import MethodsPageHeader from '../components/MethodsPageHeader.vue'
import { buildCoverageExport } from '../utils/exportArtifacts'

const route = useRoute(), router = useRouter()
const data = ref<CoverageCatalogue | null>(null), loading = ref(false), error = ref('')
const tab = ref<'genes' | 'tasks'>('genes'), geneQuery = ref(''), taskQuery = ref('')
const taskCoverage = ref<'covered' | 'full' | 'partial'>('covered')
const geneCategory = ref(''), geneId = ref(''), taskId = ref('')
let controller: AbortController | undefined
const coveredGenes = computed(() => (data.value?.genes ?? []).filter(gene => gene.in_panel))
const coveredTasks = computed(() => (data.value?.tasks ?? []).filter(task => task.coverage_status === 'full'))
const availableTasks = computed(() => (data.value?.tasks ?? []).filter(task => task.n_present_all > 0 && (task.coverage_status === 'full' || task.coverage_status === 'partial')))
const partialTasks = computed(() => availableTasks.value.filter(task => task.coverage_status === 'partial'))
const coveredReactions = computed(() => (data.value?.reactions ?? []).filter(reaction => reaction.n_genes_all > 0 && reaction.n_missing_all === 0))
const categories = computed(() => data.value?.gene_categories ?? [])
const sourceTitle = computed(() => data.value?.source.kind === 'model' ? '模型覆盖范围' : '输入覆盖范围')
const panelGroups = computed(() => {
  const groups = new Map<string, CoverageCatalogue['models']>()
  for (const model of data.value?.models ?? []) {
    const key = model.panel_sha256 || model.id
    groups.set(key, [...(groups.get(key) ?? []), model])
  }
  return [...groups.values()]
})
const sharedModels = computed(() => data.value?.source.kind === 'model'
  ? panelGroups.value.find(group => group.some(model => model.id === data.value?.source.id)) ?? [] : [])
const genes = computed(() => coveredGenes.value.filter(gene =>
  (!geneCategory.value || gene.category_ids.includes(geneCategory.value)) &&
  `${gene.symbol} ${gene.approved_symbol} ${gene.hgnc_id ?? ''} ${gene.name_zh ?? ''} ${gene.name_en}`.toLowerCase().includes(geneQuery.value.trim().toLowerCase())))
const tasks = computed(() => availableTasks.value.filter(task =>
  (taskCoverage.value === 'covered' || task.coverage_status === taskCoverage.value) &&
  `${task.id} ${task.guide?.name_zh ?? ''} ${task.guide?.name_en ?? ''} ${task.present_genes_all}`.toLowerCase().includes(taskQuery.value.trim().toLowerCase())))
const {page: genePage, pageSize: geneSize, pages: genePages, visible: geneRows} = usePagedRows(genes)
const {page: taskPage, pageSize: taskSize, pages: taskPages, visible: taskRows} = usePagedRows(tasks)
const selectedGene = computed(() => coveredGenes.value.find(gene => gene.symbol === geneId.value))
const selectedTask = computed(() => tasks.value.find(task => task.id === taskId.value))
watch(tasks, rows => {
  if (!rows.some(task => task.id === taskId.value)) taskId.value = rows[0]?.id ?? ''
})
function taskStatus(status: 'full' | 'partial' | 'absent' | 'unmapped'): string {
  return {full:'完整覆盖', partial:'部分覆盖', absent:'未覆盖', unmapped:'未登记关联基因'}[status]
}
const selectedGeneCategories = computed(() => categories.value.filter(item => selectedGene.value?.category_ids.includes(item.id)))
const returnTarget = computed(() => data.value?.source.kind === 'run' ? {path:'/demo', query:{run:data.value.source.id}} : {path:'/'})
function splitGenes(value: string) {return value ? value.split(';').filter(Boolean) : []}
function categoryName(ids: string[]) {return categories.value.filter(item => ids.includes(item.id)).map(item => item.name_zh).join('、')}
async function load() {
  controller?.abort(); const current = controller = new AbortController()
  data.value = null; error.value = ''; loading.value = true; geneId.value = ''; taskId.value = ''; geneCategory.value = ''
  try {
    const result = await apiFetch<CoverageCatalogue>('/coverage', {query:{cell_line:route.query.cell_line as string | undefined, run_id:route.query.run as string | undefined}, signal:current.signal, timeoutMs:120000})
    if (current.signal.aborted) return
    data.value = result
    taskId.value = availableTasks.value[0]?.id ?? ''
    applyTaskLink()
  } catch(reason) {if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '覆盖目录读取失败'}
  finally {if (!current.signal.aborted) loading.value = false}
}
function applyTaskLink() {
  const chosen = typeof route.query.task === 'string' ? route.query.task : ''
  if (chosen && availableTasks.value.some(task => task.id === chosen)) {tab.value = 'tasks'; taskCoverage.value = 'covered'; taskQuery.value = ''; void chooseTask(chosen)}
}
watch(() => [route.query.cell_line, route.query.run], load, {immediate:true})
watch(() => route.query.task, applyTaskLink)
onBeforeUnmount(() => controller?.abort())
function changeModel(event: Event) {void router.replace({path:'/methods/coverage',query:{cell_line:(event.target as HTMLSelectElement).value}})}
function openGene(symbol: string) {if (!coveredGenes.value.some(gene => gene.symbol === symbol)) return; tab.value = 'genes'; geneCategory.value = ''; geneQuery.value = symbol; geneId.value = symbol}
function openTask(id: string) {tab.value = 'tasks'; taskCoverage.value = 'covered'; taskQuery.value = ''; void chooseTask(id)}
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
    <MethodsPageHeader eyebrow="STATE → scCellFie / GENE &amp; TASK COVERAGE" title="代谢覆盖" description="查看表达面板覆盖了哪些代谢基因、反应与任务。覆盖说明输入范围，不代表预测准确率。" />
    <header v-if="data" class="coverage-context">
      <div><strong>{{ sourceTitle }}</strong><p v-if="data.source.kind === 'model'" class="shared-backgrounds">STATE 表达面板 · {{ sharedModels.map(model => model.cell_line).join('、') }}</p><p v-else>{{ data.source.title }} · 保存的输入面板</p></div>
      <div v-if="data" class="coverage-context-actions">
        <label v-if="data.source.kind === 'model' && panelGroups.length > 1">基因面板<select aria-label="覆盖目录基因面板" :value="sharedModels[0]?.cell_line" @change="changeModel"><option v-for="group in panelGroups" :key="group[0]!.id" :value="group[0]!.cell_line">{{ group.map(model => model.cell_line).join(' / ') }}{{ group[0]!.panel_sha256 ? '' : '（暂不可用）' }}</option></select></label>
        <template v-if="data.source.kind === 'run'"><RouterLink class="btn btn-sm" to="/methods/coverage">查看当前模型范围</RouterLink><RouterLink :to="returnTarget" class="btn btn-sm">返回实验</RouterLink></template>
        <RouterLink v-else class="btn btn-sm" to="/methods/backgrounds">了解细胞背景 ↗</RouterLink>
      </div>
    </header>
    <div v-if="loading" class="card coverage-loading" role="status"><p>正在核对基因面板与代谢关联；首次准备可能较慢，完成后复用已校验结果。</p></div>
    <div v-else-if="error" class="notice notice-danger" role="alert">{{ error }} <button class="btn btn-sm" @click="load">重试</button></div>
    <template v-else-if="data">
      <section class="coverage-metrics" aria-label="当前覆盖数量">
        <div><span>表达面板基因</span><strong>{{ data.panel_gene_count.toLocaleString() }}</strong><p>模型 / 保存结果的实际输入面板</p></div>
        <div><span>已覆盖的代谢基因</span><strong>{{ coveredGenes.length }}</strong><p>已纳入表达面板的知识库关联基因</p></div>
        <div><span>有覆盖的代谢任务</span><strong>{{ availableTasks.length }}</strong><p>完整 {{ coveredTasks.length }} 项 · 部分 {{ partialTasks.length }} 项</p></div>
        <div><span>完整覆盖的关联反应</span><strong>{{ coveredReactions.length }}</strong><p>当前知识库关联基因均已纳入输入</p></div>
      </section>
      <nav class="coverage-tabs" aria-label="覆盖目录"><button :class="{active:tab==='genes'}" :aria-pressed="tab==='genes'" @click="tab='genes'">已覆盖代谢基因 <small>{{ coveredGenes.length }}</small></button><button :class="{active:tab==='tasks'}" :aria-pressed="tab==='tasks'" @click="tab='tasks'">代谢任务介绍</button></nav>
      <div v-if="tab==='genes'" class="catalogue-layout">
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>目前覆盖哪些代谢基因？</h2><p>按蛋白功能类别浏览，点击基因查看分类与关联任务。</p></div><button class="btn btn-sm" @click="exportGenes">下载已覆盖基因</button></div>
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
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>代谢任务与关联基因</h2><p>显示当前面板已完整或部分覆盖的任务。</p></div></div>
          <p class="scope-explanation">关联基因以当前 scCellFie 知识库的反应规则为依据，覆盖率表示这些基因在输入中的可用比例；相关生物过程涉及的基因不限于此。</p>
          <label class="task-search-label">任务覆盖范围<select v-model="taskCoverage" aria-label="任务覆盖范围"><option value="covered">全部有覆盖的任务（{{ availableTasks.length }}）</option><option value="full">完整覆盖（{{ coveredTasks.length }}）</option><option value="partial">部分覆盖（{{ partialTasks.length }}）</option></select></label>
          <label class="task-search-label">搜索任务<input v-model="taskQuery" type="search" placeholder="中文、English 或关联基因" /></label><p class="catalogue-count" role="status">匹配 {{ tasks.length }} 项任务</p>
          <TaskCoverageOverview :tasks="tasks" :selected-id="taskId" @select="chooseTask" />
          <div class="task-guide-list">
            <button v-for="task in taskRows" :key="task.id" class="task-guide-card" :class="{chosen:taskId===task.id}" :aria-pressed="taskId===task.id" @click="taskId=task.id">
              <span class="task-guide-title">{{ task.guide?.name_zh || task.label }}</span>
              <small lang="en">{{ task.guide?.name_en || task.label }}</small>
              <p>{{ task.guide?.description_zh || '请结合知识库为此任务登记的关联基因及其缺失情况解读。' }}</p>
              <p v-if="task.guide" lang="en">{{ task.guide.description_en }}</p>
              <span class="coverage-state" :class="{covered:task.coverage_status==='full'}">{{ taskStatus(task.coverage_status) }} · {{ task.n_present_all }} / {{ task.n_genes_all }} 个关联基因</span>
              <span class="task-guide-genes">关联基因 · {{ splitGenes(task.present_genes_all).join(' · ') || '暂无' }}</span>
              <p class="task-guide-scope">列出当前输入中的知识库关联基因。</p>
            </button>
          </div>
          <p v-if="!tasks.length" class="empty-result">没有匹配的任务。</p><TablePager v-model:page="taskPage" v-model:page-size="taskSize" :pages="taskPages" :total="tasks.length" />
        </section>
        <aside class="card catalogue-detail" aria-label="任务范围详情"><span class="eyebrow">TASK / BIOLOGICAL MEANING</span><template v-if="selectedTask"><h2>{{ selectedTask.guide?.name_zh || selectedTask.label }}</h2><p lang="en">{{ selectedTask.guide?.name_en || selectedTask.label }}</p><strong class="coverage-state" :class="{covered:selectedTask.coverage_status==='full'}">{{ taskStatus(selectedTask.coverage_status) }}</strong><h3>功能说明 · Function</h3><p>{{ selectedTask.guide?.description_zh || '查看该代谢任务的功能说明、关联基因与输入范围。' }}</p><p v-if="selectedTask.guide" lang="en">{{ selectedTask.guide.description_en }}</p><h3>关联范围</h3><p class="task-scoring-scope">当前知识库登记 {{ selectedTask.n_genes_all }} 个关联基因，输入中已包含 {{ selectedTask.n_present_all }} 个。这里的完整覆盖仅指知识库关联范围，相关生物过程还涉及其他基因与调控机制。</p><h3>已纳入输入的关联基因</h3><div class="gene-chips"><button v-for="gene in splitGenes(selectedTask.present_genes_all)" :key="gene" @click="openGene(gene)">{{ gene }}</button></div><p v-if="!selectedTask.n_present_all">当前输入尚未包含此任务的知识库关联基因。</p><details v-if="selectedTask.n_missing_all"><summary>输入中缺失的关联基因</summary><p class="mono">{{ selectedTask.missing_genes_all }}</p></details><a v-if="selectedTask.guide" :href="selectedTask.guide.source_url" target="_blank" rel="noopener">{{ selectedTask.guide.source_label }} · 功能说明来源 ↗</a><details><summary>知识库任务名称</summary><p lang="en">{{ selectedTask.id }}</p></details></template></aside>
      </div>
      <details class="coverage-method"><summary>分类方法、版本与来源</summary><p>{{ data.classification.provenance?.annotation_version || '功能分类注释未提供' }} · {{ data.database_version }}</p><p>基因功能分类采用 PANTHER Protein Class，基因身份与英文名称对应 HGNC，代谢任务来自 scCellFie human Recon2 知识库。中文名称为界面释名，保留标准基因符号和英文原名供核对。</p><div class="btn-row"><button class="btn btn-sm" @click="exportCatalogue">下载关联基因与任务 JSON</button><a class="btn btn-sm" :href="data.classification.provenance?.source_url || 'https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0'" target="_blank" rel="noopener">PANTHER 分类来源 ↗</a></div></details>
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
