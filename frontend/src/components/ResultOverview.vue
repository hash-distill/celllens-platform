<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { comparisonBars, coverageState, finiteValue, rankGenes, rankTasks } from '../utils/resultOverview'
import type { OverviewCounts, OverviewRow, OverviewSource, OverviewTaskRow } from '../utils/resultOverview'

const props = withDefaults(defineProps<{
  readOnly?: boolean
  sourceKind: OverviewSource
  cellLine: string
  perturbation: string
  genes: OverviewRow[]
  tasks: OverviewTaskRow[]
  counts?: OverviewCounts
  baselineRatio?: number | null
  targetInPanel?: boolean | null
  geneCount?: number | null
  sourceLabel?: string
  expressionUnits?: string
  baselineSensitive?: boolean | null
}>(), { targetInPanel: null, readOnly: false })
const emit = defineEmits<{
  'select-gene': [id: string]
  'select-task': [id: string]
  'focus-task': [id: string]
  interpret: []
}>()
const selectedCategory = ref<string | null>(null)
const selectedTaskId = ref('')
const showAllTasks = ref(false)
const categoryName = (task: OverviewTaskRow) => task.category?.trim() || '未分类'
const categories = computed(() => [...new Set(props.tasks.map(categoryName))])
const activeCategory = computed(() => selectedCategory.value !== null && categories.value.includes(selectedCategory.value) ? selectedCategory.value : null)
const rankedTasks = computed(() => rankTasks(props.tasks))
const categoryTasks = computed(() => rankedTasks.value.filter(task => activeCategory.value === null || categoryName(task) === activeCategory.value))
const visibleTasks = computed(() => showAllTasks.value ? categoryTasks.value : categoryTasks.value.slice(0, 8))
const selectedTask = computed(() => visibleTasks.value.find(task => task.id === selectedTaskId.value) ?? visibleTasks.value[0] ?? null)
watch(() => selectedTask.value?.id, id => { if(id) emit('focus-task',id) }, {immediate:true})
const comparison = computed(() => selectedTask.value ? comparisonBars(selectedTask.value, props.sourceKind) : null)
const topGenes = computed(() => rankGenes(props.genes).slice(0, 12))
const scoredTaskCount = computed(() => props.tasks.filter(task => [task.control, task.predicted, task.observed].some(value => finiteValue(value) !== null)).length)
const fullCount = computed(() => props.tasks.filter(task => coverageState(task.coverage) === 'full').length)
const partialCount = computed(() => props.tasks.filter(task => coverageState(task.coverage) === 'partial').length)
const unknownCount = computed(() => props.tasks.length - fullCount.value - partialCount.value)
const baseline = computed(() => {
  const ratio = finiteValue(props.baselineRatio)
  return ratio !== null && ratio >= 0 ? ratio : null
})
const sourceLabels = { control: '对照', predicted: '模型预测', observed: '扰动实测' }
const availableCounts = computed(() => (props.sourceKind === 'run' ? ['control', 'predicted', 'observed'] as const : ['control', 'observed'] as const)
  .map(source => ({ source, value: finiteValue(props.counts?.[source]) }))
  .map(item => ({ ...item, value: item.value !== null && item.value >= 0 && Number.isInteger(item.value) ? item.value : null }))
  .filter(item => item.source !== 'observed' || props.sourceKind === 'measured' || item.value !== null))

function numberLabel(value: unknown, signed = false): string {
  const number = finiteValue(value)
  if (number === null) return '暂无数值'
  const formatted = number !== 0 && Math.abs(number) < 0.001 ? number.toExponential(2) : number.toLocaleString('zh-CN', { maximumFractionDigits: 3 })
  return signed && number > 0 ? `+${formatted}` : formatted
}
function direction(value: unknown): string {
  const number = finiteValue(value)
  return number === null ? 'missing' : number > 0 ? 'positive' : number < 0 ? 'negative' : 'zero'
}
function coverageLabel(task: OverviewTaskRow): string {
  const state = coverageState(task.coverage)
  if (state === 'full') return '关联基因齐全'
  if (state === 'unknown') return '关联基因覆盖未知'
  return `关联基因不全 · ${Math.floor(task.coverage! * 100)}%`
}
function selectCategory(category: string | null) {
  selectedCategory.value = category
  showAllTasks.value = false
}
function selectTask(id: string) {
  selectedTaskId.value = id
}
</script>

<template>
  <section class="result-overview" aria-label="研究结果概览">
    <header class="overview-heading">
      <div>
        <p class="eyebrow">研究结果概览 <span>{{ sourceKind === 'run' ? '模型探索' : '实测分析' }}</span></p>
        <h2>{{ cellLine || '细胞背景待提供' }} <span>/</span> {{ perturbation || '扰动待提供' }}</h2>
        <p class="overview-subtitle">{{ sourceLabel || (sourceKind === 'run' ? '模型预测与可用实测诊断' : '实测表达比较') }} · {{ expressionUnits || '表达尺度见来源清单' }}</p>
      </div>
      <button v-if="!readOnly" class="interpret-button" type="button" :disabled="!genes.length && !tasks.length" @click="emit('interpret')">解读当前结果 <span aria-hidden="true">↗</span></button>
    </header>

    <div v-if="availableCounts.length" class="population-counts" aria-label="群体记录数量">
      <span v-for="item in availableCounts" :key="item.source"><i :class="item.source" />{{ sourceLabels[item.source] }} <strong>{{ item.value === null ? '未记录' : item.value.toLocaleString('zh-CN') }}</strong> {{ item.source === 'predicted' ? '条预测记录' : '个细胞' }}</span>
    </div>
    <div class="result-key-metrics" aria-label="本次结果摘要">
      <div><span>{{ sourceKind === 'measured' ? '共同基因' : '当前表达面板' }}</span><strong>{{ geneCount == null ? '未确认' : numberLabel(geneCount) }}</strong></div>
      <div><span>有评分的功能任务</span><strong>{{ scoredTaskCount }}</strong><small>已收录 {{ tasks.length }} 项覆盖信息</small></div>
      <div><span>关联基因齐全</span><strong>{{ fullCount }} <small>/ {{ tasks.length }} 项</small></strong><small>不全 {{ partialCount }} · 未知 {{ unknownCount }}</small></div>
      <div v-if="topGenes[0]"><span>当前列表最大表达差</span><strong>{{ topGenes[0].label || topGenes[0].id }} <small>{{ numberLabel(topGenes[0].delta, true) }}</small></strong><small>均值差，不表示显著性</small></div>
    </div>
    <div v-if="targetInPanel === false || (sourceKind === 'run' && baseline !== null)" class="evidence-notes">
      <p v-if="targetInPanel === false">目标基因不在当前表达面板中，无法直接查看它自身的表达变化。</p>
      <p v-if="sourceKind === 'run' && baseline !== null" :class="{ 'baseline-failed': baseline >= 1 }">
        <strong>原汇总估计 · 误差比 {{ numberLabel(baseline) }}</strong>
        <span>；小于 1 表示该汇总方式下的预测误差更低。{{ baselineSensitive === true ? '基线结论依赖批次权重，请到“实验对照”查看敏感性。' : baselineSensitive === false ? '已提供批次权重敏感性诊断，详见“实验对照”；不代表独立泛化验证。' : '尚未检验批次权重敏感性，请结合“实验对照”核查。' }}</span>
      </p>
    </div>

    <slot name="landscape" />

    <div v-if="!genes.length && !tasks.length" class="overview-empty"><strong>暂无可展示的结果</strong><p>当前研究条件尚未提供表达或任务评分；完成分析后将在这里展示。</p></div>
    <div v-else class="overview-body">
      <aside class="gene-summary">
        <div class="section-heading"><span class="section-index">01</span><h3>表达变化</h3></div>
        <p class="section-caption">按{{ sourceKind === 'run' ? '预测' : '实测' }}均值差绝对值排列，展示前 {{ topGenes.length }} 项。</p>
        <div v-if="topGenes.length" class="gene-list">
          <button v-for="gene in topGenes" :key="gene.id" type="button" class="gene-row" :disabled="readOnly" @click="emit('select-gene', gene.id)">
            <span class="gene-identity"><strong>{{ gene.label || gene.id }}</strong><small v-if="gene.label && gene.label !== gene.id">{{ gene.id }}</small></span>
            <span class="delta-number" :class="direction(gene.delta)">{{ numberLabel(gene.delta, true) }}</span><span v-if="!readOnly" class="row-arrow" aria-hidden="true">↗</span>
          </button>
        </div>
        <p v-else class="small-empty">暂无基因表达结果。</p>
        <p class="reading-note">差值 = {{ sourceKind === 'run' ? '预测' : '扰动实测' }}均值 − 对照均值。正负仅表示变化方向，不表示统计显著性。</p>
      </aside>

      <div class="function-summary">
        <div class="overview-function-heading">
          <div class="section-heading"><span class="section-index">02</span><h3>代谢相关功能</h3></div>
          <span class="task-total">已加载 {{ tasks.length }} 项任务</span>
        </div>
        <p class="section-caption">表达派生的任务支持评分；点击任务，在同一尺度下比较各组均值。</p>
        <template v-if="tasks.length">
          <div class="coverage-summary"><span>关联基因齐全 <strong>{{ fullCount }}</strong></span><span>不全 <strong>{{ partialCount }}</strong></span><span>未知 <strong>{{ unknownCount }}</strong></span></div>
          <nav v-if="categories.length > 1" class="category-list" aria-label="代谢任务分类">
            <button type="button" :aria-pressed="activeCategory === null" @click="selectCategory(null)">全部分类</button>
            <button v-for="category in categories" :key="category" type="button" :aria-pressed="activeCategory === category" @click="selectCategory(category)">{{ category }}</button>
          </nav>
          <div class="function-detail">
            <div class="task-selection">
              <div class="task-list-heading"><span>覆盖优先</span><span>{{ sourceKind === 'run' ? '预测' : '实测' }}差值</span></div>
              <div class="task-list">
                <button v-for="task in visibleTasks" :key="task.id" type="button" class="task-row" :aria-pressed="selectedTask?.id === task.id" @click="selectTask(task.id)">
                  <span class="task-identity"><strong>{{ task.label || task.id }}</strong><small :class="coverageState(task.coverage)">{{ coverageLabel(task) }}</small></span>
                  <span class="delta-number" :class="direction(task.delta)">{{ numberLabel(task.delta, true) }}</span>
                </button>
              </div>
              <button v-if="categoryTasks.length > 8" type="button" class="show-all" :aria-expanded="showAllTasks" @click="showAllTasks = !showAllTasks">{{ showAllTasks ? '收起为覆盖优先的 8 项' : `查看本分类全部 ${categoryTasks.length} 项任务` }}</button>
            </div>
            <div v-if="selectedTask && comparison" class="task-comparison" aria-live="polite">
              <p class="detail-label">当前任务</p>
              <h4>{{ selectedTask.label || selectedTask.id }}</h4>
              <p class="task-id">{{ selectedTask.id }} · {{ categoryName(selectedTask) }}</p>
              <span class="coverage-tag" :class="coverageState(selectedTask.coverage)">{{ coverageLabel(selectedTask) }}</span>
              <div class="comparison-bars" role="img" :aria-label="comparison.bars.map(bar => `${sourceLabels[bar.source]}：${numberLabel(bar.value)}`).join('；')">
                <div v-for="bar in comparison.bars" :key="bar.source" class="comparison-row">
                  <div class="bar-heading"><span>{{ sourceLabels[bar.source] }}</span><strong>{{ numberLabel(bar.value) }}</strong></div>
                  <div class="bar-track" :class="{missing: bar.value === null}">
                    <span v-if="bar.value !== null" class="zero-marker" :style="{left: comparison.zero + '%'}" />
                    <span v-if="bar.value !== null" class="bar-fill" :class="bar.source" :style="{left: bar.start + '%', width: bar.width + '%'}" />
                  </div>
                </div>
                <div v-if="comparison.hasValues" class="scale-labels"><span>{{ numberLabel(comparison.domain[0]) }}</span><span>同任务共同尺度</span><span>{{ numberLabel(comparison.domain[1]) }}</span></div>
              </div>
              <p class="comparison-note">{{ coverageState(selectedTask.coverage) === 'partial' ? '部分关联基因缺失，需结合缺失结构谨慎解读。' : coverageState(selectedTask.coverage) === 'unknown' ? '尚无关联基因覆盖信息，解读前请核对输入。' : '关联基因齐全描述输入完整性，不代表功能已获验证。' }}</p>
              <p class="missing-key">灰色纹理表示缺失；数值 0 保留为零。</p>
              <button v-if="!readOnly" type="button" class="show-all" @click="emit('select-task', selectedTask.id)">查看该任务证据 →</button>
            </div>
          </div>
        </template>
        <p v-else class="small-empty">暂无代谢任务评分。</p>
      </div>
    </div>
    <footer class="overview-footer">任务分数不能跨任务累加为整体活性，也不等同于实测代谢通量或因果机制。</footer>
  </section>
</template>

<style scoped>
.result-overview{container-type:inline-size;margin:0 0 24px;border:1px solid var(--border);background:var(--card);border-radius:8px;overflow:hidden;color:var(--ink)}
.overview-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:26px 28px 20px}.eyebrow{display:flex;align-items:center;gap:12px;margin:0 0 12px;font-size:11px;letter-spacing:.06em;color:var(--muted)}.eyebrow span{padding:3px 7px;background:var(--primary-weak);color:var(--primary-strong);border-radius:3px;letter-spacing:0}.overview-heading h2{font-size:27px;font-weight:500;margin:0;letter-spacing:-.025em}.overview-heading h2>span{color:var(--border-strong);padding:0 8px;font-weight:300}.overview-subtitle{font-size:12px;color:var(--muted);margin:9px 0 0;line-height:1.7}.interpret-button{border:1px solid var(--primary);background:var(--primary-weak);color:var(--primary-strong);padding:10px 14px;border-radius:5px;cursor:pointer;font-size:12px;white-space:nowrap}.interpret-button span{margin-left:14px}.interpret-button:disabled{opacity:.5;cursor:default}.population-counts{display:flex;gap:24px;flex-wrap:wrap;padding:0 28px 20px;font-size:11px;color:var(--muted)}.population-counts>span{display:flex;gap:6px;align-items:center}.population-counts strong{font-size:13px;color:var(--ink);font-weight:500;font-variant-numeric:tabular-nums}.population-counts i{height:6px;width:6px;border-radius:50%;background:var(--border-strong)}.population-counts i.predicted{background:var(--primary)}.population-counts i.observed{background:#bc8455}.evidence-notes{margin:0 28px 22px;padding:11px 14px;background:var(--surface-soft);border-left:2px solid var(--border-strong);font-size:11px;line-height:1.8;color:var(--muted)}.evidence-notes p{margin:3px 0}.evidence-notes strong{font-weight:500;color:var(--ink)}.evidence-notes .baseline-failed strong{color:#a36432}.overview-body{display:grid;grid-template-columns:minmax(220px,.75fr) minmax(0,2fr);border-top:1px solid var(--border)}.gene-summary{padding:24px;border-right:1px solid var(--border)}.function-summary{padding:24px;min-width:0}.section-heading{display:flex;gap:10px;align-items:baseline}.section-index{font-size:11px;color:var(--faint);font-variant-numeric:tabular-nums}.section-heading h3{font-size:15px;font-weight:500;margin:0}.section-caption{font-size:11px;line-height:1.8;color:var(--muted);margin:10px 0 16px}.gene-list{border-top:1px solid var(--border)}.gene-row{display:flex;align-items:center;gap:8px;width:100%;text-align:left;padding:15px 0;border:0;border-bottom:1px solid var(--border);background:transparent;color:var(--ink);cursor:pointer}.gene-identity{flex:1;min-width:0;overflow-wrap:anywhere}.gene-identity strong{display:block;font-size:13px;font-weight:500}.gene-identity small{display:block;font-size:10px;color:var(--faint);margin-top:3px}.row-arrow{color:var(--faint);font-size:12px}.delta-number{font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}.delta-number.positive{color:#a45c35}.delta-number.negative{color:var(--primary-strong)}.delta-number.missing{color:var(--faint);font-size:10px}.reading-note{font-size:10px;line-height:1.9;color:var(--muted);margin:18px 0 0}.overview-function-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.task-total{font-size:10px;color:var(--faint)}.coverage-summary{display:flex;gap:18px;flex-wrap:wrap;font-size:10px;color:var(--muted);margin-bottom:14px}.coverage-summary strong{font-weight:500;color:var(--ink);margin-left:3px}.category-list{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 16px}.category-list button{border:1px solid var(--border);border-radius:4px;padding:6px 9px;background:var(--card);font-size:10px;color:var(--muted);cursor:pointer}.category-list button[aria-pressed=true]{border-color:var(--primary);color:var(--primary-strong);background:var(--primary-weak)}.function-detail{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(210px,1fr);gap:20px;align-items:start}.task-selection{min-width:0}.task-list-heading{display:flex;justify-content:space-between;gap:12px;font-size:10px;color:var(--faint);padding:0 9px 9px}.task-list{display:grid;gap:4px;max-height:430px;overflow-y:auto;padding:2px}.task-row{display:flex;align-items:center;justify-content:space-between;gap:12px;text-align:left;padding:10px;border:1px solid transparent;border-radius:4px;background:var(--surface-soft);color:var(--ink);cursor:pointer;width:100%}.task-row[aria-pressed=true]{border-color:var(--primary);background:var(--primary-weak)}.task-identity{min-width:0;overflow-wrap:anywhere}.task-identity strong{display:block;font-size:11px;line-height:1.6;font-weight:500}.task-identity small{display:block;font-size:9px;color:var(--muted);margin-top:4px}.task-identity small.full{color:var(--primary-strong)}.task-row .delta-number{font-size:11px}.task-row .delta-number.missing{font-size:9px}.show-all{font-size:10px;color:var(--primary-strong);border:0;background:transparent;cursor:pointer;padding:12px 2px 0;text-align:left;line-height:1.7}.task-comparison{padding:18px;border:1px solid var(--border);border-radius:5px;min-width:0}.detail-label{font-size:10px;color:var(--faint);margin:0 0 9px}.task-comparison h4{font-size:14px;font-weight:500;line-height:1.6;margin:0;overflow-wrap:anywhere}.task-id{font-size:9px;color:var(--muted);line-height:1.6;overflow-wrap:anywhere;margin:6px 0 10px}.coverage-tag{display:inline-block;font-size:9px;padding:4px 6px;border:1px solid var(--border);border-radius:3px;color:var(--muted)}.coverage-tag.full{color:var(--primary-strong);background:var(--primary-weak);border-color:transparent}.comparison-bars{margin:22px 0 18px}.comparison-row{margin-bottom:16px}.bar-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:10px;color:var(--muted);margin-bottom:7px}.bar-heading strong{font-size:11px;font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums}.bar-track{height:9px;position:relative;background:var(--figure-track-bg);border-radius:2px}.bar-track.missing{background:repeating-linear-gradient(135deg,var(--border) 0,var(--border) 3px,var(--surface-soft) 3px,var(--surface-soft) 6px)}.bar-fill{position:absolute;top:0;height:100%;background:var(--border-strong);border-radius:1px}.bar-fill.predicted{background:var(--primary)}.bar-fill.observed{background:#bc8455}.zero-marker{position:absolute;top:-2px;height:13px;width:1px;background:var(--faint);z-index:1}.scale-labels{display:flex;justify-content:space-between;gap:5px;font-size:9px;color:var(--faint);font-variant-numeric:tabular-nums}.comparison-note,.missing-key{font-size:10px;line-height:1.8;color:var(--muted);margin:10px 0 0}.missing-key{font-size:9px;color:var(--faint)}.overview-footer{font-size:10px;line-height:1.8;color:var(--muted);background:var(--surface-soft);padding:13px 28px;border-top:1px solid var(--border)}.overview-empty{padding:36px 28px;border-top:1px solid var(--border);font-size:13px}.overview-empty strong{font-weight:500}.overview-empty p,.small-empty{font-size:12px;color:var(--muted);line-height:1.8}.gene-row:hover,.task-row:hover{background:var(--primary-weak)}button:focus-visible{outline:2px solid var(--primary);outline-offset:3px}
.gene-summary{display:flex;flex-direction:column;min-width:0}
.gene-list{display:grid;flex:1;grid-auto-rows:minmax(40px,1fr)}
.gene-row{min-height:40px;padding:10px 0}
@media(max-width:1350px){.overview-heading{padding:22px}.population-counts{padding-left:22px;padding-right:22px}.gene-summary,.function-summary{padding:18px}.overview-body{grid-template-columns:minmax(190px,.7fr) minmax(0,2fr)}.function-detail{gap:12px;grid-template-columns:minmax(0,1fr) minmax(190px,1fr)}.task-comparison{padding:14px}.evidence-notes{margin-left:22px;margin-right:22px}}
@media(max-width:1000px){.overview-body{grid-template-columns:1fr}.gene-summary{border-right:0;border-bottom:1px solid var(--border)}.gene-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:20px}.function-detail{grid-template-columns:minmax(0,1.1fr) minmax(210px,1fr)}}
@container(max-width:900px){.overview-body{grid-template-columns:1fr}.gene-summary{border-right:0;border-bottom:1px solid var(--border)}.gene-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:20px}}
@container(max-width:560px){.overview-heading{flex-wrap:wrap}.function-detail{grid-template-columns:1fr}.gene-list{grid-template-columns:1fr}.population-counts{gap:12px}}
.overview-heading{padding:18px 22px 10px;gap:16px}.overview-heading h2{font-size:22px}.eyebrow{margin:0 0 6px}.overview-subtitle{font-size:12px;margin:5px 0 0}.population-counts{padding:0 22px 12px;gap:18px;font-size:13px}.population-counts strong{font-size:16px}.result-key-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:13px 22px 17px;border-top:1px solid var(--border);margin-bottom:16px;background:var(--surface-soft)}.result-key-metrics>div{min-width:0;display:grid;gap:6px}.result-key-metrics span{font-size:12px;color:var(--muted)}.result-key-metrics strong{font-size:19px;font-weight:500;overflow-wrap:anywhere}.result-key-metrics small{font-size:12px;font-weight:400;color:var(--muted)}.evidence-notes{font-size:12px;margin:0 22px 16px}.task-identity strong{font-size:13px}.task-identity small,.task-id,.coverage-tag,.bar-heading,.comparison-note,.section-caption,.reading-note,.overview-footer{font-size:12px}.task-total,.coverage-summary,.category-list button,.show-all{font-size:12px}@container(max-width:650px){.result-key-metrics{grid-template-columns:repeat(2,minmax(0,1fr));padding:14px}.population-counts{gap:10px;padding-left:14px;padding-right:14px}.overview-heading{padding:16px 14px 10px}}
</style>
