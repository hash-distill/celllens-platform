<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listResearchRecords } from '../api/researchRecords'
import { isMockEnabled } from '../api/mockFlag'
import { STATUS_LABEL, fmtServerTime } from '../utils/format'
import { selectRecords, type ResearchRecord, type RecordCategory, type RecordStatusFilter } from '../utils/researchRecords'

const route = useRoute(), router = useRouter()
const records = ref<ResearchRecord[]>([]), loading = ref(false), error = ref('')
const search = ref('')
const mock = isMockEnabled()
const resultsOnly = computed(() => route.query.view === 'results')
const category = computed<RecordCategory>(() => ['measured', 'predicted'].includes(String(route.query.category))
  ? route.query.category as RecordCategory : route.query.view === 'measured' ? 'measured' : 'all')
const status = computed<RecordStatusFilter>(() => resultsOnly.value ? 'completed'
  : ['active', 'completed', 'failed', 'cancelled', 'interrupted'].includes(String(route.query.status)) ? route.query.status as RecordStatusFilter : 'all')
const limit = computed(() => [10, 20, 50, 100].includes(Number(route.query.size)) ? Number(route.query.size) : 20)
const filtered = computed(() => selectRecords(records.value, {
  category: category.value, status: status.value, resultsOnly: resultsOnly.value,
  query: typeof route.query.q === 'string' ? route.query.q : '',
}))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / limit.value)))
const page = computed(() => {
  const requested = Number(route.query.page)
  return Number.isInteger(requested) && requested > 0 ? Math.min(requested, pageCount.value) : 1
})
const visibleRecords = computed(() => filtered.value.slice((page.value - 1) * limit.value, page.value * limit.value))
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

watch(() => route.query.q, value => { search.value = typeof value === 'string' ? value : '' }, { immediate: true })
onMounted(load)
onBeforeUnmount(() => controller?.abort())
function applyFilters() {
  void router.push({ path: '/records', query: { ...route.query, page: undefined, q: search.value.trim() || undefined } })
}
function changeFilter(key: 'category' | 'status' | 'size', event: Event) {
  const value = (event.target as HTMLSelectElement).value
  void router.push({ path: '/records', query: {
    ...route.query, view: resultsOnly.value ? 'results' : undefined,
    category: category.value === 'all' ? undefined : category.value,
    page: undefined, [key]: value === 'all' ? undefined : value,
  } })
}
function movePage(value: number) {
  void router.push({ path: '/records', query: { ...route.query, page: value === 1 ? undefined : String(value) } })
}
</script>

<template>
  <div class="page records-page">
    <header class="page-heading">
      <div><span class="eyebrow">{{ resultsOnly ? 'RESULT INTERPRETATION' : 'EXPERIMENT RECORDS' }}</span><h1>{{ resultsOnly ? '结果解读' : '实验记录' }}</h1><p>{{ resultsOnly ? '选择已完成的实测分析或模型预测，查看图表、关键变化与证据。' : '实测分析与模型预测统一查看，按类别和状态筛选。' }}</p></div>
      <RouterLink to="/research" class="btn btn-primary">新建研究分析</RouterLink>
    </header>
    <section class="records-panel" aria-label="实验记录列表">
      <form class="record-filters" @submit.prevent="applyFilters">
        <div class="search-field"><label class="label" for="record-search">检索实验</label><input id="record-search" v-model="search" class="input" maxlength="128" placeholder="搜索细胞背景、扰动基因或编号" /></div>
        <div><label class="label" for="record-category">类别</label><select id="record-category" :value="category" class="select" @change="changeFilter('category', $event)"><option value="all">全部类别</option><option value="measured">实测分析</option><option value="predicted">模型预测</option></select></div>
        <div v-if="!resultsOnly"><label class="label" for="record-status">运行状态</label><select id="record-status" :value="status" class="select" @change="changeFilter('status', $event)"><option value="all">全部状态</option><option value="active">进行中</option><option value="completed">已完成</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option></select></div>
        <button class="btn btn-primary" type="submit">检索</button><button class="btn" type="button" :disabled="loading" @click="load">刷新记录</button>
      </form>
      <div class="records-count"><span>{{ loading ? '正在读取…' : error ? '记录读取失败' : '共 ' + filtered.length + ' 条' + (resultsOnly ? '已完成结果' : '实验记录') }}</span><span>按创建时间倒序{{ mock ? ' · 合成示例' : '' }}</span></div>
      <div v-if="error" class="records-empty" role="alert"><h2>实验记录读取失败</h2><p>{{ error }}</p><button class="btn" @click="load">重试记录</button></div>
      <div v-else-if="loading" class="records-empty" role="status">正在加载实验记录…</div>
      <div v-else-if="!filtered.length" class="records-empty"><h2>{{ resultsOnly ? '暂无符合条件的已完成结果' : '暂无符合条件的实验记录' }}</h2><p>可调整筛选条件，或新建研究分析后再查看。</p><RouterLink :to="resultsOnly ? '/records' : '/research'" class="btn">{{ resultsOnly ? '查看全部实验记录' : '新建研究分析' }}</RouterLink></div>
      <div v-else class="records-table-wrap">
        <table class="records-table"><thead><tr><th scope="col">实验</th><th scope="col">类别 / 来源</th><th scope="col">运行状态</th><th scope="col">创建时间</th><th scope="col">操作</th></tr></thead>
          <tbody><tr v-for="record in visibleRecords" :key="record.key" :data-record-kind="record.category" :data-record-id="record.id">
            <td><RouterLink :to="record.target" class="record-title">{{ record.title }}</RouterLink><span class="record-id mono">{{ record.id }}</span><small>{{ record.subtitle }}</small></td>
            <td><span class="record-source">{{ record.category === 'measured' ? '实测分析' : '模型预测' }}</span><small v-if="record.sourceLabel !== (record.category === 'measured' ? '实测分析' : '模型预测')">{{ record.sourceLabel }}</small></td>
            <td><span class="record-status" :class="record.status">{{ labels[record.status] ?? record.status }}</span><small v-if="!['completed', 'failed', 'cancelled', 'interrupted'].includes(record.status)">进度 {{ record.progress }}%</small></td>
            <td class="record-time">{{ fmtServerTime(record.createdAt) }}</td>
            <td><RouterLink v-if="record.status === 'completed'" :to="record.target" class="btn btn-sm">结果解读</RouterLink><template v-else><button class="btn btn-sm" disabled>结果解读</button><small>尚无完整结果，点击实验名称查看状态</small></template></td>
          </tr></tbody>
        </table>
      </div>
      <footer v-if="!error && !loading && filtered.length" class="record-pagination"><span>第 {{ page }} / {{ pageCount }} 页</span><div class="btn-row"><label class="sr-only" for="record-size">每页条数</label><select id="record-size" :value="limit" class="select" style="width:auto;font-size:10px" @change="changeFilter('size', $event)"><option value="10">10 条 / 页</option><option value="20">20 条 / 页</option><option value="50">50 条 / 页</option><option value="100">100 条 / 页</option></select><button class="btn btn-sm" :disabled="page === 1" @click="movePage(page - 1)">上一页</button><button class="btn btn-sm" :disabled="page >= pageCount" @click="movePage(page + 1)">下一页</button></div></footer>
    </section>
  </div>
</template>

<style scoped>
.records-panel{background:var(--card);border:1px solid var(--border)}
.record-filters{display:flex;gap:12px;align-items:end;padding:24px;flex-wrap:wrap}.search-field{flex:1;min-width:200px}.record-filters .label{font-size:11px}.record-filters .input,.record-filters .select{font-size:12px;min-height:38px}.record-filters .select{min-width:120px}.record-filters .btn{min-height:38px;font-size:12px}
.records-count{display:flex;justify-content:space-between;gap:15px;border-top:1px solid var(--border);padding:15px 24px;color:var(--muted);font-size:11px}.records-count>span:first-child{color:var(--primary)}
.records-table-wrap{overflow-x:auto}.records-table{width:100%;border-collapse:collapse;text-align:left}.records-table th{background:var(--table-head-bg);color:var(--muted);font-size:11px;font-weight:500;padding:12px 20px;white-space:nowrap}.records-table td{padding:20px;border-bottom:1px solid var(--border);font-size:12px;vertical-align:middle}.records-table td:last-child{min-width:140px}.records-table .btn{white-space:nowrap}
.record-title{display:block;font-size:14px;font-weight:500;min-width:180px}.record-id{display:block;font-size:10px;color:var(--muted);margin:7px 0;overflow-wrap:anywhere}.records-table small{display:block;font-size:11px;color:var(--muted);margin-top:7px;line-height:1.6}.record-source{display:block;font-size:12px;white-space:nowrap}.record-time{max-width:180px;font-size:11px!important;line-height:1.8;color:var(--muted)}
.record-status{display:inline-block;padding:4px 8px;background:var(--surface-tint);font-size:11px;color:var(--primary);white-space:nowrap}.record-status.failed{color:var(--danger);background:var(--danger-bg)}.record-status.completed{background:var(--ok-bg);color:var(--ok)}
.records-empty{text-align:center;padding:55px 24px;color:var(--muted);font-size:12px}.records-empty h2{font-size:20px;font-weight:500;color:var(--ink)}.records-empty p{margin:15px 0 24px}.record-pagination{display:flex;align-items:center;justify-content:space-between;padding:18px 24px;gap:12px;font-size:11px;color:var(--muted)}
</style>
