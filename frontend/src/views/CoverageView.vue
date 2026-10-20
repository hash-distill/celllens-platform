<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api/http'
import type { CoverageCatalogue } from '../types/coverage'
import { downloadBlob, downloadCsv } from '../utils/csv'
import { usePagedRows } from '../utils/pagination'
import TablePager from '../components/TablePager.vue'
import GeneCategoryGuide from '../components/GeneCategoryGuide.vue'
import CellBackgroundGuide from '../components/CellBackgroundGuide.vue'

const route = useRoute(), router = useRouter()
const data = ref<CoverageCatalogue | null>(null), loading = ref(false), error = ref('')
const tab = ref<'genes' | 'tasks'>('genes'), geneQuery = ref(''), taskQuery = ref('')
const geneCategory = ref(''), geneId = ref(''), taskId = ref('')
let controller: AbortController | undefined
const coveredGenes = computed(() => (data.value?.genes ?? []).filter(gene => gene.in_panel))
const coveredTasks = computed(() => (data.value?.tasks ?? []).filter(task => task.coverage_status === 'full'))
const coveredReactions = computed(() => (data.value?.reactions ?? []).filter(reaction => reaction.n_genes_all > 0 && reaction.n_missing_all === 0))
const categories = computed(() => data.value?.gene_categories ?? [])
const sourceTitle = computed(() => data.value?.source.kind === 'model' ? '模型覆盖范围' : '输入覆盖范围')
const genes = computed(() => coveredGenes.value.filter(gene =>
  (!geneCategory.value || gene.category_ids.includes(geneCategory.value)) &&
  `${gene.symbol} ${gene.approved_symbol} ${gene.hgnc_id ?? ''} ${gene.name_en}`.toLowerCase().includes(geneQuery.value.trim().toLowerCase())))
const tasks = computed(() => coveredTasks.value.filter(task =>
  `${task.id} ${task.guide?.name_zh ?? ''} ${task.guide?.name_en ?? ''} ${task.present_genes_all}`.toLowerCase().includes(taskQuery.value.trim().toLowerCase())))
const {page: genePage, pageSize: geneSize, pages: genePages, visible: geneRows} = usePagedRows(genes)
const selectedGene = computed(() => coveredGenes.value.find(gene => gene.symbol === geneId.value))
const selectedTask = computed(() => data.value?.tasks.find(task => task.id === taskId.value))
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
    taskId.value = coveredTasks.value[0]?.id ?? ''
    applyTaskLink()
  } catch(reason) {if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '覆盖目录读取失败'}
  finally {if (!current.signal.aborted) loading.value = false}
}
function applyTaskLink() {
  const chosen = typeof route.query.task === 'string' ? route.query.task : ''
  if (chosen && data.value?.tasks.some(task => task.id === chosen)) {tab.value = 'tasks'; taskId.value = chosen}
}
watch(() => [route.query.cell_line, route.query.run], load, {immediate:true})
watch(() => route.query.task, applyTaskLink)
onBeforeUnmount(() => controller?.abort())
function changeModel(event: Event) {void router.replace({path:'/coverage',query:{cell_line:(event.target as HTMLSelectElement).value}})}
function openGene(symbol: string) {if (!coveredGenes.value.some(gene => gene.symbol === symbol)) return; tab.value = 'genes'; geneCategory.value = ''; geneQuery.value = symbol; geneId.value = symbol}
function openTask(id: string) {tab.value = 'tasks'; taskQuery.value = ''; taskId.value = id}
function exportGenes() {
  if (!data.value) return
  downloadCsv(`${data.value.source.id}-covered-metabolic-genes.csv`, ['symbol','approved_symbol','hgnc_id','name_en','category_zh','category_en'], coveredGenes.value.map(gene => [gene.symbol,gene.approved_symbol,gene.hgnc_id ?? '',gene.name_en,categoryName(gene.category_ids),categories.value.filter(item => gene.category_ids.includes(item.id)).map(item => item.name_en).join(';')]))
}
function exportCatalogue() {
  if (!data.value) return
  const output = {source:data.value.source, method:data.value.method, package_version:data.value.package_version, database_version:data.value.database_version, database_provenance:data.value.database_provenance, classification:data.value.classification, covered_counts:{genes:coveredGenes.value.length,tasks:coveredTasks.value.length,reactions:coveredReactions.value.length},gene_categories:categories.value,genes:coveredGenes.value,tasks:coveredTasks.value,reactions:coveredReactions.value}
  downloadBlob(new Blob([JSON.stringify(output,null,2)],{type:'application/json'}),`${data.value.source.id}-covered-catalogue.json`)
}
</script>

<template>
  <div class="page coverage-page">
    <header class="page-heading"><div><span class="eyebrow">STATE → scCellFie / COVERED FUNCTIONS</span><h1>{{ sourceTitle }}</h1><p>了解目前覆盖的代谢基因、功能类别和代谢任务。</p></div><RouterLink :to="returnTarget" class="btn">{{ data?.source.kind === 'model' || !data ? '返回首页' : '返回实验' }}</RouterLink></header>
    <div v-if="loading" class="card coverage-loading" role="status"><h2>正在读取覆盖目录…</h2><p>首次读取会校验基因面板与功能注释，不运行扰动预测。</p></div>
    <div v-else-if="error" class="notice notice-danger" role="alert">{{ error }} <button class="btn btn-sm" @click="load">重试</button></div>
    <template v-else-if="data">
      <section class="coverage-context">
        <div><span class="eyebrow">{{ data.source.kind === 'model' ? 'REGISTERED MODEL PANEL' : 'SAVED INPUT PANEL' }}</span><h2>{{ data.source.kind === 'model' ? data.source.cell_line + ' · STATE 输出面板' : data.source.title }}</h2><p>{{ data.database_version }}</p></div>
        <label v-if="data.source.kind === 'model'">细胞背景<select aria-label="覆盖目录细胞背景" :value="data.source.cell_line" @change="changeModel"><option v-for="model in data.models" :key="model.id" :value="model.cell_line">{{ model.cell_line }}</option></select></label>
        <RouterLink v-else class="btn btn-sm" to="/coverage">查看当前模型范围</RouterLink>
      </section>
      <p class="scope-explanation">{{ data.source.kind === 'model' ? '同一输出基因面板与数据库下，覆盖范围保持相同，不随扰动目标、细胞数或随机种子改变。' : '当前显示该实验保存的实际输入范围；历史模型的基因面板可能与当前在线模型不同。' }}任务的完整覆盖指其在冻结数据库中关联的基因均可用，不代表整条生物通路已经验证。</p>
      <CellBackgroundGuide v-if="data.source.kind === 'model'" :cell-line="data.source.cell_line" :cell-lines="data.models.map(model => model.cell_line)" />
      <section class="coverage-metrics" aria-label="当前覆盖数量">
        <div><span>已覆盖的代谢基因</span><strong>{{ coveredGenes.length }}</strong><p>Metabolic genes in the input panel</p></div>
        <div><span>完整覆盖的代谢任务</span><strong>{{ coveredTasks.length }}</strong><p>Tasks with all mapped genes available</p></div>
        <div><span>完整覆盖的关联反应</span><strong>{{ coveredReactions.length }}</strong><p>Reactions with all mapped genes available</p></div>
      </section>
      <nav class="coverage-tabs" aria-label="覆盖目录"><button :class="{active:tab==='genes'}" :aria-pressed="tab==='genes'" @click="tab='genes'">已覆盖代谢基因 <small>{{ coveredGenes.length }}</small></button><button :class="{active:tab==='tasks'}" :aria-pressed="tab==='tasks'" @click="tab='tasks'">代谢任务介绍 <small>{{ coveredTasks.length }}</small></button></nav>
      <div v-if="tab==='genes'" class="catalogue-layout">
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>目前覆盖哪些代谢基因？</h2><p>按蛋白功能类别浏览，点击基因查看分类与关联任务。</p></div><button class="btn btn-sm" @click="exportGenes">下载已覆盖基因</button></div>
          <div class="catalogue-filters"><label class="gene-class-filter">功能类别<select v-model="geneCategory" aria-label="代谢基因功能分类"><option value="">全部已覆盖类别</option><option v-for="item in categories" :key="item.id" :value="item.id">{{ item.name_zh }} · {{ item.name_en }}（{{ item.count }}）</option></select></label><label class="catalogue-search">搜索基因<input v-model="geneQuery" type="search" placeholder="基因符号、名称或 HGNC ID" /></label></div>
          <GeneCategoryGuide :categories="categories" :selected="geneCategory" />
          <p v-if="!data.classification.available" class="muted small">功能分类注释暂不可用，当前基因列为“暂无分类注释”。</p>
          <p class="catalogue-count" role="status">匹配 {{ genes.length }} 个已覆盖基因</p>
          <div class="table-wrap"><table class="table"><thead><tr><th>基因</th><th>蛋白功能类别</th><th>HGNC 身份</th></tr></thead><tbody><tr v-for="gene in geneRows" :key="gene.symbol" :class="{chosen:geneId===gene.symbol}"><td><button class="catalogue-link mono" @click="geneId=gene.symbol">{{ gene.symbol }}</button><small v-if="gene.approved_symbol!==gene.symbol" class="symbol-alias">现用名 {{ gene.approved_symbol }}</small></td><td><span>{{ categoryName(gene.category_ids) }}</span><small class="class-english" lang="en">{{ categories.filter(item=>gene.category_ids.includes(item.id)).map(item=>item.name_en).join('; ') }}</small></td><td class="mono">{{ gene.hgnc_id || '未登记' }}</td></tr></tbody></table></div>
          <p v-if="!genes.length" class="empty-result">没有匹配的已覆盖基因。</p><TablePager v-model:page="genePage" v-model:page-size="geneSize" :pages="genePages" :total="genes.length" />
        </section>
        <aside class="card catalogue-detail" aria-label="基因范围详情"><span class="eyebrow">GENE / FUNCTION CLASS</span><template v-if="selectedGene"><h2>{{ selectedGene.symbol }}</h2><p lang="en">{{ selectedGene.name_en }}</p><p>{{ selectedGene.approved_symbol }} · {{ selectedGene.hgnc_id || '无 HGNC 身份记录' }}</p><strong class="coverage-state covered">已包含在输入面板中</strong><section v-for="item in selectedGeneCategories" :key="item.id" class="gene-class-explanation"><h3>{{ item.name_zh }}</h3><small lang="en">{{ item.name_en }}</small><p>{{ item.description_zh }}</p><p lang="en">{{ item.description_en }}</p></section><h3>关联的已覆盖任务</h3><button v-for="task in coveredTasks.filter(item=>selectedGene?.tasks.includes(item.id))" :key="task.id" class="association-link" @click="openTask(task.id)">{{ task.guide?.name_zh || task.label }} ↗</button><p v-if="!coveredTasks.some(item=>selectedGene?.tasks.includes(item.id))">该基因暂无关联的完整覆盖任务；仍可能参与部分覆盖任务的评分。</p><a v-if="selectedGene.hgnc_id" :href="'https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/'+selectedGene.hgnc_id" target="_blank" rel="noopener">HGNC 基因信息 ↗</a></template><template v-else><h2>从基因认识功能类别</h2><p>点击基因名称，查看类别的中英文说明及其关联的已覆盖任务。</p></template></aside>
      </div>
      <div v-else class="catalogue-layout">
        <section class="card catalogue-list"><div class="catalogue-title"><div><h2>目前完整覆盖的代谢任务</h2><p>每项介绍说明其生物学含义、当前关联基因与解读范围。</p></div></div>
          <label class="task-search-label">搜索任务<input v-model="taskQuery" type="search" placeholder="中文、English 或关联基因" /></label><p class="catalogue-count" role="status">匹配 {{ tasks.length }} 项已覆盖任务</p>
          <div class="task-guide-list"><button v-for="task in tasks" :key="task.id" class="task-guide-card" :class="{chosen:taskId===task.id}" :aria-pressed="taskId===task.id" @click="taskId=task.id"><span class="task-guide-title">{{ task.guide?.name_zh || task.label }}</span><small lang="en">{{ task.guide?.name_en || task.label }}</small><p>{{ task.guide?.description_zh || '该任务的全部关联基因已包含在本输入中。' }}</p><p v-if="task.guide" lang="en">{{ task.guide.description_en }}</p><span class="task-guide-genes">关联基因 · {{ splitGenes(task.present_genes_all).join(' · ') }}</span></button></div>
          <p v-if="!tasks.length" class="empty-result">没有匹配的已覆盖任务。</p>
        </section>
        <aside class="card catalogue-detail" aria-label="任务范围详情"><span class="eyebrow">TASK / BIOLOGICAL MEANING</span><template v-if="selectedTask"><h2>{{ selectedTask.guide?.name_zh || selectedTask.label }}</h2><p lang="en">{{ selectedTask.guide?.name_en || selectedTask.label }}</p><strong class="coverage-state" :class="{covered:selectedTask.coverage_status==='full'}">{{ selectedTask.coverage_status==='full'?'关联基因完整覆盖':'该实验任务存在缺失关联基因' }}</strong><h3>功能说明 · Function</h3><p>{{ selectedTask.guide?.description_zh || '当前输入包含该任务的可用关联基因，评分请结合缺失范围解读。' }}</p><p v-if="selectedTask.guide" lang="en">{{ selectedTask.guide.description_en }}</p><h3>本任务的已覆盖基因</h3><div class="gene-chips"><button v-for="gene in splitGenes(selectedTask.present_genes_all)" :key="gene" @click="openGene(gene)">{{ gene }}</button></div><h3>如何理解 · Interpretation</h3><p>{{ selectedTask.guide?.scope_zh || '完整覆盖只描述数据库映射的输入范围，不代表整条通路的活性。' }}</p><p v-if="selectedTask.guide" lang="en">{{ selectedTask.guide.scope_en }}</p><details v-if="selectedTask.n_missing_all"><summary>该实验任务的缺失基因</summary><p class="mono">{{ selectedTask.missing_genes_all }}</p></details><a v-if="selectedTask.guide" :href="selectedTask.guide.source_url" target="_blank" rel="noopener">{{ selectedTask.guide.source_label }} · 说明来源 ↗</a><details><summary>冻结数据库原始任务名称</summary><p lang="en">{{ selectedTask.id }}</p></details></template></aside>
      </div>
      <details class="coverage-method"><summary>分类方法、版本与来源</summary><p>{{ data.classification.provenance?.annotation_version || '功能分类注释未提供' }} · {{ data.database_version }}</p><p>基因分类来源于已冻结的 PANTHER 蛋白功能注释，使用 HGNC 身份对应基因；类别允许重叠，无注释的基因保留“暂无分类注释”。任务介绍参考 UniProt，关联基因仍以当前冻结数据库为准。</p><p>实验评分随表达变化；分类与覆盖范围描述输入依据，不能直接代表功能活性、代谢通量或预测准确率。</p><p>输入来源：{{ data.source.id }} · SHA-256：<code>{{ data.source.panel_sha256 }}</code></p><p>冻结数据库清单 SHA-256：<code>{{ data.database_provenance.manifest_sha256 }}</code></p><div class="btn-row"><button class="btn btn-sm" @click="exportCatalogue">下载当前覆盖目录 JSON</button><a class="btn btn-sm" :href="data.classification.provenance?.source_url || 'https://data.pantherdb.org/PANTHER19.0/ontology/Protein_Class_19.0'" target="_blank" rel="noopener">PANTHER 分类来源 ↗</a></div></details>
    </template>
  </div>
</template>

<style scoped>

.coverage-page{max-width:1500px}.coverage-context{display:flex;justify-content:space-between;align-items:center;gap:24px;border-top:1px solid var(--border);padding:24px 0 14px}.coverage-context h2{font-size:22px;font-weight:500;margin:10px 0}.coverage-context p,.scope-explanation{font-size:12px;color:var(--muted);line-height:1.9}.coverage-context label{min-width:150px;font-size:11px;color:var(--muted)}select,input{display:block;width:100%;min-width:0;border:1px solid var(--border-strong);background:var(--card);color:var(--ink);padding:10px 12px;margin-top:8px;font:12px var(--font)}.scope-explanation{max-width:1000px;margin:10px 0 24px}.coverage-metrics{display:grid;grid-template-columns:repeat(3,1fr);background:var(--card);border:1px solid var(--border);margin:24px 0 32px}.coverage-metrics>div{padding:25px 28px;border-right:1px solid var(--border)}.coverage-metrics>div:last-child{border:0}.coverage-metrics span{font-size:11px;color:var(--muted)}.coverage-metrics strong{display:block;font:38px Georgia,serif;margin:16px 0 8px;color:var(--primary-strong)}.coverage-metrics small{font-size:21px;color:var(--muted)}.coverage-metrics p{margin:0;font-size:11px;color:var(--muted)}.coverage-tabs{display:flex;gap:32px;border-bottom:1px solid var(--border);margin-bottom:24px}.coverage-tabs button{border:0;background:transparent;border-bottom:2px solid transparent;color:var(--muted);font:14px var(--font);padding:14px 0;cursor:pointer}.coverage-tabs button.active{color:var(--primary);border-bottom-color:var(--primary)}.coverage-tabs small{font-size:11px;margin-left:8px}.catalogue-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px;align-items:start}.catalogue-list,.catalogue-detail{min-width:0;padding:24px}.catalogue-title{display:flex;align-items:start;justify-content:space-between;gap:16px}.catalogue-title h2,.catalogue-detail h2{font-size:19px;font-weight:500;margin:0 0 10px;overflow-wrap:anywhere}.catalogue-title p,.catalogue-detail p{font-size:11px;color:var(--muted);line-height:1.9}.catalogue-title .btn{flex:none}.catalogue-filters{display:flex;gap:16px;margin-top:24px}.catalogue-filters label{font-size:11px;color:var(--muted);flex:0 1 170px;min-width:0}.catalogue-filters .catalogue-search{flex:1}.catalogue-count{font-size:11px;color:var(--muted);margin:18px 0 10px}.table th{font-size:11px}.table td{font-size:12px}.table td:first-child{min-width:140px}.table-wrap{overflow-x:auto}.catalogue-link{background:transparent;border:0;padding:0;color:var(--primary);font:inherit;text-align:left;text-decoration:underline;text-underline-offset:3px;cursor:pointer;line-height:1.8}.symbol-alias{display:block;color:var(--muted);font-size:10px;margin-top:5px}.chosen{background:var(--primary-weak)}.coverage-state{display:inline-block;color:var(--muted);font-size:11px;padding:4px 7px;background:var(--surface-soft);font-weight:400;white-space:nowrap}.coverage-state.covered{color:var(--primary);background:var(--primary-weak)}.catalogue-detail{position:sticky;top:100px}.catalogue-detail>.eyebrow{display:block;margin-bottom:18px}.catalogue-detail h3{font-size:12px;font-weight:500;border-top:1px solid var(--border);padding-top:18px;margin:24px 0 12px}.association-link{display:block;width:100%;border:0;border-bottom:1px solid var(--border);padding:10px 0;background:transparent;color:var(--primary);font:11px var(--font);text-align:left;line-height:1.9;cursor:pointer}.catalogue-detail details{margin-top:20px;font-size:11px}.catalogue-detail summary,.coverage-method summary{cursor:pointer;color:var(--primary)}.gene-chips{display:flex;gap:6px;flex-wrap:wrap;font-size:11px;color:var(--muted)}.gene-chips button{border:1px solid var(--border);background:var(--primary-weak);color:var(--primary);font:11px Consolas,monospace;padding:5px 8px;cursor:pointer}.gene-chips.missing button{background:var(--surface-soft);color:var(--muted)}.coverage-method{margin-top:32px;padding:20px 0;border-top:1px solid var(--border);font-size:12px}.coverage-method p{color:var(--muted);line-height:1.9}.coverage-method code,.catalogue-detail .mono{overflow-wrap:anywhere}.coverage-loading{padding:45px}.coverage-loading h2{font-size:21px;font-weight:500}.coverage-loading p,.empty-result{font-size:12px;color:var(--muted)}@media(max-width:1100px){.catalogue-layout{grid-template-columns:minmax(0,1fr) 270px}.catalogue-filters{flex-wrap:wrap}.catalogue-filters .catalogue-search{flex-basis:100%}.catalogue-title{display:block}.catalogue-title .btn{margin-top:8px}}@media(max-width:800px){.catalogue-layout{grid-template-columns:1fr}.catalogue-detail{position:static}.coverage-metrics>div{padding:20px 16px}.coverage-metrics strong{font-size:30px}.coverage-metrics small{font-size:16px}.coverage-context{flex-wrap:wrap}}@media(max-width:480px){.coverage-metrics{grid-template-columns:1fr}.coverage-metrics>div{border-right:0;border-bottom:1px solid var(--border);display:grid;grid-template-columns:1fr 1fr;align-items:center;gap:8px}.coverage-metrics strong{grid-column:2;grid-row:1/3;margin:0}.coverage-metrics p{font-size:10px}.catalogue-list,.catalogue-detail{padding:18px}.coverage-tabs{gap:20px}.coverage-tabs button{font-size:12px}.catalogue-filters label{flex:1}.coverage-context h2{font-size:20px}}

.catalogue-filters .gene-class-filter{flex:1 1 300px}.class-english{display:block;font-size:10px;color:var(--muted);margin-top:5px;line-height:1.6}.task-search-label{display:block;font-size:11px;color:var(--muted);margin-top:24px}.task-guide-list{display:grid;gap:12px}.task-guide-card{display:block;width:100%;text-align:left;background:var(--card);border:1px solid var(--border);padding:18px 20px;cursor:pointer;color:var(--ink);font:12px var(--font)}.task-guide-card.chosen{border-color:var(--primary);background:var(--primary-weak)}.task-guide-card:hover{border-color:var(--primary)}.task-guide-title{display:block;font-size:16px;line-height:1.6}.task-guide-card>small{display:block;color:var(--primary);font-size:11px;line-height:1.8;margin:6px 0 12px}.task-guide-card p{font-size:12px;line-height:1.9;margin:8px 0}.task-guide-card p[lang=en]{font-size:11px;color:var(--muted)}.task-guide-genes{display:block;font:11px Consolas,monospace;color:var(--primary);margin-top:16px}.gene-class-explanation small{color:var(--primary);font-size:11px}.catalogue-detail>a{display:block;font-size:11px;line-height:1.9;margin-top:18px}.scope-explanation{max-width:1100px}.coverage-metrics strong{margin-bottom:12px}@media(max-width:480px){.task-guide-card{padding:16px}.task-guide-title{font-size:14px}.catalogue-filters .gene-class-filter{flex-basis:100%}.coverage-metrics strong{margin:0}}
</style>
