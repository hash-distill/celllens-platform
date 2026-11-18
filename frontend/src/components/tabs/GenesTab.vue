<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useRunStore } from '../../stores/run'
import { useUiStore } from '../../stores/ui'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import ExpressionResponseGallery from '../ExpressionResponseGallery.vue'
import { accessSession } from '../../stores/access'
import { fmtDelta, fmtNumber } from '../../utils/format'
import { downloadBlob } from '../../utils/csv'
import { api } from '../../api/client'
import type { GeneRow } from '../../types/run'
import TablePager from '../TablePager.vue'
import { usePagedRows } from '../../utils/pagination'
import { isSyntheticResult } from '../../utils/source'
import { hasPredictionChange } from '../../utils/predictionEvidence'

/**
 * 基因响应：上方绝对变化最大基因水平条形图（以零为中心发散），
 * 下方可搜索排序表格 + 选中基因详情；概览使用 summary.top_genes。
 * 仅展示完整、有限且非零的模型预测变化；不以零补缺失值。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const ui = useUiStore()

const entry = computed(() => runs.entry(props.runId))
const block = computed(() => entry.value?.genes ?? null)
const galleryRows = computed(() => (block.value?.data?.items ?? []).map(row => ({id:row.gene, control:row.control ?? null, predicted:row.predicted, delta:row.predicted_delta})))
const tableTools = ref<HTMLElement | null>(null)
async function inspectGene(id: string) { selectedGene.value = id; search.value = id; await nextTick(); tableTools.value?.scrollIntoView({behavior:'smooth',block:'start'}) }

const route = useRoute()
const search = ref('')
const sortKey = ref<'gene' | 'control' | 'predicted' | 'predicted_delta' | 'observed' | 'observed_delta'>(
  'predicted_delta',
)
const sortDir = ref<'asc' | 'desc'>('desc')
const selectedGene = ref<string | null>(null)
watch(() => route.query.gene, gene => { if (typeof gene === 'string') { search.value = gene; selectedGene.value = gene } }, {immediate:true})
const exporting = ref(false), exportError = ref('')
const exportUnavailable = computed(() => isSyntheticResult(entry.value?.record?.request.mode,props.runId,entry.value?.record?.result_kind) || entry.value?.record?.request.mode === 'validation')
let exportController: AbortController | undefined
watch(() => props.runId, () => {exportController?.abort();exporting.value=false;exportError.value=''}, {flush:'sync'})
onBeforeUnmount(() => exportController?.abort())

const items = computed<GeneRow[]>(() => (block.value?.data?.items ?? []).filter(row => hasPredictionChange(row) || row.gene === route.query.gene || row.gene === selectedGene.value))
const truncated = computed(() => block.value?.data?.truncated ?? false)

const filtered = computed(() => {
  const query = search.value.trim().toUpperCase()
  if (!query) return items.value
  return items.value.filter((row) => row.gene.toUpperCase().includes(query))
})

const sorted = computed(() => {
  const key = sortKey.value
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...filtered.value].sort((a, b) => {
    const va = a[key]
    const vb = b[key]
    // null（未提供）一律排在最后
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    if (typeof va === 'string' && typeof vb === 'string') return va.localeCompare(vb) * dir
    return ((va as number) - (vb as number)) * dir
  })
})

const { page, pageSize, pages, visible: pageRows } = usePagedRows(sorted)

const hasObserved = computed(() => items.value.some((row) => row.observed !== null || row.observed_delta !== null))
watch(hasObserved, available => {
  if (!available && (sortKey.value === 'observed' || sortKey.value === 'observed_delta')) sortKey.value = 'predicted_delta'
})

const display = computed<BlockDisplay>(() => {
  const b = block.value
  if (!b || b.status === 'idle' || b.status === 'loading') return 'loading'
  if (b.status === 'error') {
    if (b.error?.status === 404 || b.error?.status === 409) return 'unavailable'
    return 'error'
  }
  return items.value.length > 0 ? 'ok' : 'empty'
})

function toggleSort(key: typeof sortKey.value): void {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = key === 'gene' ? 'asc' : 'desc'
  }
}

function sortMark(key: typeof sortKey.value): string {
  if (sortKey.value !== key) return ''
  return sortDir.value === 'asc' ? ' ▲' : ' ▼'
}

function retry(): void {
  runs.retryBlock(props.runId, 'genes')
}

async function exportCsv(): Promise<void> {
  if (exporting.value || exportUnavailable.value) return
  const id = props.runId, current = exportController = new AbortController()
  exporting.value=true;exportError.value=''
  try {
    const result = await api.getExportTable(id,'genes','original',current.signal)
    if (!current.signal.aborted && id === props.runId) {
      downloadBlob(result.blob,result.filename)
      ui.push('success','已导出完整基因汇总表，包含尺度、群体与来源说明')
    }
  } catch(error) {if (!current.signal.aborted) exportError.value=error instanceof Error ? error.message : '基因表导出失败'}
  finally {if (!current.signal.aborted) exporting.value=false}
}
</script>

<template>
  <BlockState
    :display="display"
    :error="block?.error"
    loading-text="正在加载基因响应表…"
    empty-text="暂无可展示的基因响应"
    unavailable-text="本次结果未提供基因差异表"
    unavailable-hint="其他标签页仍可正常使用。"
    @retry="retry"
  >
    <template #empty-extra>
      <button class="btn btn-sm" type="button" :disabled="exporting || exportUnavailable" @click="exportCsv">{{ exporting?'下载中…':'导出完整基因 CSV' }}</button>
      <p v-if="exportUnavailable" class="muted small">此数据来源暂不支持完整表导出。</p>
      <p v-if="exportError" class="notice notice-warn" role="alert">{{ exportError }}</p>
    </template>
    <ExpressionResponseGallery :record-id="runId" source-kind="run" :rows="galleryRows" :selected-id="selectedGene || undefined" :truncated="truncated" :read-only="Boolean(accessSession?.read_only)" units="平均归一化表达（原运行尺度）" @select="inspectGene" />
    <!-- 表格工具行 -->
    <div ref="tableTools" class="table-tools" style="scroll-margin-top:100px;margin-top:30px">
      <label class="sr-only" for="gene-search">搜索基因</label>
      <input
        id="gene-search"
        v-model="search"
        class="input search-input"
        type="search"
        placeholder="搜索基因符号（仅覆盖已加载记录）"
      />
      <span class="small muted">{{ sorted.length }} / {{ items.length }} 条</span>
      <span class="spacer"></span>
      <button class="btn btn-sm" type="button" :disabled="exporting || exportUnavailable" @click="exportCsv">{{ exporting?'下载中…':'导出完整基因 CSV' }}</button>
      <span v-if="exportUnavailable" class="muted small">此数据来源暂不支持完整表导出。</span>
      <span v-if="exportError" class="notice notice-warn" role="alert">{{ exportError }}</span>
    </div>

    <!-- 基因表 -->
    <div class="table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="sortable" scope="col" @click="toggleSort('gene')">基因{{ sortMark('gene') }}</th>
            <th class="sortable" scope="col" @click="toggleSort('control')">对照{{ sortMark('control') }}</th>
            <th class="sortable" scope="col" @click="toggleSort('predicted')">预测{{ sortMark('predicted') }}</th>
            <th class="sortable" scope="col" @click="toggleSort('predicted_delta')">
              预测变化{{ sortMark('predicted_delta') }}
            </th>
            <th v-if="hasObserved" class="sortable" scope="col" @click="toggleSort('observed')">观测{{ sortMark('observed') }}</th>
            <th v-if="hasObserved" class="sortable" scope="col" @click="toggleSort('observed_delta')">
              观测变化{{ sortMark('observed_delta') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="sorted.length === 0">
            <td :colspan="hasObserved ? 6 : 4" class="muted" style="text-align: center">
              已加载记录中没有匹配「{{ search }}」的基因
            </td>
          </tr>
          <tr
            v-for="row in pageRows"
            :key="row.gene"
            class="clickable"
            :class="{ 'row-selected': selectedGene === row.gene }"
            tabindex="0"
            @click="selectedGene = row.gene"
            @keydown.enter="selectedGene = row.gene"
          >
            <td class="mono">{{ row.gene }}</td>
            <td><span :class="{ 'null-value': row.control === null }">{{ fmtNumber(row.control) }}</span></td>
            <td><span :class="{ 'null-value': row.predicted === null }">{{ fmtNumber(row.predicted) }}</span></td>
            <td>
              <span :class="{ 'null-value': row.predicted_delta === null }">
                {{ fmtDelta(row.predicted_delta) }}
              </span>
            </td>
            <td v-if="hasObserved"><span :class="{ 'null-value': row.observed === null }">{{ fmtNumber(row.observed) }}</span></td>
            <td v-if="hasObserved">
              <span :class="{ 'null-value': row.observed_delta === null }">
                {{ fmtDelta(row.observed_delta) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="sorted.length" />
    <p class="muted small" style="margin: 8px 0 0">
      预测变化 = 预测平均表达 − 对照平均表达；“未提供”表示暂无数值。
    </p>
  </BlockState>
</template>

<style scoped>
.gene-analysis-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(220px,1fr);gap:12px}
.gene-analysis-grid .chart-card{margin:12px 0 0}
.gene-analysis-grid .gene-detail{margin:12px 0 0;align-self:stretch;border-color:var(--border);background:var(--figure-soft-bg);padding:20px 16px}
.gene-detail strong{font-size:21px;font-weight:500}
.expression-values{margin:24px 0 14px;display:grid;gap:16px}
.expression-value{display:grid;grid-template-columns:28px 1fr 48px;gap:8px;align-items:center;font-size:10px}
.expression-value strong{font-size:11px;font-weight:400;text-align:right}
.expression-track{height:5px;background:var(--figure-track-bg)}.expression-track i{display:block;height:100%}
.gene-detail .evidence-list{font-size:11px}
.gene-detail-empty{color:var(--muted);font-size:12px}


.overview {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.chart-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 12px 14px;
  margin: 12px 0;
  background: var(--card);
}
.chart-title {
  font-size: 14px;
}
.table-tools {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0 10px;
  flex-wrap: wrap;
}
.search-input {
  max-width: 300px;
}
.spacer {
  flex: 1;
}
.gene-detail {
  border: 1px solid var(--primary);
  background: var(--primary-weak);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  margin-bottom: 10px;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
