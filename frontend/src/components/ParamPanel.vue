<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCatalogStore } from '../stores/catalog'
import { useDraftStore } from '../stores/draft'
import { useRunStore } from '../stores/run'
import { useUiStore } from '../stores/ui'
import { isIntegerInRange } from '../utils/number'
import { buildDiagnostics, copyText, diagnosticsFromError } from '../utils/diagnostics'
import type { CellLine } from '../types/run'
import { dataCatalogApi, type CatalogPair } from '../api/dataCatalog'
import GenePicker from './GenePicker.vue'
import CellBackgroundPicker from './CellBackgroundPicker.vue'

/**
 * 实验参数面板。
 * 运行开始后，本表单作为「下一次实验草稿」独立编辑，不改变当前结果标题。
 * 新建实验统一执行在线推演；已有结果从实验记录读取。
 */

const router = useRouter()
const props = withDefaults(defineProps<{ destination?: 'workbench' | 'detail'; horizontal?: boolean }>(), { destination: 'workbench', horizontal: false })
const catalog = useCatalogStore()
const draft = useDraftStore()
const runs = useRunStore()
const ui = useUiStore()

onMounted(() => {
  draft.mode = 'online'
  if (catalog.contexts.length === 0 && !catalog.loading) void catalog.load()
  if (draft.cellLine) void catalog.loadPerturbations(draft.cellLine, 'online')
})

watch(
  () => draft.cellLine,
  (cellLine) => {
    runs.clearSubmitState()
    void catalog.loadPerturbations(cellLine, 'online')
  },
)

// ---------- 细胞背景 ----------
const cellOptions = computed(() =>
  catalog.contexts.map((ctx) => {
    const ready = ctx.online_ready
    const reason = !ready
      ? (ctx.disabled_reason ??
        (ctx.readiness_reasons.length > 0
          ? ctx.readiness_reasons.join('；')
          : '该背景暂不可用'))
      : null
    return { value: ctx.cell_line as CellLine, disabled: !ready, reason }
  }),
)

const perturbationState = computed(() => catalog.perturbations[`${draft.cellLine}:online`] ?? null)
const measuredOptions = computed(() => perturbationState.value?.measured_comparisons ?? [])
const geneCategories = computed(() => perturbationState.value?.categories ?? [])
const sourceCoverage = ref<CatalogPair | null>(null), sourceLoading = ref(false), sourceError = ref(''), sourceRefresh = ref(0)
const measuredTarget = computed(() => ({ path: '/research', query: { type: 'measured', cell_line: draft.cellLine, perturbation: draft.perturbation } }))
const catalogTarget = computed(() => ({ path: '/data-catalog', query: { cell_line: draft.cellLine, perturbation: draft.perturbation } }))
watch([() => draft.cellLine, () => draft.perturbation, sourceRefresh], (_value, _old, cleanup) => {
  const controller = new AbortController()
  sourceCoverage.value = null; sourceError.value = ''; sourceLoading.value = !!draft.perturbation
  const timer = window.setTimeout(async () => {
    if (!draft.perturbation) { sourceLoading.value = false; return }
    try {
      const result = await dataCatalogApi.pair(draft.cellLine, draft.perturbation, controller.signal)
      if (!controller.signal.aborted) sourceCoverage.value = result
    } catch (error) { if (!controller.signal.aborted) sourceError.value = error instanceof Error ? error.message : '实测覆盖读取失败' }
    finally { if (!controller.signal.aborted) sourceLoading.value = false }
  }, 200)
  cleanup(() => { window.clearTimeout(timer); controller.abort() })
}, { immediate: true })
// ---------- 在线服务可用性 ----------
const onlineReady = computed(() => catalog.contextFor(draft.cellLine)?.online_ready ?? false)
const onlineReason = computed(() => catalog.contextFor(draft.cellLine)?.readiness_reasons.join('；') || '在线推演服务暂不可用')

// ---------- 采样参数校验 ----------
const nCellsError = computed(() => {
  if (!isIntegerInRange(draft.nCells, 64, 4096)) return '预测细胞数需为 64–4096 的整数'
  return null
})
const seedError = computed(() => {
  if (!isIntegerInRange(draft.seed, 0, 2147483647)) return '随机种子需为 0–2147483647 的整数'
  return null
})

const perturbationError = computed(() => {
  if (!draft.perturbation) return '请从列表中选择一个扰动基因'
  const items = perturbationState.value?.items ?? []
  if (!perturbationState.value || perturbationState.value.loading) return '正在读取在线推演可用的扰动'
  if (perturbationState.value.error) return '扰动目录读取失败，请重试'
  if (!items.includes(draft.perturbation)) return '请从当前背景的可用列表重新选择扰动'
  return null
})

const canSubmit = computed(() => {
  if (runs.submitting) return false
  if (catalog.contexts.length === 0) return false
  if (!onlineReady.value) return false
  if (perturbationError.value) return false
  if (nCellsError.value || seedError.value) return false
  return true
})

// ---------- 提交 ----------
const submitAlternatives = computed(() => {
  const extras = runs.submitError?.extras
  const alt = extras?.supported_alternatives
  return Array.isArray(alt) ? alt.map((x) => String(x)) : []
})

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  const payload = {
    cell_line: draft.cellLine,
    perturbation: draft.perturbation.trim().toUpperCase(),
    mode: 'online' as const,
    n_cells: Number(draft.nCells),
    seed: Number(draft.seed),
  }
  const res = await runs.createRun(payload)
  if (!res) return
  ui.push(
    'success',
    res.cache_hit
      ? '已找到相同参数的结果，正在打开'
      : '已接收：任务进入队列，等待执行',
  )
  await router.push(props.destination === 'workbench'
    ? { path: '/workbench', query: { run: res.run_id } }
    : { path: `/runs/${encodeURIComponent(res.run_id)}` })
}

function useAlternative(alt: string): void {
  runs.clearSubmitState()
  draft.perturbation = alt
}

async function copySubmitDiagnostics(): Promise<void> {
  const text = runs.submitError
    ? diagnosticsFromError(runs.submitError, undefined, {
        cell_line: draft.cellLine,
        perturbation: draft.perturbation,
        mode: 'online',
        n_cells: draft.nCells,
        seed: draft.seed,
      })
    : buildDiagnostics({
        endpoint: 'POST /runs',
        params: {
          cell_line: draft.cellLine,
          perturbation: draft.perturbation,
          mode: 'online',
          n_cells: draft.nCells,
          seed: draft.seed,
        },
        message: '提交超时，结果待确认',
      })
  const ok = await copyText(text)
  ui.push(ok ? 'success' : 'error', ok ? '诊断信息已复制' : '复制失败，请手动记录')
}
</script>

<template>
  <div class="param-panel" :class="{horizontal}">
    <section class="card" aria-label="实验参数">
      <h2 v-if="!horizontal" class="card-title">实验设置 <span class="micro" style="float:right">SETUP</span></h2>

      <!-- catalog 加载失败 -->
      <div v-if="catalog.error" class="notice notice-danger">
        细胞背景可用性加载失败：{{ catalog.error.message }}
        <button class="btn btn-sm" style="margin-left: 8px" @click="catalog.load()">重试</button>
      </div>
      <div v-else-if="catalog.loading && catalog.contexts.length === 0" class="skeleton-wrap">
        <div class="skeleton" style="height: 64px"></div>
        <div class="skeleton" style="height: 64px"></div>
      </div>

      <template v-else>
        <!-- 细胞背景与采样参数 -->
        <div class="field context-field">
          <CellBackgroundPicker :model-value="draft.cellLine" :options="cellOptions" :compact="horizontal" @update:model-value="draft.setCellLine" />
          <div class="sampling-fields">
            <div class="sampling-field">
              <label class="label" for="n-cells-input">预测采样细胞数</label>
              <input id="n-cells-input" v-model="draft.nCells" class="input" type="number" min="64" max="4096" step="1" inputmode="numeric" aria-describedby="n-cells-hint" />
              <p v-if="nCellsError" class="field-error">{{ nCellsError }}</p>
              <p id="n-cells-hint" class="field-hint">请求生成 64–4096 个预测样本，不改变真实对照数。<RouterLink :to="{path:'/methods/backgrounds',query:{cell_line:draft.cellLine},hash:'#control-sampling'}">了解对照与采样</RouterLink></p>
            </div>
            <div class="sampling-field">
              <label class="label" for="seed-input">随机种子</label>
              <input id="seed-input" v-model="draft.seed" class="input" type="number" min="0" max="2147483647" step="1" inputmode="numeric" />
              <p v-if="seedError" class="field-error">{{ seedError }}</p>
              <p class="field-hint">固定种子便于重现。</p>
            </div>
          </div>
        </div>

        <!-- 扰动基因 -->
        <div class="field perturbation-field">
          <GenePicker v-model="draft.perturbation" :context="draft.cellLine" :items="perturbationState?.items ?? []" :genes="perturbationState?.genes" :categories="geneCategories" :loading="perturbationState?.loading ?? true" :error="perturbationState?.error?.message" :warning="perturbationState?.classification?.warning" @retry="catalog.loadPerturbations(draft.cellLine, 'online', true)">
          <div v-if="draft.perturbation" class="source-coverage" aria-live="polite">
            <p v-if="sourceLoading">正在核对当前固定源的实测覆盖…</p>
            <template v-else-if="sourceCoverage?.source_status === 'measured'"><strong>该组合在固定源中有实测数据</strong><p>源中有 {{ sourceCoverage.source_cell_count ?? '未知数量的' }} 个目标扰动细胞；{{ sourceCoverage.local_verified ? '本地已有经核验的实测数据。' : '实测分析可按需读取这一组合。' }}</p><RouterLink :to="measuredTarget" class="btn btn-primary btn-sm">直接分析实测数据</RouterLink><p>如需评估模型，可明确运行下方预测，再在结果的“实测对比”中查看可用评估。</p></template>
            <p v-else-if="sourceCoverage?.source_status === 'not_in_source'">当前固定源未收录该组合的实测数据，可在模型支持范围内进行探索性预测。源缺失不表示全球未测，预测完成也不证明泛化能力。</p>
            <p v-else-if="sourceCoverage?.source_status === 'unknown'">该组合的实测覆盖尚未确认。可查询数据目录；模型支持范围与已验证泛化是不同信息。</p>
            <p v-else-if="sourceError">实测覆盖读取失败：{{ sourceError }} <button type="button" class="btn btn-sm" @click="sourceRefresh++">重试覆盖</button></p>
            <RouterLink :to="catalogTarget" class="source-catalog-link">查看该组合的数据覆盖 →</RouterLink>
          </div>
          <div v-if="measuredOptions.length" class="measured-shortcuts"><span>本地已备实测对比：</span><button v-for="item in measuredOptions" :key="item.perturbation" type="button" @click="draft.perturbation=item.perturbation">{{item.perturbation}} · {{item.measured_cells}} 个实测细胞</button></div>
          </GenePicker>
          <p v-if="perturbationError && draft.perturbation && !perturbationState?.error" class="field-error">
            {{ perturbationError }}
          </p>
        </div>

        <p v-if="!onlineReady" class="notice notice-warn">
          {{ onlineReason }}。<RouterLink to="/records">查看实验记录</RouterLink>
        </p>

        <!-- 提交 -->
        <button
          class="btn btn-primary submit-btn"
          type="button"
          :disabled="!canSubmit"
          :title="canSubmit ? undefined : '请先完成上方必填项与可用性检查'"
          @click="submit"
        >
          {{ runs.submitting ? '提交中…' : '运行模型预测' }}
        </button>

        <!-- 提交结果 -->
        <div v-if="runs.submitTimeoutPending" class="notice notice-warn" style="margin-top: 12px">
          <strong>提交结果待确认：</strong>创建请求超时，服务端可能已接收该任务。
          为避免重复提交，不会自动重发；请稍后在「实验记录」中确认。
          参数已保留在表单中。
          <div class="btn-row" style="margin-top: 8px">
            <button class="btn btn-sm" @click="copySubmitDiagnostics">复制诊断信息</button>
            <button class="btn btn-ghost btn-sm" @click="runs.clearSubmitState()">我已了解</button>
          </div>
        </div>

        <div v-else-if="runs.submitError" class="notice notice-danger" style="margin-top: 12px">
          <template v-if="runs.submitError.code === 'UNSUPPORTED_PERTURBATION'">
            <strong>不支持的扰动：</strong>{{ runs.submitError.message }}
            <div v-if="submitAlternatives.length > 0" class="alt-row">
              <span class="small">可改为：</span>
              <button
                v-for="alt in submitAlternatives"
                :key="alt"
                class="btn btn-sm"
                type="button"
                @click="useAlternative(alt)"
              >
                {{ alt }}
              </button>
            </div>
          </template>
          <template v-else>
            <strong>提交失败：</strong>{{ runs.submitError.message }}
            <div v-if="runs.submitError.fieldErrors.length > 0" class="small">
              <p v-for="fe in runs.submitError.fieldErrors" :key="fe.loc" style="margin: 2px 0">
                字段 {{ fe.loc }}：{{ fe.msg }}
              </p>
            </div>
            <p v-if="runs.submitError.code" class="small mono" style="margin: 4px 0 0">
              错误码：{{ runs.submitError.code }}
            </p>
            <p
              v-if="runs.submitError.status === 503"
              class="small"
              style="margin: 6px 0 0"
            >
              在线推演暂时不可用。参数已保留；可从<RouterLink to="/records">实验记录</RouterLink>查看已保存结果。
            </p>
          </template>
          <div class="btn-row" style="margin-top: 8px">
            <button class="btn btn-sm" @click="copySubmitDiagnostics">复制诊断信息</button>
            <button class="btn btn-ghost btn-sm" @click="runs.clearSubmitState()">关闭</button>
          </div>
        </div>
      </template>
    </section>

  </div>
</template>

<style scoped>
.sampling-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-top:24px}.sampling-field{min-width:0}.sampling-field .label{margin-top:0}.sampling-field .input{width:100%}
.horizontal .perturbation-field{grid-column:2/-1}
.horizontal>.card{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.6fr);gap:22px 28px;padding:24px}.horizontal .card-title{grid-column:1/-1;font-size:15px}.horizontal .field{margin:0;min-width:0}.horizontal .submit-btn,.horizontal .notice,.horizontal .skeleton-wrap{grid-column:1/-1}.horizontal .submit-btn{width:fit-content;min-width:170px;justify-self:end;font-size:13px;padding:11px 22px}
.param-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mode-availability {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
.mode-availability li + li {
  margin-top: 6px;
}
.submit-btn {
  width: 100%;
  padding: 10px;
  font-size: 15px;
}
.alt-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 8px;
}
.skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.measured-shortcuts{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0;font-size:10px;color:var(--muted)}.measured-shortcuts>span,.measured-shortcuts>small{flex-basis:100%;line-height:1.8}.measured-shortcuts>button{background:var(--card);border:1px solid var(--border);color:var(--primary);padding:6px 9px;cursor:pointer;font:inherit}
.source-coverage{margin:12px 0;padding:0;font-size:11px;line-height:1.8;color:var(--muted)}.source-coverage>strong{font-weight:500;color:var(--primary)}.source-coverage>p{margin:7px 0}.source-coverage .btn{font-size:11px}.source-catalog-link{display:inline-block;margin-top:6px;color:var(--primary)}
</style>
