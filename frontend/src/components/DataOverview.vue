<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiFetch } from '../api/http'
import { cellBackgrounds, getCellBackground } from '../data/cellBackgrounds'
import { useCatalogStore } from '../stores/catalog'
import { usePagedRows } from '../utils/pagination'
import { downloadCsv } from '../utils/csv'
import TablePager from './TablePager.vue'
import CellBackgroundCard from './CellBackgroundCard.vue'
import MethodsPageHeader from './MethodsPageHeader.vue'

interface DataContext {
  cell_line: string; model_id: string; model_version: string | null; expression_scale: string | null
  expression_gene_count: number | null; expression_genes: string[]; panel_verified: boolean
  panel_sha256: string | null; perturbation_count: number; dataset_id: string | null
  control_registered: boolean; registered_observations: {perturbation: string; cell_count: number | null}[]
  control_cell_count: number | null; control_metadata_verified: boolean
}
const route = useRoute(), router = useRouter(), catalog = useCatalogStore()
const contexts = shallowRef<DataContext[]>([]), loading = ref(false), error = ref(''), query = ref('')
let controller: AbortController | undefined
const backgrounds = Object.values(cellBackgrounds)
const selectedCellLine = computed(() => backgrounds.find(row => row.id === route.query.cell_line)?.id ?? backgrounds[0]!.id)
const selected = computed(() => contexts.value.find(row => row.cell_line === selectedCellLine.value))
const selectedBackground = computed(() => getCellBackground(selectedCellLine.value))
function contextFor(cellLine: string) {return contexts.value.find(row => row.cell_line === cellLine)}
const filtered = computed(() => (selected.value?.expression_genes ?? []).filter(gene => gene.toLowerCase().includes(query.value.trim().toLowerCase())))
const {page, pageSize, pages, visible} = usePagedRows(filtered)
watch(() => selected.value?.cell_line, () => {query.value = ''})
function choose(cellLine: string) {void router.replace({path:'/methods/backgrounds', query:{cell_line:cellLine}})}
function number(value: number | null | undefined) {return value == null ? '—' : value.toLocaleString()}
async function load() {
  controller?.abort(); const current = controller = new AbortController()
  loading.value = true; error.value = ''; contexts.value = []
  try {
    const result = await apiFetch<{contexts:DataContext[]}>('/catalog/data-summary', {signal:current.signal})
    if (!current.signal.aborted) {
      contexts.value = result.contexts
      loading.value = false
      await nextTick()
      if (!current.signal.aborted && route.hash === '#control-sampling') document.getElementById('control-sampling')?.scrollIntoView({block:'start'})
    }
  } catch (reason) {if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '数据范围读取失败'}
  finally {if (!current.signal.aborted) loading.value = false}
}
function exportPanel() {
  if (selected.value?.panel_verified) downloadCsv(`${selected.value.cell_line}-expression-panel.csv`, ['gene'], selected.value.expression_genes.map(gene => [gene]))
}
onMounted(load)
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="data-overview" aria-label="系统数据背景">
    <MethodsPageHeader eyebrow="CELL BACKGROUNDS / DATA SOURCES" title="细胞背景" description="了解四种细胞背景的生物学特点，再查看对应表达面板、对照来源与可用实测。" />
      <div class="background-cards" aria-label="支持的细胞背景">
        <button v-for="background in backgrounds" :key="background.id" class="background-choice" :class="{selected:selectedCellLine===background.id}" :aria-pressed="selectedCellLine===background.id" @click="choose(background.id)">
          <span class="background-heading"><strong>{{ background.id }}</strong><span class="background-status" :class="{ready:catalog.contextFor(background.id)?.online_ready}">{{ catalog.loading ? '读取状态中' : catalog.contextFor(background.id)?.online_ready ? '在线可用' : '当前未就绪' }}</span></span>
          <span class="background-type">{{ background.type_zh }}</span>
          <span class="background-description">{{ background.features_zh }}</span>
          <span class="background-counts"><span><b>{{ number(contextFor(background.id)?.expression_gene_count) }}</b>表达基因</span><span><b>{{ number(contextFor(background.id)?.perturbation_count) }}</b>可选扰动</span></span>
        </button>
      </div>
    <details v-if="selectedBackground" class="source-details background-biography"><summary>了解 {{ selectedCellLine }} 的生物学背景</summary><CellBackgroundCard :background="selectedBackground" /></details>
    <p v-if="loading" role="status" class="data-notice">正在核对表达面板与实测数量；生物学背景可直接浏览。</p>
    <div v-else-if="error" role="alert" class="notice notice-danger">{{ error }} <button class="btn btn-sm" @click="load">重试</button></div>
    <template v-else>
      <section v-if="selected" class="data-source" aria-label="当前数据来源">
        <div class="source-heading"><div><span class="eyebrow">{{ selected.cell_line }} / DATA SOURCES</span><h3>数据与分析内容</h3></div><span class="source-scale">{{ selected.expression_scale || '表达尺度暂无信息' }}</span></div>
        <dl class="source-roles"><div><dt>真实对照</dt><dd>对应背景的 non-targeting 实测阴性对照，作为模型输入与比较基线。<template v-if="selected.control_metadata_verified">当前固定保存 {{ number(selected.control_cell_count) }} 个细胞。</template><template v-else>{{ selected.control_registered ? '对照已配置，细胞数暂未核验。' : '暂无对照数据。' }}</template></dd></div><div><dt>预测表达</dt><dd>模型生成的表达矩阵，当前面板 {{ number(selected.expression_gene_count) }} 个基因；预测样本数由实验参数决定。</dd></div><div><dt>匹配实测</dt><dd v-if="selected.registered_observations.length">可用 {{ selected.registered_observations.length }} 组：{{ selected.registered_observations.map(row => `${row.perturbation}（${row.cell_count ?? '—'} 个细胞）`).join('、') }}。</dd><dd v-else>暂无匹配的实测对比数据。</dd></div></dl>
        <p class="data-footnote">数据来源：STATE 官方 State-Replogle-Filtered 单细胞扰动数据集。</p>
        <section id="control-sampling" class="control-sampling" aria-labelledby="control-sampling-title">
          <h3 id="control-sampling-title">对照来源与预测采样</h3>
          <p>公开 Perturb-seq 数据由实验测量单细胞 RNA 表达。系统按细胞背景及 non-targeting 标签筛选阴性对照；这些细胞使用非靶向引导序列，未针对本次目标基因实施靶向干预。</p>
          <p>数据准备时以固定种子抽样并保存，新任务复用当前登记的对照池，历史实验仍按自身冻结输入追溯。各背景的实际细胞数由当前文件核验，不代表公开数据集的全部细胞数；共同批次筛选后，实际分析人数可能减少。图上的二维位置由表达降维得到。</p>
          <div class="table-wrap"><table class="table sampling-table"><thead><tr><th scope="col">数量</th><th scope="col">当前含义</th><th scope="col">什么时候确定</th></tr></thead><tbody>
            <tr><th scope="row">真实对照细胞</th><td>{{ selected.control_metadata_verified ? number(selected.control_cell_count) + ' 个 ' + selected.cell_line + ' 实测细胞' : '当前数量暂未核验' }}</td><td>数据准备阶段固定；修改预测采样数不会改变它。</td></tr>
            <tr><th scope="row">预测采样细胞</th><td>每次请求 64–4096 条模型预测表达记录</td><td>由实验参数指定；完成后以结果中的实际数量为准。</td></tr>
          </tbody></table></div>
          <p>当前 STATE 从对照池中有放回取样，再计算目标扰动下的预测表达；同一对照状态可以被重复使用，因此预测样本数可以超过真实对照数。两组按群体均值和分布比较，不要求等量，也不逐细胞配对。</p>
          <p class="sampling-limit">64–4096 是平台允许的请求范围，用于限定任务规模。更多预测记录会增加计算与输出开销，不会增加独立实测细胞，也不保证更准确；样本量不等时，不能直接用散点疏密或数量判断细胞增殖、死亡或扰动强弱。</p>
          <div class="source-links"><a href="https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered" target="_blank" rel="noopener">公开数据集 ↗</a><a href="https://pmc.ncbi.nlm.nih.gov/articles/PMC9380471/" target="_blank" rel="noopener">Perturb-seq 原始研究 ↗</a><a href="https://github.com/ArcInstitute/state/blob/main/src/state/_cli/_tx/_infer.py" target="_blank" rel="noopener">STATE 采样实现 ↗</a></div>
        </section>
        <details class="source-details"><summary>模型与数据来源</summary><p>模型：{{ selected.model_id }} · arc-state {{ selected.model_version || '暂无版本信息' }}</p><p>对照数据：{{ selected.dataset_id || '暂无信息' }}</p><div class="source-links"><a href="https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered" target="_blank" rel="noopener">官方数据来源 ↗</a><a v-for="source in getCellBackground(selected.cell_line)?.sources" :key="source.url" :href="source.url" target="_blank" rel="noopener">{{ source.label }} ↗</a></div></details>
        <details class="expression-explorer"><summary>浏览 {{ selected.cell_line }} 的表达基因面板 <span>{{ number(selected.expression_gene_count) }} 个基因</span></summary><div class="expression-toolbar"><label>搜索表达基因<input v-model="query" type="search" placeholder="输入基因符号" /></label><button class="btn btn-sm" :disabled="!selected.panel_verified" @click="exportPanel">下载表达面板</button></div><p v-if="!selected.panel_verified" class="data-footnote">表达面板暂不可用，请稍后重试。</p><p v-else class="data-footnote">匹配 {{ filtered.length }} 个表达基因。此处是模型输出面板；“覆盖范围”页展示与代谢知识库相交的基因。</p><div class="expression-genes"><span v-for="gene in visible" :key="gene">{{ gene }}</span></div><TablePager v-model:page="page" v-model:page-size="pageSize" :pages="pages" :total="filtered.length" /></details>
      </section>
    </template>
  </section>
</template>

<style scoped>
.control-sampling{border-top:1px solid var(--border);margin-top:24px;padding-top:20px;scroll-margin-top:100px}.control-sampling h3{font-size:18px;font-weight:600;margin:0 0 14px}.control-sampling p{font-size:13px;color:var(--muted);line-height:1.85;margin:12px 0}.sampling-table{margin:16px 0}.sampling-table tbody th{font-weight:500;text-align:left;white-space:nowrap;padding:13px 14px;border-bottom:1px solid var(--border);color:var(--ink)}.control-sampling .sampling-limit{border-left:2px solid var(--border-strong);padding-left:14px}
.data-intro{max-width:860px;margin-bottom:28px}.data-intro h2{font-size:30px;font-weight:500;letter-spacing:-.03em;margin:16px 0}.data-intro p{color:var(--muted);font-size:13px;line-height:1.95}.background-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.background-choice{min-width:0;appearance:none;text-align:left;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--ink);padding:22px 20px;font:12px var(--font);cursor:pointer}.background-choice:hover,.background-choice.selected{border-color:var(--primary)}.background-choice.selected{background:var(--primary-weak);box-shadow:inset 0 3px var(--primary)}.background-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.background-heading>strong{font:30px Georgia,serif;letter-spacing:-.03em}.background-status{font-size:9px;color:var(--muted);white-space:nowrap}.background-status.ready{color:var(--primary)}.background-type{display:block;margin-top:14px;font-size:12px;min-height:36px;line-height:1.6}.background-description{display:block;font-size:11px;line-height:1.85;color:var(--muted);min-height:84px}.background-counts{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--border);margin-top:20px;padding-top:16px;gap:12px}.background-counts span{font-size:10px;color:var(--muted)}.background-counts b{display:block;color:var(--primary-strong);font:25px Georgia,serif;margin-bottom:7px}.data-source{margin:30px 0 46px}.source-heading{display:flex;justify-content:space-between;align-items:center;gap:24px}.source-heading h3{font-size:21px;font-weight:500;margin:12px 0 20px}.source-scale{font:11px Consolas,monospace;color:var(--muted)}.source-roles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28px;margin:8px 0 18px}.source-roles>div{border-left:2px solid var(--border-strong);padding-left:18px}.source-roles dt{font-size:12px;color:var(--primary);margin-bottom:10px}.source-roles dd{font-size:12px;color:var(--muted);line-height:1.9;margin:0}.data-footnote,.data-notice{font-size:11px;color:var(--muted);line-height:1.9}.source-details,.expression-explorer{margin-top:20px;border-top:1px solid var(--border);padding-top:16px;font-size:12px}.source-details summary,.expression-explorer summary{cursor:pointer;color:var(--primary);line-height:1.8}.source-details p{font-size:11px;color:var(--muted);line-height:1.8}.source-details code{font-size:10px;overflow-wrap:anywhere;color:var(--muted)}.source-links{display:flex;flex-wrap:wrap;gap:20px;margin:16px 0;font-size:11px}.expression-explorer summary span{font-size:10px;color:var(--muted);margin-left:16px}.expression-toolbar{display:flex;gap:24px;justify-content:space-between;align-items:end;margin-top:20px}.expression-toolbar label{font-size:11px;color:var(--muted);max-width:340px;flex:1}.expression-toolbar input{display:block;margin-top:8px;width:100%;background:var(--card);color:var(--ink);border:1px solid var(--border-strong);padding:10px 12px;font:12px var(--font)}.expression-genes{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin:20px 0}.expression-genes span{padding:10px 12px;background:var(--surface-soft);font:11px Consolas,monospace;overflow-wrap:anywhere}
</style>
