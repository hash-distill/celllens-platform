<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { dataCatalogApi, type Availability, type CatalogPair, type CatalogResponse } from '../api/dataCatalog'
import TablePager from '../components/TablePager.vue'
import MethodsPageHeader from '../components/MethodsPageHeader.vue'
import { downloadBlob } from '../utils/csv'

const route = useRoute()
const contexts = ['HepG2', 'Jurkat', 'K562', 'RPE1']
const cellLine = ref(contexts.includes(String(route.query.cell_line)) ? String(route.query.cell_line) : '')
const term = ref(typeof route.query.perturbation === 'string' ? route.query.perturbation : '')
const availability = ref<Availability>('all'), support = ref('all')
const page = ref(1), pageSize = ref(20)
const data = ref<CatalogResponse | null>(null), loading = ref(false), error = ref('')
const downloading = ref(false), downloadError = ref('')
let controller: AbortController | undefined, downloadController: AbortController | undefined
let timer: ReturnType<typeof setTimeout> | undefined
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / pageSize.value)))
function filters() {
  return { cell_line: cellLine.value || undefined, query: term.value.trim(), availability: availability.value,
    model_supported: support.value === 'all' ? undefined : support.value === 'yes' }
}
async function load() {
  controller?.abort()
  const current = controller = new AbortController()
  loading.value = true; error.value = ''
  try {
    const result = await dataCatalogApi.query({ ...filters(), limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value }, current.signal)
    if (!current.signal.aborted) data.value = result
  } catch (reason) {
    if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '数据目录读取失败'
  } finally { if (!current.signal.aborted) loading.value = false }
}
watch([cellLine, term, availability, support], () => {
  page.value = 1; controller?.abort(); clearTimeout(timer)
  timer = setTimeout(() => { void load() }, 200)
})
watch([page, pageSize], () => { clearTimeout(timer); void load() })
void load()
onBeforeUnmount(() => { clearTimeout(timer); controller?.abort(); downloadController?.abort() })
function destination(row: CatalogPair, path: string) {
  return { path: '/research', query: { type: path === '/measured' ? 'measured' : 'prediction', cell_line: row.cell_line, perturbation: row.perturbation } }
}
function splitName(value: string) {
  return value === 'test' ? '上游 test 候选' : value === 'val' ? '上游 val 候选'
    : value === 'unknown' ? '未核验' : '未声明留出'
}
async function download(missingOnly = false) {
  downloading.value = true; downloadError.value = ''
  downloadController?.abort(); downloadController = new AbortController()
  try {
    const result = await dataCatalogApi.download(missingOnly
      ? { availability: 'missing', model_supported: true }
      : filters(), downloadController.signal)
    downloadBlob(result.blob, missingOnly ? 'model-supported-without-source.csv' : result.filename)
  } catch (reason) { downloadError.value = reason instanceof Error ? reason.message : '目录下载失败' }
  finally { downloading.value = false }
}
</script>

<template>
  <div class="data-catalog-page">
    <MethodsPageHeader eyebrow="PUBLIC DATA / PERTURBATION COVERAGE" title="扰动数据目录" description="先查询公开实测，再选择直接分析或模型预测。"><RouterLink class="btn" to="/research">研究分析 ↗</RouterLink></MethodsPageHeader>
    <section class="catalog-boundary card">
      <div><strong>固定公开源 · State-Replogle-Filtered</strong><p>“本源无记录”仅指当前固定 filtered 版本，不代表其他研究中没有实测。源中的细胞数与本地已核验下载数分别列出。</p></div>
      <a v-if="data" :href="data.source.url" target="_blank" rel="noopener">查看公开来源 ↗</a>
    </section>
    <div v-if="error" class="notice notice-danger" role="alert">{{ error }} <button class="btn btn-sm" @click="load">重试</button></div>
    <template v-if="data">
      <p v-if="!data.source_verified" class="notice notice-warning" role="status">源索引缺失或核验未通过：覆盖状态为未知，请先检查源目录，不能按零细胞判断。</p>
      <section class="catalog-metrics" aria-label="四背景总体覆盖">
        <div><span>本源有实测的组合</span><strong>{{ data.source_verified ? data.summary.measured_pairs.toLocaleString() : '未知' }}</strong></div>
        <div><span>模型词表支持的组合</span><strong>{{ data.summary.model_supported_pairs.toLocaleString() }}</strong></div>
        <div><span>词表支持 · 本源无记录</span><strong>{{ data.summary.model_supported_unmeasured_pairs?.toLocaleString() ?? '未知' }}</strong></div>
        <div><span>本地已核验的组合</span><strong>{{ data.summary.local_verified_pairs }}</strong></div>
      </section>
      <details class="catalog-contexts"><summary>查看四种细胞背景的覆盖</summary><div class="table-wrap"><table class="table"><thead><tr><th>背景</th><th>本源细胞总数（含对照）</th><th>有实测的扰动</th><th>词表支持</th><th>支持且本源无记录</th></tr></thead><tbody><tr v-for="context in data.summary.contexts" :key="context.cell_line"><td>{{ context.cell_line }}</td><td>{{ context.source_total_cells?.toLocaleString() ?? '未知' }}</td><td>{{ data.source_verified ? context.measured_pairs : '未知' }}</td><td>{{ context.model_supported_pairs }}</td><td>{{ context.model_supported_unmeasured_pairs ?? '未知' }}</td></tr></tbody></table></div></details>
    </template>
    <section class="card catalog-table-card">
      <form class="catalog-filters" @submit.prevent="load">
        <label>细胞背景<select v-model="cellLine" aria-label="数据目录细胞背景"><option value="">全部四背景</option><option v-for="context in contexts" :key="context">{{ context }}</option></select></label>
        <label class="catalog-search">搜索扰动基因<input v-model="term" type="search" maxlength="64" placeholder="例如 ALDOA、ABHD11" aria-label="搜索扰动基因" /></label>
        <label>实测状态<select v-model="availability" aria-label="实测状态"><option value="all">全部</option><option value="measured">本源有实测</option><option value="missing">本源无记录</option><option value="unknown">源状态未知</option></select></label>
        <label>模型词表<select v-model="support" aria-label="模型词表支持"><option value="all">全部</option><option value="yes">支持</option><option value="no">不支持</option></select></label>
      </form>
      <div class="catalog-results-bar"><span role="status">{{ loading ? '正在读取…' : `匹配 ${data?.total.toLocaleString() ?? 0} 个组合` }}</span><div><button class="btn btn-sm" :disabled="downloading || !data" @click="download()">下载完整筛选 CSV</button><button class="btn btn-sm" :disabled="downloading || !data?.source_verified" @click="download(true)">下载全部支持但本源无记录组合</button></div></div>
      <p v-if="downloadError" class="notice notice-danger" role="alert">{{ downloadError }}</p>
      <div class="table-wrap" :aria-busy="loading"><table class="table catalog-pairs"><thead><tr><th>背景 / 扰动</th><th>本源实测细胞</th><th>本地已核验</th><th>模型词表</th><th>上游划分声明</th><th>分析入口</th></tr></thead><tbody><tr v-for="row in data?.items ?? []" :key="`${row.cell_line}-${row.perturbation}`"><td><strong class="mono">{{ row.perturbation }}</strong><small>{{ row.cell_line }}</small></td><td><span :class="{'catalog-measured':row.source_status==='measured'}">{{ row.source_status === 'unknown' ? '未知' : row.source_status === 'not_in_source' ? '本源无记录' : row.source_cell_count?.toLocaleString() }}</span></td><td>{{ row.local_verified ? `${row.local_measured_cells.toLocaleString()} 个细胞` : '未下载或未核验' }}</td><td>{{ row.model_supported ? '支持' : '不支持' }}</td><td>{{ splitName(row.official_split) }}</td><td class="catalog-actions"><RouterLink v-if="row.recommended_action==='measured'" class="btn btn-sm btn-primary" :to="destination(row, '/measured')">直接分析实测</RouterLink><RouterLink v-if="row.model_supported && row.source_status!=='unknown'" class="btn btn-sm" :to="destination(row, '/workbench')">{{ row.source_status === 'measured' ? '预测并评估' : '探索预测' }}</RouterLink><span v-if="row.recommended_action==='check_source'" class="muted">先核验来源</span><span v-else-if="row.recommended_action==='unsupported'" class="muted">当前模型不支持</span></td></tr></tbody></table></div>
      <p v-if="!loading && data && !data.items.length" class="catalog-empty">没有匹配的组合，请调整搜索或筛选条件。</p>
      <TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="data?.total ?? 0" />
    </section>
    <aside class="catalog-notes"><p>模型词表支持只表示可编码该目标，不代表泛化效果已验证。上游 test / val 是公开配置声明的候选，本项目尚未独立核实 checkpoint 训练排除与泛化结果。</p><p>旧 K562 本地评估列表仅含选取的部分目标；本目录采用四背景固定上游配置与全量 obs 计数。对照细胞用于来源总数核对，不作为扰动目标显示。</p></aside>
  </div>
</template>

<style scoped>
.data-catalog-page{max-width:1500px;margin:0 auto;padding:28px clamp(18px,3vw,48px) 48px}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:18px}.page-heading h2{margin:8px 0}.page-heading p,.catalog-boundary p{color:var(--muted);margin:8px 0;line-height:1.7}.catalog-boundary{display:flex;align-items:center;justify-content:space-between;gap:24px;margin:22px 0;padding:20px 24px}.catalog-boundary a{white-space:nowrap;color:var(--primary)}.catalog-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--border);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin:20px 0}.catalog-metrics>div{padding:20px 24px;background:var(--card)}.catalog-metrics span{display:block;color:var(--muted);font-size:12px}.catalog-metrics strong{display:block;font-size:27px;font-weight:600;margin-top:12px;font-variant-numeric:tabular-nums}.catalog-contexts{margin:0 0 22px;color:var(--muted)}.catalog-contexts summary{cursor:pointer;padding:8px 0}.catalog-table-card{padding:24px}.catalog-filters{display:grid;grid-template-columns:1fr 1.7fr 1fr 1fr;gap:16px}.catalog-filters label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:8px}.catalog-filters select,.catalog-filters input{width:100%;min-width:0;padding:10px 12px;border:1px solid var(--border);border-radius:5px;background:var(--field-bg);color:var(--ink);font:inherit;font-size:13px}.catalog-results-bar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin:24px 0 14px;color:var(--muted);font-size:12px}.catalog-results-bar>div{display:flex;gap:8px;flex-wrap:wrap}.catalog-pairs{min-width:920px}.catalog-pairs td{vertical-align:middle}.catalog-pairs td small{display:block;margin-top:6px;color:var(--muted);font-size:11px}.catalog-pairs th{white-space:nowrap}.catalog-measured{color:var(--primary);font-weight:600}.catalog-actions{white-space:nowrap}.catalog-actions a+a{margin-left:7px}.catalog-notes{font-size:12px;color:var(--muted);line-height:1.8;padding:12px 2px}.catalog-empty{padding:25px;text-align:center;color:var(--muted)}@media(max-width:1000px){.catalog-filters{grid-template-columns:1fr 1fr}.catalog-metrics{grid-template-columns:repeat(2,1fr)}.catalog-results-bar,.catalog-boundary{align-items:flex-start;flex-direction:column}}@media(max-width:600px){.catalog-filters{grid-template-columns:1fr}.page-heading{align-items:flex-start;flex-direction:column}.catalog-table-card{padding:16px}.catalog-metrics>div{padding:16px}.catalog-metrics strong{font-size:22px}}
</style>

<style scoped>
.data-catalog-page{max-width:1400px;padding:28px 32px 56px}
</style>
