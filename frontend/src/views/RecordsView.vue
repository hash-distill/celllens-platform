<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { accessSession } from '../stores/access'
import { listResearchRecords } from '../api/researchRecords'
import { isMockEnabled } from '../api/mockFlag'
import UiIcon from '../components/UiIcon.vue'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
import { selectRecords, type ResearchRecord, type RecordCategory, type RecordStatusFilter } from '../utils/researchRecords'

const route = useRoute(), router = useRouter()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const records = ref<ResearchRecord[]>([]), loading = ref(false), error = ref('')
const search = ref('')
const mock = isMockEnabled()
const category = computed<RecordCategory>(() => ['measured', 'predicted'].includes(String(route.query.category))
  ? route.query.category as RecordCategory : route.query.view === 'measured' ? 'measured' : 'all')
const status = computed<RecordStatusFilter>(() => ['active', 'completed', 'failed', 'cancelled', 'interrupted'].includes(String(route.query.status)) ? route.query.status as RecordStatusFilter : 'all')
const limit = computed(() => [10, 20, 50, 100].includes(Number(route.query.size)) ? Number(route.query.size) : 20)
const filtered = computed(() => selectRecords(records.value, {
  category: category.value, status: status.value, resultsOnly: false,
  query: typeof route.query.q === 'string' ? route.query.q : '',
}))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / limit.value)))
const page = computed(() => {
  const requested = Number(route.query.page)
  return Number.isInteger(requested) && requested > 0 ? Math.min(requested, pageCount.value) : 1
})
const visibleRecords = computed(() => filtered.value.slice((page.value - 1) * limit.value, page.value * limit.value))
const counts = computed(() => ({
  all: records.value.length,
  completed: records.value.filter(record => record.status === 'completed').length,
  active: records.value.filter(record => !['completed', 'failed', 'cancelled', 'interrupted'].includes(record.status)).length,
  failed: records.value.filter(record => record.status === 'failed').length,
}))
const labels: Record<string, string> = { ...STATUS_LABEL, queued: '等待执行', preparing: '准备数据', analysing: '分析中', completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断' }
let controller: AbortController | undefined

async function load() {
  controller?.abort()
  const current = controller = new AbortController()
  loading.value = true
  error.value = ''
  try {
    const result = await listResearchRecords(current.signal)
    if (!current.signal.aborted) records.value = result
  } catch (reason) {
    if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '实验记录读取失败'
  } finally {
    if (!current.signal.aborted) loading.value = false
  }
}

// Preserve bookmarked completed-result links as an ordinary status filter.
watch(() => route.query.view, view => {
  if (view === 'results') void router.replace({ path: '/records', query: { ...route.query, view: undefined, status: route.query.status ?? 'completed' }, hash: route.hash })
}, { immediate: true })
watch(() => route.query.q, value => { search.value = typeof value === 'string' ? value : '' }, { immediate: true })
onMounted(load)
onBeforeUnmount(() => controller?.abort())
function applyFilters() {
  void router.push({ path: '/records', query: { ...route.query, page: undefined, q: search.value.trim() || undefined } })
}
function changeFilter(key: 'category' | 'status' | 'size', event: Event) {
  const value = (event.target as HTMLSelectElement).value
  void router.push({ path: '/records', query: {
    ...route.query, view: undefined,
    category: category.value === 'all' ? undefined : category.value,
    page: undefined, [key]: value === 'all' ? undefined : value,
  } })
}
function movePage(value: number) {
  void router.push({ path: '/records', query: { ...route.query, page: value === 1 ? undefined : String(value) } })
}
</script>

<template>
  <div class="page records-page national-page">
    <header class="page-heading">
      <div><span class="eyebrow">EXPERIMENT RECORDS</span><h1>{{ readOnly ? '已发布研究案例' : '实验记录' }}</h1><p>{{ readOnly ? '仅包含部署者登记的冻结案例，不代表工作区完整实验历史。' : '从一次运行到一份发现，保存每个研究问题的参数、状态与结果。' }}</p></div>
      <RouterLink :to="readOnly?'/data-catalog':'/research'" class="btn btn-primary">{{readOnly?'案例覆盖子集':'新建分析'}} <UiIcon name="arrow" :size="15"/></RouterLink>
    </header>
    <section class="record-overview" aria-label="全部研究记录状态汇总"><div class="record-overview-title"><span class="eyebrow">RESEARCH LEDGER</span><strong>研究持续推进，<br>每一步都留下记录。</strong></div><div class="record-overview-numbers"><RouterLink to="/records"><strong>{{ loading || error ? '—' : counts.all }}</strong><span>全部研究</span></RouterLink><RouterLink to="/records?status=completed"><strong>{{ loading || error ? '—' : counts.completed }}</strong><span>已完成</span></RouterLink><RouterLink to="/records?status=active"><strong>{{ loading || error ? '—' : counts.active }}</strong><span>进行中</span></RouterLink><RouterLink to="/records?status=failed"><strong>{{ loading || error ? '—' : counts.failed }}</strong><span>失败</span></RouterLink></div><div class="record-overview-art" aria-hidden="true"><svg viewBox="0 0 120 85"><g fill="none" stroke="currentColor" stroke-width="1.2"><path d="M12 42h30l17-24 19 49 18-25h14"/><path d="M17 15v57h90" opacity=".4"/><path d="M18 29h90M18 57h90" stroke-dasharray="2 4" opacity=".3"/></g><g fill="currentColor"><circle cx="42" cy="42" r="3"/><circle cx="59" cy="18" r="3"/><circle cx="78" cy="67" r="3"/></g></svg><span>参数 · 运行 · 结果</span></div></section>
    <div class="records-section-heading"><h2>研究运行清单</h2></div>
    <section class="records-panel" aria-label="实验记录列表">
      <form class="record-filters" @submit.prevent="applyFilters">
        <div class="search-field"><label class="label" for="record-search">检索实验</label><input id="record-search" v-model="search" class="input" maxlength="128" placeholder="搜索细胞背景、扰动基因或编号" /></div>
        <div><label class="label" for="record-category">类别</label><select id="record-category" :value="category" class="select" @change="changeFilter('category', $event)"><option value="all">全部类别</option><option value="measured">实测分析</option><option value="predicted">模型预测</option></select></div>
        <div><label class="label" for="record-status">运行状态</label><select id="record-status" :value="status" class="select" @change="changeFilter('status', $event)"><option value="all">全部状态</option><option value="active">进行中</option><option value="completed">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option></select></div>
        <button class="btn btn-primary" type="submit">检索</button><button class="btn" type="button" :disabled="loading" @click="load">刷新记录</button>
      </form>
      <div class="records-count"><span>{{ loading ? '正在读取…' : error ? '记录读取失败' : '共 ' + filtered.length + ' 条实验记录' }}</span><span>按创建时间倒序{{ mock ? ' · 合成示例' : '' }}</span></div>
      <div v-if="error" class="records-empty" role="alert"><h2>实验记录读取失败</h2><p>{{ error }}</p><button class="btn" @click="load">重试记录</button></div>
      <div v-else-if="loading" class="records-empty" role="status">正在加载实验记录…</div>
      <div v-else-if="!filtered.length" class="records-empty"><h2>暂无符合条件的实验记录</h2><p>{{readOnly?'公开展览仅展示白名单中的冻结案例，可调整筛选条件。':'可调整筛选条件，或新建研究分析后再查看。'}}</p><RouterLink :to="readOnly ? '/records' : '/research'" class="btn">{{ readOnly ? '查看全部已发布案例' : '新建研究分析' }}</RouterLink></div>
      <div v-else class="records-table-wrap">
        <table class="records-table"><thead><tr><th scope="col">实验</th><th scope="col">类别 / 来源</th><th scope="col">运行状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead>
          <tbody><tr v-for="record in visibleRecords" :key="record.key" :data-record-kind="record.category" :data-record-id="record.id">
            <td><RouterLink :to="record.target" class="record-title">{{ record.title }}</RouterLink><span class="record-id mono">{{ record.id }}</span><small>{{ record.subtitle }}</small></td>
            <td><span class="record-source" :class="record.category">{{ record.category === 'measured' ? '实测分析' : '模型预测' }}</span><small v-if="record.sourceLabel !== (record.category === 'measured' ? '实测分析' : '模型预测')">{{ record.sourceLabel }}</small></td>
            <td><span class="record-status" :class="record.status">{{ labels[record.status] ?? record.status }}</span><small v-if="!['completed', 'failed', 'cancelled', 'interrupted'].includes(record.status)">进度 {{ record.progress }}%</small></td>
            <td class="record-time">{{ fmtServerTime(record.createdAt) }}</td>
            <td><RouterLink v-if="record.status === 'completed'" :to="record.target" class="btn btn-sm">打开工作台 <UiIcon name="arrow" :size="13"/></RouterLink><template v-else><RouterLink :to="record.target" class="btn btn-sm">查看运行 <UiIcon name="arrow" :size="13"/></RouterLink><small>尚无完整结果</small></template></td>
          </tr></tbody>
        </table>
      </div>
      <footer v-if="!error && !loading && filtered.length" class="record-pagination"><span>第 {{ page }} / {{ pageCount }} 页</span><div class="btn-row"><label class="sr-only" for="record-size">每页条数</label><select id="record-size" :value="limit" class="select" style="width:auto;font-size:10px" @change="changeFilter('size', $event)"><option value="10">10 条 / 页</option><option value="20">20 条 / 页</option><option value="50">50 条 / 页</option><option value="100">100 条 / 页</option></select><button class="btn btn-sm" :disabled="page === 1" @click="movePage(page - 1)">上一页</button><button class="btn btn-sm" :disabled="page >= pageCount" @click="movePage(page + 1)">下一页</button></div></footer>
    </section>
    <aside class="record-explanation"><UiIcon name="file" :size="17"/><p>实测分析和模型预测分别保留数据身份。打开研究可查看当前状态、输入参数与已有产物；完整结果中的图表、来源和导出始终关联同一条记录。</p><RouterLink to="/about">了解研究流程 ↗</RouterLink></aside>
  </div>
</template>

<style scoped>
.records-page{max-width:1440px}.page-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.record-overview{display:flex;align-items:center;gap:30px;background:linear-gradient(110deg,var(--surface-tint-strong),var(--surface-tint));border:1px solid var(--surface-tint-border);border-radius:17px;padding:24px 28px;margin-bottom:25px;overflow:hidden}.record-overview-title{min-width:220px}.record-overview-title .eyebrow{display:block;font-size:9px!important;color:var(--muted);margin-bottom:12px}.record-overview-title>strong{display:block;font-size:18px;font-weight:500;line-height:1.65;color:var(--ink)}.record-overview-numbers{display:grid;grid-template-columns:repeat(4,1fr);gap:27px;flex:1;max-width:610px}.record-overview-numbers a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;text-decoration:none;border-left:1px solid var(--surface-tint-border-strong);min-height:65px;padding-left:23px}.record-overview-numbers strong{font:31px Bahnschrift,sans-serif;color:var(--primary-strong)}.record-overview-numbers span{font-size:10px;color:var(--muted);white-space:nowrap}.record-overview-art{width:130px;margin-left:auto;color:var(--primary);opacity:.5;text-align:center;flex:none}.record-overview-art svg{width:120px;height:75px}.record-overview-art span{display:block;font-size:8px;letter-spacing:2px}.records-section-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin:26px 1px 16px}.records-section-heading h2{font-size:18px;font-weight:500;margin:0}.record-text-link{display:inline-flex;align-items:center;gap:6px;text-decoration:none;font-size:11px;color:var(--primary)}.records-panel{background:var(--card);border:1px solid var(--border);border-radius:15px!important;overflow:hidden}.record-filters{display:flex;gap:14px;align-items:end;padding:24px;flex-wrap:wrap}.search-field{flex:1;min-width:200px}.record-filters .label{font-size:11px}.record-filters .input,.record-filters .select{font-size:12px;min-height:39px;border-radius:8px!important}.record-filters .select{min-width:120px}.record-filters .btn{min-height:39px;font-size:12px}.records-count{display:flex;justify-content:space-between;gap:15px;border-top:1px solid var(--border);padding:15px 24px;color:var(--muted);font-size:11px}.records-count>span:first-child{color:var(--primary)}.records-table-wrap{overflow-x:auto}.records-table{width:100%;border-collapse:collapse;text-align:left;min-width:770px}.records-table th{background:var(--table-head-bg);color:var(--muted);font-size:11px;font-weight:500;padding:14px 20px;white-space:nowrap}.records-table td{padding:20px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle}.records-table td:last-child{min-width:140px}.records-table .btn{white-space:nowrap}.record-title{display:block;font-size:14px;font-weight:500;min-width:180px;text-decoration:none}.record-id{display:block;font-size:10px;color:var(--faint);margin:7px 0;overflow-wrap:anywhere;max-width:290px}.records-table small{display:block;font-size:10px;color:var(--muted);margin-top:7px;line-height:1.6}.record-source{display:inline-block!important;font-size:10px!important;white-space:nowrap;border:1px solid var(--surface-tint-border);border-radius:5px;padding:4px 7px;background:var(--primary-weak);color:var(--primary)}.record-source.predicted{border-color:var(--border);background:var(--surface-tint);color:var(--primary)}.record-time{max-width:180px;font-size:11px!important;line-height:1.8;color:var(--muted)}.record-status{display:inline-block;padding:4px 8px;background:var(--surface-tint);font-size:11px;color:var(--primary);white-space:nowrap;border-radius:5px}.record-status.failed,.record-status.interrupted{color:var(--danger);background:var(--danger-bg)}.record-status.completed{background:var(--ok-bg);color:var(--ok)}.record-status.cancelled{background:var(--card-soft);color:var(--muted)}.records-empty{text-align:center;padding:55px 24px;color:var(--muted);font-size:12px}.records-empty h2{font-size:20px;font-weight:500;color:var(--ink)}.records-empty p{margin:15px 0 24px;overflow-wrap:anywhere}.record-pagination{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;gap:12px;font-size:11px;color:var(--muted)}.record-explanation{display:flex;align-items:center;gap:13px;color:var(--muted);margin-top:21px;padding:0 2px}.record-explanation>svg{flex:none;color:var(--primary)}.record-explanation p{font-size:11px;line-height:1.9;max-width:900px;margin:0}.record-explanation a{margin-left:auto;white-space:nowrap;font-size:10px;color:var(--primary);text-decoration:none}
@media(max-width:1100px){.record-overview-art{display:none}.record-overview-title{min-width:200px}.record-overview{gap:15px}.record-overview-numbers{gap:15px}.record-overview-numbers a{padding-left:15px}}@media(max-width:800px){.record-overview{flex-direction:column;align-items:stretch;padding:23px}.record-overview-title>strong br{display:none}.record-overview-title .eyebrow{margin-bottom:8px}.record-overview-numbers{max-width:none;margin-top:7px}.record-overview-numbers a{padding:0}.record-overview-numbers a:first-child{border:0}.record-overview-numbers strong{font-size:28px}.record-explanation{align-items:flex-start}.record-explanation a{display:none}.record-filters .select{min-width:100px}.record-filters .search-field{flex-basis:100%}}@media(max-width:500px){.page-heading>.btn{white-space:nowrap;font-size:11px!important;padding:9px!important}.record-overview{padding:20px}.record-overview-title>strong{font-size:16px}.record-overview-numbers{gap:10px}.record-overview-numbers strong{font-size:25px}.record-overview-numbers span{font-size:9px}.records-section-heading h2{font-size:16px}.record-text-link{font-size:10px}.record-filters{padding:17px!important;gap:10px!important}.record-filters>div:not(.search-field){flex:1}.record-filters .select{width:100%;min-width:0}.record-filters .btn{flex:1;min-width:90px}.records-count{font-size:10px!important;padding:13px 17px!important}.record-pagination{padding:15px!important;flex-wrap:wrap}.record-pagination .btn-row{gap:6px}.record-pagination .btn{font-size:10px!important}.record-explanation p{font-size:10px}.records-empty{padding:40px 20px}.records-empty h2{font-size:17px}}
</style>
