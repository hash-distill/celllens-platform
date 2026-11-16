<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MeasuredSetup from '../components/MeasuredSetup.vue'
import ParamPanel from '../components/ParamPanel.vue'
import ControlledImport from '../components/ControlledImport.vue'
import { useDraftStore } from '../stores/draft'
import { useRunStore } from '../stores/run'
import { accessSession } from '../stores/access'
import type { CellLine } from '../types/run'
import { isIntegerInRange } from '../utils/number'

const route = useRoute(), router = useRouter(), draft = useDraftStore(), runs = useRunStore()
const reviewing = ref(false), importBusy = ref(false)
const options = [
  { id: 'measured', index: '01', label: '实测数据分析', tag: '比较已观察的细胞', description: '输入公开数据或自有 H5AD，对比对照组与扰动组的表达变化和功能支持。', scope: '真实 RNA 观测 → 表达响应与功能证据' },
  { id: 'prediction', index: '02', label: '基因扰动预测', tag: '探索模型支持的响应', description: '选择细胞背景与扰动基因，预测表达响应；有匹配实测时，进一步查看诊断对照。', scope: '背景与目标基因 → 预测表达与功能线索' },
]
const sources = [
  { id: 'measured', label: '公开数据', description: '选择固定公开来源中已收录的背景与扰动。' },
  { id: 'import', label: '自有 H5AD', description: '先由部署者将文件放入受控目录，再核对分组与表达尺度。' },
]
const selectedType = computed(() => typeof route.query.type === 'string' && ['measured', 'import', 'prediction'].includes(route.query.type) ? route.query.type : null)
const selected = computed(() => options.find(option => option.id === (selectedType.value === 'import' ? 'measured' : selectedType.value)) ?? null)
const step = computed(() => reviewing.value ? 3 : selected.value ? 2 : 1)
const locked = computed(() => draft.measuredSubmitting || runs.submitting || importBusy.value)
watch(() => route.query.type, () => { reviewing.value = false; importBusy.value = false }, { flush: 'sync' })
function choose(type: string) {
  if (locked.value || !['measured', 'import', 'prediction'].includes(type)) return
  reviewing.value = false
  // Internal task switches carry the edited draft, not stale parameters from the
  // link that originally opened the form. Each task keeps its own seed.
  void router.replace({ path: '/research', query: {
    ...route.query, type, cell_line: draft.cellLine, perturbation: draft.perturbation || undefined,
    max_cells: type === 'measured' ? draft.measuredMaxCells : undefined,
    seed: type === 'measured' ? draft.measuredSeed : type === 'prediction' ? draft.seed : undefined,
  } })
}
watch(() => [route.query.cell_line, route.query.perturbation], ([cellLine, perturbation]) => {
  if (typeof cellLine === 'string' && ['K562', 'RPE1', 'Jurkat', 'HepG2'].includes(cellLine)) draft.setCellLine(cellLine as CellLine)
  if (typeof perturbation === 'string') { const value = perturbation.trim().toUpperCase(); if (!value || (value.length <= 128 && /^[A-Z0-9][A-Z0-9._-]*$/.test(value))) draft.perturbation = value }
}, { immediate: true })
watch(() => [route.query.max_cells, route.query.seed], ([maxCells, seed]) => {
  if (typeof maxCells === 'string' && isIntegerInRange(maxCells, 1, 4096)) draft.measuredMaxCells = maxCells
  if (typeof seed === 'string' && isIntegerInRange(seed, 0, 2147483647)) { if (selectedType.value === 'measured') draft.measuredSeed = seed; else draft.seed = seed }
}, { immediate: true })
</script>

<template>
  <div class="page research-page">
    <header class="research-heading">
      <div><span class="eyebrow">RESEARCH STUDIO</span><h1>新建研究</h1><p>选择一项任务，设置输入，核对后提交。完成结果保留数据来源与方法记录。</p></div>
      <RouterLink to="/records" class="btn">继续已有研究 ↗</RouterLink>
    </header>
    <div class="research-steps" aria-label="研究创建步骤">
      <div v-for="(label, index) in ['选择分析任务', '设置输入与条件', '核对并提交']" :key="label" :class="{ active: step === index + 1, done: step > index + 1 }" :aria-current="step === index + 1 ? 'step' : undefined"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ label }}</div>
    </div>
    <section v-if="accessSession?.read_only" class="read-only-research"><h2>公开研究展览</h2><p>当前工作区展示已发布的研究结果。新建分析需要进入私人工作区。</p><RouterLink to="/records" class="btn btn-primary">浏览已发布结果</RouterLink></section>
    <template v-else>
      <div class="research-paths" aria-label="分析任务">
        <button v-for="option in options" :key="option.id" :class="['research-path', option.id, { chosen: selected?.id === option.id }]" :disabled="locked" :aria-pressed="selected?.id === option.id" @click="choose(option.id === 'measured' && selectedType === 'import' ? 'import' : option.id)">
          <div class="path-meta"><span>{{ option.index }} / {{ option.tag }}</span><i>{{ selected?.id === option.id ? '✓' : '↗' }}</i></div><h2>{{ option.label }}</h2><p>{{ option.description }}</p><small>{{ option.scope }}</small>
        </button>
      </div>
      <section v-if="selected" class="experiment-setup">
        <header class="setup-heading"><div><span class="eyebrow">02 / 研究条件</span><h2>{{ selected.label }}</h2><p>{{ selected.id === 'measured' ? '先选数据来源，再核对分组、表达尺度与采样条件。' : '预测结果用于提出假设；模型支持目标不代表独立泛化已经验证。' }}</p></div><RouterLink :to="{ path: '/data-catalog', query: { cell_line: draft.cellLine, perturbation: draft.perturbation || undefined } }">核对数据覆盖 →</RouterLink></header>
        <div v-if="selected.id === 'measured'" class="source-picker" role="group" aria-label="实测数据来源">
          <button v-for="source in sources" :key="source.id" :class="{ active: selectedType === source.id }" :aria-pressed="selectedType === source.id" :disabled="locked" @click="choose(source.id)"><strong>{{ source.label }}</strong><span>{{ source.description }}</span></button>
        </div>
        <MeasuredSetup v-if="selectedType === 'measured'" review-before-submit @review-change="reviewing = $event" />
        <ControlledImport v-else-if="selectedType === 'import'" @review-change="reviewing = $event" @busy-change="importBusy = $event" />
        <ParamPanel v-else destination="detail" horizontal review-before-submit @review-change="reviewing = $event" />
      </section>
      <section v-else class="research-start-note"><h2>已有实测数据，从比较开始</h2><p>选择“实测数据分析”可使用公开来源或自有 H5AD；需要探索基因扰动后的表达响应时，选择“基因扰动预测”。两项任务都可查看结果、核对来源并导出研究记录。</p><RouterLink to="/data-catalog">先查询细胞背景与数据覆盖 →</RouterLink></section>
    </template>
    <footer class="research-notes"><p>任务在后台执行，离开页面后可从实验记录继续查看。</p><RouterLink to="/methods/models">了解方法与解释范围 →</RouterLink></footer>
  </div>
</template>

<style scoped>
.research-page{max-width:1440px;margin:0 auto}.research-heading{display:flex;align-items:center;justify-content:space-between;gap:25px;padding:4px 0 24px}.eyebrow{font:12px Consolas,monospace;letter-spacing:1.2px;color:var(--primary)}h1{font-weight:500;font-size:32px;line-height:1.5;margin:12px 0 8px}.research-heading p{color:var(--muted);font-size:14px;line-height:1.8;margin:0}.research-steps{display:flex;gap:40px;border-block:1px solid var(--border);padding:16px 0;margin-bottom:24px}.research-steps>div{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--muted)}.research-steps span{font:12px Consolas,monospace;border:1px solid var(--border);border-radius:50%;width:30px;height:30px;display:grid;place-items:center;flex:none}.research-steps .active{color:var(--primary);font-weight:600}.research-steps .active span{background:var(--primary);color:#fff;border-color:var(--primary)}.research-steps .done span{background:var(--primary-weak);color:var(--primary)}.research-paths{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin-bottom:24px}.research-path{display:block;min-width:0;text-align:left;padding:23px 25px;background:#e5eddd;border:1px solid #c7d5bd;border-radius:15px;color:#1e432e;cursor:pointer;transition:transform .18s,border-color .18s,box-shadow .18s;font:inherit}.research-path.prediction{background:#dfeae4;border-color:#bfd1c9}.research-path.chosen{border-color:#356a44;box-shadow:inset 0 0 0 1px #356a44,0 8px 20px #1a432a0c}.research-path:hover{transform:translateY(-2px);box-shadow:0 8px 30px #1a432a13}.research-path:disabled{cursor:wait;transform:none}.path-meta{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:#50684b}.path-meta i{font-style:normal;font-size:18px}.research-path h2{font-size:22px;font-weight:500;margin:16px 0 10px}.research-path p{font-size:14px;line-height:1.8;color:#4c624b;margin:0 0 17px}.research-path small{font-size:12px;color:#50684b}.experiment-setup{border:1px solid var(--border);background:var(--card);border-radius:18px;overflow:visible}.setup-heading{padding:24px 28px;display:flex;justify-content:space-between;gap:25px;border-bottom:1px solid var(--border);align-items:center}.setup-heading h2{font-size:21px;font-weight:500;margin:10px 0}.setup-heading p{font-size:14px;line-height:1.8;color:var(--muted);margin:0}.setup-heading a{font-size:13px;color:var(--primary);white-space:nowrap}.source-picker{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:22px 28px 0}.source-picker button{text-align:left;font:inherit;color:var(--ink);background:var(--card-soft);border:1px solid var(--border);border-radius:10px;padding:15px 18px;cursor:pointer}.source-picker button.active{border-color:var(--primary);box-shadow:inset 0 0 0 1px var(--primary);background:var(--primary-weak)}.source-picker strong{display:block;font-size:15px;font-weight:600;margin-bottom:8px}.source-picker span{display:block;font-size:13px;line-height:1.7;color:var(--muted)}.source-picker button:disabled{cursor:wait}.experiment-setup :deep(.param-panel>.card){border:0;margin:0;background:transparent}.research-notes{display:flex;justify-content:space-between;gap:20px;margin-top:22px;font-size:12px;color:var(--muted);line-height:1.8}.research-notes p{margin:0}.research-notes a{color:var(--primary)}.research-start-note,.read-only-research{padding:28px;border:1px solid var(--border);border-radius:15px;background:var(--card)}.research-start-note h2,.read-only-research h2{font-size:21px;font-weight:500;margin:0 0 12px}.research-start-note p,.read-only-research p{font-size:14px;color:var(--muted);max-width:800px;line-height:1.9}.research-start-note a{display:inline-block;margin-top:8px;font-size:13px;color:var(--primary)}
:global(html[data-theme='dark']) .research-path{background:#2a442e;border-color:#41613d;color:#d8e6cd}:global(html[data-theme='dark']) .research-path.prediction{background:#264135;border-color:#3e6151}:global(html[data-theme='dark']) .research-path p,:global(html[data-theme='dark']) .research-path small,:global(html[data-theme='dark']) .path-meta{color:#b5c9aa}
@media(max-width:900px){.research-heading,.setup-heading{align-items:flex-start;flex-direction:column;gap:16px}.research-steps{gap:14px;justify-content:space-between}.research-steps>div{gap:7px;font-size:12px}.research-notes{flex-direction:column;gap:8px}.experiment-setup :deep(.horizontal>.card){grid-template-columns:1fr}.experiment-setup :deep(.horizontal .perturbation-field){grid-column:1}}
@media(max-width:600px){.research-paths,.source-picker{grid-template-columns:1fr}.research-path{padding:20px}.research-steps>div{flex-direction:column;align-items:flex-start;line-height:1.6}.research-heading h1{font-size:28px}.source-picker{padding:18px 18px 0}.setup-heading{padding:22px 18px}.research-start-note,.read-only-research{padding:24px}}
@media(prefers-reduced-motion:reduce){.research-path{transition:none}.research-path:hover{transform:none}}
</style>
