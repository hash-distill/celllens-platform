<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRunStore } from '../../stores/run'
import { useUiStore } from '../../stores/ui'
import BlockState, { type BlockDisplay } from '../BlockState.vue'
import DivergingBar, { type DivergingBarItem } from '../../charts/DivergingBar.vue'
import { fmtDelta, fmtNumber, EVIDENCE_LABEL } from '../../utils/format'
import { downloadCsv } from '../../utils/csv'
import type { GeneRow } from '../../types/run'
import TablePager from '../TablePager.vue'
import { usePagedRows } from '../../utils/pagination'
import { isSyntheticResult, runSourceLabel } from '../../utils/source'

/**
 * 基因响应：上方绝对变化最大基因水平条形图（以零为中心发散），
 * 下方可搜索排序表格 + 选中基因详情；概览使用 summary.top_genes。
 * 排序使用转换后数值；空值显示「未提供」，不得转为 0。
 */

const props = defineProps<{ runId: string }>()

const runs = useRunStore()
const ui = useUiStore()

const entry = computed(() => runs.entry(props.runId))
const block = computed(() => entry.value?.genes ?? null)
const summary = computed(() => entry.value?.summary.data ?? null)

const search = ref('')
const sortKey = ref<'gene' | 'control' | 'predicted' | 'predicted_delta' | 'observed' | 'observed_delta'>(
  'predicted_delta',
)
const sortDir = ref<'asc' | 'desc'>('desc')
const selectedGene = ref<string | null>(null)

const items = computed<GeneRow[]>(() => block.value?.data?.items ?? [])
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

const barItems = computed<DivergingBarItem[]>(() =>
  items.value
    .filter((row) => row.predicted_delta !== null)
    .sort((a, b) => Math.abs(b.predicted_delta ?? 0) - Math.abs(a.predicted_delta ?? 0))
    .slice(0, 15)
    .map((row) => ({
      name: row.gene,
      value: row.predicted_delta ?? 0,
      extra: `对照 ${fmtNumber(row.control)} → 预测 ${fmtNumber(row.predicted)}`,
    })),
)

const { page, pages, visible: pageRows } = usePagedRows(sorted)

const selected = computed(() => items.value.find((row) => row.gene === selectedGene.value) ?? null)

const expressionScale = computed(() => Math.max(1e-9, ...[selected.value?.control, selected.value?.predicted, selected.value?.observed].filter((v): v is number => v !== null && v !== undefined).map(Math.abs)))
watch(items, rows => {
  if (!rows.some(row => row.gene === selectedGene.value)) selectedGene.value = barItems.value[0]?.name ?? null
}, {immediate:true})

const hasObserved = computed(() => items.value.some((row) => row.observed !== null || row.observed_delta !== null))

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

function exportCsv(): void {
  const data = block.value?.data
  if (!data) return
  const source = runSourceLabel(entry.value?.record?.request.mode, props.runId, entry.value?.record?.result_kind)
  const filename = `celllens-genes-${source}-${props.runId}-${data.truncated ? 'partial' : 'full'}-limit${data.limit}.csv`
  downloadCsv(
    filename,
    ['gene', 'control', 'predicted', 'predicted_delta', 'observed', 'observed_delta'],
    data.items.map((row) => [
      row.gene,
      row.control === null ? '' : String(row.control),
      row.predicted === null ? '' : String(row.predicted),
      row.predicted_delta === null ? '' : String(row.predicted_delta),
      row.observed === null ? '' : String(row.observed),
      row.observed_delta === null ? '' : String(row.observed_delta),
    ]),
  )
  ui.push(
    'success',
    `已导出 ${data.items.length} 行（${data.truncated ? '部分结果，服务端已截断' : '全部已加载结果'}，来源：genes 接口）`,
  )
}
</script>

<template>
  <BlockState
    :display="display"
    :error="block?.error"
    loading-text="正在加载基因响应表…"
    empty-text="本次结果没有基因差异记录"
    unavailable-text="本次结果未提供基因差异表"
    unavailable-hint="其他标签页仍可正常使用。"
    @retry="retry"
  >
    <!-- 后端 Top 基因概览 -->
    <div v-if="summary && summary.top_genes.length > 0" class="overview">
      <span class="small muted">后端 Top 基因概览（summary.top_genes）：</span>
      <span
        v-for="gene in summary.top_genes.slice(0,4)"
        :key="gene.id"
        class="pill pill-info"
        :title="`证据等级：${EVIDENCE_LABEL[gene.evidence_level]}；覆盖 ${(gene.coverage * 100).toFixed(1)}%`"
      >
        {{ gene.label }} {{ fmtDelta(gene.predicted_delta) }}
      </span>
    </div>

    <div v-if="truncated" class="notice notice-warn">
      当前为部分结果：服务端按 limit={{ block?.data?.limit }} 截断，表格与图表只覆盖已加载记录。
    </div>

    <div class="gene-analysis-grid">
    <!-- 差异条形图 -->
    <div class="chart-card">
      <div class="flex-between">
        <h3 class="chart-title">绝对变化最大的基因（前 {{ barItems.length }}）</h3>
        <span class="small muted">预测减对照的平均归一化表达差</span>
      </div>
      <DivergingBar
        v-if="barItems.length > 0"
        :items="barItems"
        category-name="基因"
        value-label="预测变化"
        :height="380"
        :selected-name="selectedGene"
        @select="selectedGene = $event"
      />
      <p v-else class="muted small">已加载记录中没有有效的预测变化数值。</p>
      <p class="muted small" style="margin:4px 0 0">点击条形或表格行查看同一基因的数值。</p>
    </div>

    <!-- 选中基因详情 -->
    <div v-if="selected" class="gene-detail" role="region" aria-label="选中基因详情">
      <div class="flex-between">
        <strong>{{ selected.gene }}</strong>
        <button class="btn btn-ghost btn-sm" type="button" @click="selectedGene = null">关闭</button>
      </div>
      <div class="expression-values">
        <div v-for="item in [{label:'对照',value:selected.control,color:'var(--source-control)'},{label:'预测',value:selected.predicted,color:'var(--source-predicted)'},{label:'观测',value:selected.observed,color:'var(--source-observed)'}]" :key="item.label" class="expression-value">
          <span>{{ item.label }}</span><div class="expression-track"><i v-if="item.value!==null" :style="{width:Math.abs(item.value)/expressionScale*100+'%',background:item.color}"></i></div><strong>{{ fmtNumber(item.value) }}</strong>
        </div>
      </div>
      <p class="micro">本页展示群体平均归一化表达</p>
      <RouterLink v-if="!isSyntheticResult(entry?.record?.request.mode,runId,entry?.record?.result_kind)" class="btn btn-sm" :to="{path:'/workbench',query:{run:runId,tab:'cell',feature_kind:'gene',feature_id:selected.gene}}">查看该基因逐细胞分布</RouterLink>
      <dl class="evidence-list" style="margin-top: 8px">
        <dt>对照表达</dt>
        <dd>{{ fmtNumber(selected.control) }}</dd>
        <dt>预测表达</dt>
        <dd>{{ fmtNumber(selected.predicted) }}</dd>
        <dt>预测变化</dt>
        <dd>{{ fmtDelta(selected.predicted_delta) }}（预测减对照的平均归一化表达差）</dd>
        <template v-if="hasObserved">
          <dt>观测表达</dt>
          <dd>{{ fmtNumber(selected.observed) }}</dd>
          <dt>观测变化</dt>
          <dd>{{ fmtDelta(selected.observed_delta) }}</dd>
        </template>
      </dl>
    </div>

<div v-if="!selected" class="gene-detail gene-detail-empty"><span class="micro">GENE INSPECTOR</span><p>选择条形或表格记录，查看本次表达数值。</p></div></div>
    <!-- 表格工具行 -->
    <div class="table-tools">
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
      <button class="btn btn-sm" type="button" @click="exportCsv">导出全部已加载 CSV</button>
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
            <th class="sortable" scope="col" @click="toggleSort('observed')">观测{{ sortMark('observed') }}</th>
            <th class="sortable" scope="col" @click="toggleSort('observed_delta')">
              观测变化{{ sortMark('observed_delta') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="sorted.length === 0">
            <td colspan="6" class="muted" style="text-align: center">
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
            <td><span :class="{ 'null-value': row.observed === null }">{{ fmtNumber(row.observed) }}</span></td>
            <td>
              <span :class="{ 'null-value': row.observed_delta === null }">
                {{ fmtDelta(row.observed_delta) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <TablePager v-model:page="page" :pages="pages" :total="sorted.length" />
    <p class="muted small" style="margin: 8px 0 0">
      「预测变化」为预测减对照的平均归一化表达差（不是 log2FC）；空值表示接口未提供，不以 0 代替。
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
@media(max-width:1100px){.gene-analysis-grid{grid-template-columns:1fr}.expression-values{max-width:420px;margin-top:14px}}

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
