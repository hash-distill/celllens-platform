<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { measuredApi } from '../api/measured'
import { ApiError } from '../api/http'
import { useDraftStore } from '../stores/draft'
import { isIntegerInRange } from '../utils/number'
import type { MeasuredCoverage } from '../types/measured'
import type { CellLine, PerturbationList } from '../types/run'
import CellBackgroundPicker from './CellBackgroundPicker.vue'
import GenePicker from './GenePicker.vue'
import SubmissionReview from './SubmissionReview.vue'
const props=withDefaults(defineProps<{reviewBeforeSubmit?:boolean}>(),{reviewBeforeSubmit:false})
const emit=defineEmits<{'review-change':[open:boolean]}>()
const reviewing=ref(false)
function review(open:boolean){reviewing.value=open;emit('review-change',open)}

const router = useRouter(), draft = useDraftStore()
const cellOptions = ['K562', 'RPE1', 'Jurkat', 'HepG2'].map(value => ({value:value as CellLine}))
const coverage = ref<MeasuredCoverage | null>(null), coverageLoading = ref(false), coverageError = ref('')
const choices = ref<PerturbationList | null>(null), choicesLoading = ref(false), choicesError = ref(''), choicesRefresh = ref(0)
const actionError = ref(''), coverageRefresh = ref(0)
const lifetime = new AbortController()
const maxCellsError = computed(() => isIntegerInRange(draft.measuredMaxCells, 1, 4096) ? '' : '目标实测细胞上限需为 1–4096 的整数')
const seedError = computed(() => isIntegerInRange(draft.measuredSeed, 0, 2147483647) ? '' : '采样种子需为 0–2147483647 的整数')
const canStart = computed(() => !!draft.perturbation.trim() && !choicesLoading.value && !choicesError.value && !!choices.value?.items.includes(draft.perturbation) && !maxCellsError.value && !seedError.value && coverage.value?.source_status === 'measured' && !coverageLoading.value && !draft.measuredSubmitting && !draft.measuredUncertain)
const catalogTarget = computed(() => ({path:'/data-catalog', query:{cell_line:draft.cellLine, perturbation:draft.perturbation}}))

watch([() => draft.cellLine, choicesRefresh], async ([cellLine], _old, cleanup) => {
  const controller = new AbortController(); cleanup(() => controller.abort())
  choices.value=null;choicesLoading.value=true;choicesError.value=''
  try {
    const result = await measuredApi.choices(String(cellLine), controller.signal)
    if (!controller.signal.aborted) choices.value=result
  } catch (error) { if (!controller.signal.aborted) choicesError.value=error instanceof Error ? error.message : '实测扰动目录读取失败' }
  finally { if (!controller.signal.aborted) choicesLoading.value=false }
}, {immediate:true})
watch([() => draft.cellLine, () => draft.perturbation, coverageRefresh], (_value, _old, cleanup) => {
  const controller = new AbortController()
  coverage.value = null; coverageError.value = ''; coverageLoading.value = !!draft.perturbation.trim()
  const timer = window.setTimeout(async () => {
    if (!draft.perturbation.trim()) { coverageLoading.value = false; return }
    try {
      const result = await measuredApi.coverage(draft.cellLine, draft.perturbation.trim().toUpperCase(), controller.signal)
      if (!controller.signal.aborted) coverage.value = result
    } catch (error) { if (!controller.signal.aborted) coverageError.value = error instanceof Error ? error.message : '读取失败，请重试' }
    finally { if (!controller.signal.aborted) coverageLoading.value = false }
  }, 250)
  cleanup(() => { window.clearTimeout(timer); controller.abort() })
}, {immediate:true})

async function start(confirmed=false) {
  if (!canStart.value) return
  if(props.reviewBeforeSubmit&&!confirmed){review(true);return}
  review(false)
  draft.measuredSubmitting = true; actionError.value = ''
  const payload = {cell_line:draft.cellLine, perturbation:draft.perturbation.trim().toUpperCase(), max_cells:Number(draft.measuredMaxCells), seed:Number(draft.measuredSeed)}
  let postStarted = false
  try {
    const source = await measuredApi.coverage(payload.cell_line, payload.perturbation, lifetime.signal)
    if (source.source_status !== 'measured') {
      coverage.value = source
      throw new Error('当前固定源未确认该组合的实测数据，请先查看数据目录')
    }
    postStarted = true; draft.measuredUncertain = true
    const record = await measuredApi.create(payload, lifetime.signal)
    if (lifetime.signal.aborted) return
    draft.measuredUncertain = false
    await router.push(`/measured/${encodeURIComponent(record.id)}`)
  } catch (error) {
    if (lifetime.signal.aborted) return
    actionError.value = error instanceof Error ? error.message : '提交失败，请重试'
    draft.measuredUncertain = postStarted && error instanceof ApiError && ['network', 'timeout'].includes(error.kind)
  } finally { draft.measuredSubmitting = false }
}
onBeforeUnmount(() => lifetime.abort())
</script>

<template>
  <form class="measured-setup" @submit.prevent="start()">
    <fieldset :disabled="draft.measuredSubmitting" class="measured-fields">
      <div class="measured-context"><CellBackgroundPicker :model-value="draft.cellLine" :options="cellOptions" compact @update:model-value="draft.setCellLine" />
        <div class="sampling-fields"><div><label class="label" for="measured-cap">目标实测细胞上限</label><input id="measured-cap" v-model="draft.measuredMaxCells" type="number" min="1" max="4096" step="1" class="input" aria-describedby="measured-cap-hint"/><p v-if="maxCellsError" class="field-error">{{ maxCellsError }}</p><p id="measured-cap-hint" class="field-hint">1–4096；控制实测扰动组采样上限，对照数量另行核验。</p></div><div><label class="label" for="measured-seed">采样种子</label><input id="measured-seed" v-model="draft.measuredSeed" type="number" min="0" max="2147483647" step="1" class="input"/><p v-if="seedError" class="field-error">{{ seedError }}</p><p class="field-hint">固定种子便于重现。</p></div></div>
      </div>
      <div class="measured-target"><GenePicker v-model="draft.perturbation" :context="draft.cellLine" :items="choices?.items ?? []" :genes="choices?.genes" :categories="choices?.categories" :loading="choicesLoading" :error="choicesError" :warning="choices?.classification?.warning" @retry="choicesRefresh++">
      </GenePicker></div>
      <div class="measured-support">
        <div class="coverage-state" role="status"><span v-if="coverageLoading">正在核对固定源覆盖…</span><template v-else-if="coverageError"><span>覆盖读取失败：{{ coverageError }}</span><button type="button" class="btn btn-sm" @click="coverageRefresh++">重试覆盖查询</button></template><template v-else-if="coverage?.source_status === 'measured'"><strong>固定源有实测数据</strong><span>源中扰动细胞 {{ coverage.source_cell_count ?? '未知' }} 个</span><span>{{ coverage.local_verified ? `本地已核验 ${coverage.local_measured_cells} 个实测扰动细胞` : '启动时按需读取这一组合的数据' }}</span></template><span v-else-if="coverage?.source_status === 'not_in_source'">当前固定源未收录该组合的实测数据，可切换实验类型查看模型预测。</span><span v-else-if="coverage?.source_status === 'unknown'">该组合的源覆盖尚未确认，暂不能启动实测分析。</span><span v-else>输入扰动基因后核对实测覆盖。</span><span v-if="coverage && !coverage.model_supported">该组合未列入当前模型的支持词表，不影响已确认数据的实测分析。</span></div>
        <RouterLink :to="catalogTarget" class="catalog-link">查询这一组合的数据覆盖 →</RouterLink>
      </div>
    </fieldset>
    <p v-if="actionError" class="notice notice-danger" role="alert">{{ actionError }}</p>
    <div v-if="draft.measuredUncertain" class="notice notice-warn" role="alert"><p>提交结果待确认。请先核对实验记录，避免重复创建。</p><div class="btn-row"><RouterLink to="/records?category=measured" class="btn btn-sm">核对实测记录</RouterLink><button class="btn btn-sm" type="button" :disabled="draft.measuredSubmitting" @click="draft.measuredUncertain=false">已核对记录，允许再次提交</button></div></div>
    <button class="btn btn-primary measured-submit" type="submit" :disabled="!canStart">{{ draft.measuredSubmitting ? '正在提交…' : '开始实测分析' }}</button>
  </form>
<SubmissionReview v-if="reviewing" title="核对实测分析" :parameters="{'分析类型':'公开实测','细胞背景':draft.cellLine,'扰动目标':draft.perturbation,'目标细胞上限':draft.measuredMaxCells,'采样种子':draft.measuredSeed}" @cancel="review(false)" @confirm="start(true)"/></template>

<style scoped>
.measured-setup{padding:24px;display:grid;gap:18px}.measured-fields{padding:0;margin:0;border:0;min-width:0;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.6fr);gap:32px}.measured-fields>div{min-width:0}.measured-fields .label{margin:0 0 8px}.measured-fields .input,.measured-fields .select{width:100%;min-height:42px}.sampling-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:24px}.field-hint{font-size:11px;color:var(--muted);line-height:1.8;margin:8px 0 0}.field-error{font-size:12px;color:var(--danger)}.coverage-state{margin:16px 0;padding:15px;font-size:12px;line-height:1.9;color:var(--muted)}.coverage-state span{display:block}.coverage-state strong{color:var(--primary);font-weight:500}.catalog-link{font-size:12px;color:var(--primary)}.measured-submit{justify-self:end;min-width:170px;padding:11px 22px;font-size:13px}.notice p{margin-top:0}@media(max-width:900px){.measured-fields{grid-template-columns:1fr;gap:24px}}@media(max-width:480px){.sampling-fields{grid-template-columns:1fr}}

.measured-fields>.measured-context,.measured-fields>.measured-target{display:contents}
.measured-context :deep(.cell-background-picker){grid-column:1;grid-row:1;display:flex;flex-direction:column}
.measured-context :deep(.cell-choice-group){flex:1}
.measured-context .sampling-fields{grid-column:1;grid-row:2;margin-top:0;align-content:start}
.measured-target :deep(.gene-picker){display:contents}
.measured-target :deep(.gene-picker-controls){grid-column:2;grid-row:1;min-width:0}
.measured-target :deep(.gene-picker-details){grid-column:2;grid-row:2;min-width:0}
.measured-target :deep(.gene-picker-details>:first-child){margin-top:0}
.measured-support{grid-column:1/-1;border-top:1px solid var(--border);padding-top:18px}
.measured-support .coverage-state{padding:0;margin:0 0 10px}
@media(max-width:900px){
  .measured-context :deep(.cell-background-picker),.measured-context .sampling-fields,.measured-target :deep(.gene-picker-controls),.measured-target :deep(.gene-picker-details){grid-column:1;grid-row:auto}
}
</style>
