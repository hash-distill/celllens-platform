<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../api/client'
import { ApiError } from '../api/http'
import type { CompletenessResponse } from '../types/completeness'
import { fmtPercent } from '../utils/format'
import { usePagedRows } from '../utils/pagination'
import TablePager from './TablePager.vue'

const props = defineProps<{ runId: string; available?: boolean; selectedTask?: string }>()
const emit = defineEmits<{ loaded: [report: CompletenessResponse | null] }>()
const data = ref<CompletenessResponse | null>(null)
const loading = ref(false)
const error = ref<ApiError | null>(null)
const query = ref('')
const selected = ref('')
let controller: AbortController | undefined
const summary = computed(() => data.value?.overall_summary)
const filtered = computed(() => (data.value?.tasks ?? []).filter(row => row.id.toLowerCase().includes(query.value.trim().toLowerCase())))
const { page, pages, visible } = usePagedRows(filtered)
const detail = computed(() => data.value?.tasks.find(row => row.id === selected.value))
const emptyEssential = computed(() => data.value?.tasks.filter(row => row.n_genes_essential === 0).length ?? 0)
async function load() {
  controller?.abort()
  const active = new AbortController(); controller = active
  data.value = null; error.value = null; selected.value = ''; query.value = ''; emit('loaded', null)
  loading.value = false
  if (props.available !== true) return
  loading.value = true
  try {
    const result = await api.getCompleteness(props.runId, active.signal)
    if (active.signal.aborted || result.run_id !== props.runId) return
    data.value = result; emit('loaded', result)
    selected.value = props.selectedTask || result.tasks[0]?.id || ''
  } catch (err) {
    if (!active.signal.aborted) error.value = err instanceof ApiError ? err : new ApiError({ kind: 'network', status: null, code: null, message: '官方完整性报告读取失败', endpoint: '/completeness' })
  } finally { if (!active.signal.aborted) loading.value = false }
}
watch(() => [props.runId, props.available], load, { immediate: true })
watch(() => props.selectedTask, id => { if (id && data.value?.tasks.some(row => row.id === id)) selected.value = id })
onBeforeUnmount(() => controller?.abort())
function download() {
  if (!data.value) return
  const url = URL.createObjectURL(new Blob([JSON.stringify(data.value, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = `${props.runId}-official-completeness.json`; anchor.click(); URL.revokeObjectURL(url)
}
</script>

<template>
  <section class="official-completeness" aria-label="scCellFie 官方完整性分析">
    <div class="official-heading"><h3>scCellFie 官方完整性分析</h3><a href="https://sccellfie.readthedocs.io/en/latest/api/index.html#reports" target="_blank" rel="noopener">方法说明 ↗</a></div>
    <p v-if="loading" role="status">正在读取本次运行的官方完整性报告…</p>
    <div v-else-if="error" class="notice notice-danger" role="alert">{{ error.message }}<button class="btn btn-sm" @click="load">重试</button></div>
    <p v-else-if="!data" class="muted small" role="status">{{ available === undefined ? '等待任务结果…' : '本次保存结果未提供官方完整性报告。已有项目分档保留为历史信息。' }}</p>
    <template v-else>
      <p class="small muted">基于本次预测的 {{ data.panel_gene_count }} 个基因和完整冻结数据库计算。完整性衡量数据可用范围，不代表预测准确率或实验验证。</p>
      <div class="official-cards">
        <div><strong>{{ summary?.n_genes_in_db_present_in_adata }} / {{ summary?.n_genes_in_db_total }}</strong><span>代谢库基因覆盖</span><small>{{ fmtPercent(summary?.fraction_db_genes_present, 1) }}</small></div>
        <div><strong>{{ summary?.n_tasks_fully_covered_all }} / {{ summary?.n_tasks_total }}</strong><span>全部关联基因完整覆盖的任务</span><small>官方统计，不使用 80%／60% 分档</small></div>
        <div><strong>{{ fmtPercent(summary?.mean_task_impact_weighted_all, 1) }}</strong><span>任务平均影响加权完整性</span><small>官方单基因消融参考下的指标</small></div>
        <div><strong>{{ summary?.n_reactions_fully_covered_all }} / {{ summary?.n_reactions_total }}</strong><span>全部关联基因完整覆盖的反应</span><small>不等于实际反应发生比例</small></div>
      </div>
      <details class="official-details"><summary>查看全部 {{ data.tasks.length }} 项任务的完整性与缺失基因</summary>
        <p class="small muted">关键基因由官方统一参考中的单基因消融定义。{{ emptyEssential }} 项任务未识别到单基因必需项，此时官方返回的 100% 不作为完整证据展示；多个替代基因共同缺失仍可能影响评分。</p>
        <input v-model="query" class="input" aria-label="搜索官方完整性任务" placeholder="搜索任务名称" />
        <div class="table-wrap"><table class="data-table"><thead><tr><th>任务</th><th>全部基因覆盖</th><th>关键基因覆盖</th><th>影响加权完整性</th></tr></thead><tbody>
          <tr v-for="row in visible" :key="row.id" class="official-task-row"><td><button class="task-link" @click="selected = row.id">{{ row.id }}</button></td><td>{{ row.n_present_all }} / {{ row.n_genes_all }} · {{ fmtPercent(row.fraction_present_all, 1) }}</td><td>{{ row.n_genes_essential ? `${row.n_present_essential} / ${row.n_genes_essential}` : '无单基因必需项' }}</td><td>{{ fmtPercent(row.impact_weighted_completeness_all, 1) }}</td></tr>
        </tbody></table></div>
        <p v-if="!filtered.length" role="status">没有匹配的任务。</p>
        <TablePager v-model:page="page" :pages="pages" :total="filtered.length" />
        <div v-if="detail" class="official-missing"><strong>{{ detail.id }}</strong><p>缺失关联基因（{{ detail.n_missing_all }}）：{{ detail.missing_genes_all || '无' }}</p><p>缺失关键基因（{{ detail.n_missing_essential }}）：{{ detail.missing_genes_essential || (detail.n_genes_essential ? '无' : '未识别到单基因必需项') }}</p></div>
      </details>
      <details class="official-provenance"><summary>方法版本与来源 · 下载官方报告</summary><p>{{ data.method }} · scCellFie {{ data.package_version }} · {{ data.database_version }}</p><p>参数：metric={{ data.parameters.metric }}，threshold={{ data.parameters.threshold }}；数据集级完整性，不以单细胞零表达判断基因缺失。</p><p>预测面板文件 SHA-256：<code>{{ data.source_gene_sha256 }}</code></p><p>冻结数据库清单 SHA-256：<code>{{ data.database_provenance.manifest_sha256 }}</code></p><p class="small muted">影响加权指标基于官方均一参考，单基因影响累加不能证明多个缺失基因的联合效应。</p><button class="btn btn-sm" @click="download">下载完整 JSON（含反应明细）</button></details>
    </template>
  </section>
</template>

<style scoped>
.official-completeness{margin:18px 0;padding:18px;border:1px solid var(--border-strong);background:var(--card);min-width:0}.official-heading{display:flex;gap:12px;justify-content:space-between;align-items:center}.official-heading h3{font-size:15px;margin:0}.official-heading a{font-size:11px;white-space:nowrap}.official-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.official-cards>div{display:flex;flex-direction:column;gap:7px;border-left:2px solid var(--surface-tint-border);padding:5px 12px}.official-cards strong{font-size:22px;font-weight:500}.official-cards span{font-size:12px}.official-cards small{font-size:10px;color:var(--muted)}details{font-size:12px;padding:12px 0;border-top:1px solid var(--border)}summary{cursor:pointer;color:var(--primary)}.official-details .input{margin:12px 0;max-width:360px}.task-link{border:0;background:transparent;font:inherit;color:var(--primary);text-align:left;cursor:pointer;text-decoration:underline}.official-missing{background:var(--coverage-bg);padding:14px;margin-top:12px;overflow-wrap:anywhere}.official-provenance code{overflow-wrap:anywhere}.official-provenance p{line-height:1.7}.data-table td{white-space:normal;min-width:120px}.data-table td:first-child{min-width:190px}@media(max-width:800px){.official-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:420px){.official-completeness{padding:12px}.official-cards strong{font-size:18px}}
</style>
