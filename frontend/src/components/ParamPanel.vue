<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useCatalogStore } from '../stores/catalog'
import { useDraftStore } from '../stores/draft'
import { useRunStore } from '../stores/run'
import { useUiStore } from '../stores/ui'
import { isIntegerInRange } from '../utils/number'
import { buildDiagnostics, copyText, diagnosticsFromError } from '../utils/diagnostics'
import type { CellLine, RunMode } from '../types/run'

/**
 * 实验参数面板。
 * 运行开始后，本表单作为「下一次实验草稿」独立编辑，不改变当前结果标题。
 * 不静默替换不可用模式；预计算模式隐藏并锁定 n_cells / seed。
 */

const router = useRouter()
const props = withDefaults(defineProps<{ destination?: 'workbench' | 'detail'; horizontal?: boolean }>(), { destination: 'workbench', horizontal: false })
const catalog = useCatalogStore()
const draft = useDraftStore()
const runs = useRunStore()
const ui = useUiStore()

onMounted(() => {
  if (catalog.contexts.length === 0 && !catalog.loading) void catalog.load()
  if (draft.cellLine) void catalog.loadPerturbations(draft.cellLine, draft.mode)
})

watch(
  () => [draft.cellLine, draft.mode] as const,
  ([cellLine, mode]) => {
    perturbationQuery.value = draft.perturbation
    runs.clearSubmitState()
    void catalog.loadPerturbations(cellLine, mode)
  },
)

// ---------- 细胞背景 ----------
const cellOptions = computed(() =>
  catalog.contexts.map((ctx) => {
    const anyReady = ctx.online_ready || ctx.precomputed_ready || ctx.validation_ready
    const reason = !anyReady
      ? (ctx.disabled_reason ??
        (ctx.readiness_reasons.length > 0
          ? ctx.readiness_reasons.join('；')
          : '接口报告该背景当前不可用'))
      : null
    return { value: ctx.cell_line as CellLine, disabled: !anyReady, reason }
  }),
)

// ---------- 扰动：可搜索下拉，禁止任意文本 ----------
const perturbationQuery = ref(draft.perturbation)
watch(() => draft.perturbation, value => { perturbationQuery.value = value })
const dropdownOpen = ref(false)
const highlightIndex = ref(-1)
let dropdownCloseTimer: number | undefined
onBeforeUnmount(() => window.clearTimeout(dropdownCloseTimer))

const perturbationState = computed(() => catalog.perturbations[`${draft.cellLine}:${draft.mode}`] ?? null)

const filteredPerturbations = computed(() => {
  const items = perturbationState.value?.items ?? []
  const query = perturbationQuery.value.trim().toUpperCase()
  if (!query) return items
  return items.filter((item) => item.toUpperCase().includes(query))
})

function openDropdown(): void {
  window.clearTimeout(dropdownCloseTimer)
  dropdownOpen.value = true
  highlightIndex.value = -1
}

function closeDropdownSoon(): void {
  window.clearTimeout(dropdownCloseTimer)
  dropdownCloseTimer = window.setTimeout(() => {
    dropdownOpen.value = false
    // 失焦时若输入不是列表项，回退到已提交选择（禁止任意文本）
    const query = perturbationQuery.value.trim().toUpperCase()
    const items = perturbationState.value?.items ?? []
    if (items.includes(query)) {
      draft.perturbation = query
      perturbationQuery.value = query
    } else {
      perturbationQuery.value = draft.perturbation
    }
  }, 160)
}

function pickPerturbation(item: string): void {
  draft.perturbation = item
  perturbationQuery.value = item
  dropdownOpen.value = false
}

function onQueryKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    dropdownOpen.value = false
    return
  }
  const list = filteredPerturbations.value
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    dropdownOpen.value = true
    highlightIndex.value = Math.min(highlightIndex.value + 1, list.length - 1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlightIndex.value = Math.max(highlightIndex.value - 1, 0)
  } else if (event.key === 'Enter') {
    event.preventDefault()
    if (dropdownOpen.value && list.length > 0) {
      pickPerturbation(list[highlightIndex.value >= 0 ? highlightIndex.value : 0])
    }
  }
}

// ---------- 运行模式 ----------
const modeOptions = computed(() => {
  const ctx = catalog.contextFor(draft.cellLine)
  const reasons = ctx?.readiness_reasons ?? []
  const demoContexts = catalog.contexts.filter((item) => item.precomputed_ready).map((item) => item.cell_line)
  return [
    {
      value: 'online' as RunMode,
      label: '在线推演',
      ready: ctx?.online_ready ?? false,
      reason:
        ctx === null
          ? '细胞背景可用性尚未加载'
          : ctx.online_ready
            ? null
            : reasons.length > 0
              ? reasons.join('；')
              : '接口报告在线推演不可用',
    },
    {
      value: 'precomputed' as RunMode,
      label: '结果回放',
      ready: ctx?.precomputed_ready ?? false,
      reason:
        ctx === null
          ? '细胞背景可用性尚未加载'
          : ctx.precomputed_ready
            ? '读取已保存的真实模型结果，本次不重新计算'
            : `${draft.cellLine} 暂无可回放结果${demoContexts.length > 0 ? `；可切换至 ${demoContexts.join('、')} 使用结果回放` : ''}`,
    },
    {
      value: 'validation' as RunMode,
      label: '实测对照',
      ready: ctx?.validation_ready ?? false,
      reason: ctx?.validation_ready
        ? '仅开放有匹配实测数据的扰动；生成新预测并与登记观测比较'
        : '当前背景暂无已核验的实测对照数据与名单；已有结果可在实验记录查看',
    },
  ]
})

const unavailableModes = computed(() => modeOptions.value.filter((mode) => !mode.ready))

const selectedModeOption = computed(
  () => modeOptions.value.find((m) => m.value === draft.mode) ?? null,
)

const isPrecomputed = computed(() => draft.mode === 'precomputed')

// ---------- 高级参数校验 ----------
const nCellsError = computed(() => {
  if (isPrecomputed.value) return null
  if (!isIntegerInRange(draft.nCells, 64, 4096)) return 'n_cells 需为 64–4096 的整数'
  return null
})
const seedError = computed(() => {
  if (isPrecomputed.value) return null
  if (!isIntegerInRange(draft.seed, 0, 2147483647)) return 'seed 需为 0–2147483647 的整数'
  return null
})

const perturbationError = computed(() => {
  if (!draft.perturbation) return '请从列表中选择一个扰动基因'
  const items = perturbationState.value?.items ?? []
  if (!perturbationState.value || perturbationState.value.loading) return '正在读取该模式可用的扰动'
  if (perturbationState.value.error) return '扰动目录读取失败，请重试'
  if (!items.includes(draft.perturbation)) return '请从当前模式的可用列表重新选择扰动'
  return null
})

const canSubmit = computed(() => {
  if (runs.submitting) return false
  if (catalog.contexts.length === 0) return false
  if (!selectedModeOption.value?.ready) return false
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
    mode: draft.mode,
    n_cells: isPrecomputed.value ? 512 : Number(draft.nCells),
    seed: isPrecomputed.value ? 42 : Number(draft.seed),
  }
  const res = await runs.createRun(payload)
  if (!res) return
  ui.push(
    'success',
    res.cache_hit
      ? '已接收：复用已有结果（cache_hit），未重新计算'
      : '已接收：任务进入队列，等待执行',
  )
  await router.push(props.destination === 'workbench'
    ? { path: '/workbench', query: { run: res.run_id } }
    : { path: `/runs/${encodeURIComponent(res.run_id)}`, query: { tab: 'response' } })
}

function useAlternative(alt: string): void {
  runs.clearSubmitState()
  pickPerturbation(alt)
}

async function copySubmitDiagnostics(): Promise<void> {
  const text = runs.submitError
    ? diagnosticsFromError(runs.submitError, undefined, {
        cell_line: draft.cellLine,
        perturbation: draft.perturbation,
        mode: draft.mode,
        n_cells: draft.nCells,
        seed: draft.seed,
      })
    : buildDiagnostics({
        endpoint: 'POST /runs',
        params: {
          cell_line: draft.cellLine,
          perturbation: draft.perturbation,
          mode: draft.mode,
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
        <!-- 细胞背景 -->
        <div class="field">
          <span class="label" id="cell-line-label">细胞背景</span>
          <div class="choice-group cell-choice-group" role="radiogroup" aria-labelledby="cell-line-label">
            <label
              v-for="opt in cellOptions"
              :key="opt.value"
              class="choice"
              :class="{ selected: draft.cellLine === opt.value, disabled: opt.disabled }"
              :title="opt.disabled ? (opt.reason ?? '不可用') : undefined"
            >
              <input
                type="radio"
                name="cell-line"
                :value="opt.value"
                :checked="draft.cellLine === opt.value"
                :disabled="opt.disabled"
                @change="draft.setCellLine(opt.value)"
              />
              <span>
                <span class="choice-name">{{ opt.value }}</span>
                <span v-if="opt.disabled && opt.reason && !horizontal" class="choice-reason">
                  <br />{{ opt.reason }}
                </span>
              </span>
            </label>
          </div>
        </div>

        <!-- 扰动基因 -->
        <div class="field">
          <label class="label" for="perturbation-input">扰动基因</label>
          <div class="perturbation-box">
            <input
              id="perturbation-input"
              v-model="perturbationQuery"
              class="input"
              type="text"
              role="combobox"
              :aria-expanded="dropdownOpen"
              aria-controls="perturbation-listbox"
              aria-autocomplete="list"
              placeholder="搜索扰动基因…"
              autocomplete="off"
              :disabled="perturbationState?.loading"
              @focus="openDropdown"
              @click="openDropdown"
              @input="openDropdown"
              @blur="closeDropdownSoon"
              @keydown="onQueryKeydown"
            />
            <div
              v-if="dropdownOpen"
              id="perturbation-listbox"
              class="dropdown"
              role="listbox"
              aria-label="可选扰动基因"
            >
              <p v-if="perturbationState?.loading" class="dropdown-note">正在加载扰动列表…</p>
              <p v-else-if="filteredPerturbations.length === 0" class="dropdown-note">
                无匹配的可用扰动
              </p>
              <template v-else>
                <button
                  v-for="(item, index) in filteredPerturbations"
                  :key="item"
                  type="button"
                  role="option"
                  :aria-selected="draft.perturbation === item"
                  class="dropdown-item"
                  :class="{ highlighted: index === highlightIndex }"
                  @mousedown.prevent="pickPerturbation(item)"
                >
                  {{ item }}
                </button>
              </template>
            </div>
          </div>
          <p v-if="perturbationState?.error" class="field-error">
            扰动列表加载失败：{{ perturbationState.error.message }}
            <button class="btn btn-ghost btn-sm" @click="catalog.loadPerturbations(draft.cellLine, draft.mode, true)">
              重试
            </button>
          </p>
          <p v-else-if="perturbationError && draft.perturbation" class="field-error">
            {{ perturbationError }}
          </p>
        </div>

        <!-- 运行模式 -->
        <div class="field">
          <span class="label" id="mode-label">运行模式</span>
          <div class="choice-group" role="radiogroup" aria-labelledby="mode-label">
            <label
              v-for="opt in modeOptions"
              :key="opt.value"
              class="choice"
              :class="{ selected: draft.mode === opt.value, disabled: !opt.ready }"
              :title="!opt.ready ? (opt.reason ?? '不可用') : undefined"
            >
              <input
                type="radio"
                name="run-mode"
                :value="opt.value"
                :checked="draft.mode === opt.value"
                :disabled="!opt.ready"
                :aria-describedby="!opt.ready ? `mode-unavailable-${opt.value}` : undefined"
                @change="draft.mode = opt.value"
              />
              <span>
                <span class="choice-name">{{ opt.label }}</span>
                <span v-if="opt.ready && opt.reason && (!horizontal || draft.mode === opt.value)" class="choice-reason"><br />{{ opt.reason }}</span>
              </span>
            </label>
          </div>
          <ul v-if="unavailableModes.length" class="mode-availability" aria-label="模式可用性说明">
            <li v-for="opt in unavailableModes" :id="`mode-unavailable-${opt.value}`" :key="opt.value">
              <strong>{{ opt.label }}：</strong>{{ opt.reason }}。
            </li>
          </ul>
          <p v-if="selectedModeOption && !selectedModeOption.ready" class="field-error">
            当前选择的模式不可用：{{ selectedModeOption.reason }}。模式不会被自动替换，请手动调整。
          </p>
        </div>

        <!-- 高级参数 -->
        <div class="field advanced-field">
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :aria-expanded="draft.advancedOpen"
            @click="draft.advancedOpen = !draft.advancedOpen"
          >
            {{ draft.advancedOpen ? '收起高级参数' : '展开高级参数' }}
          </button>
          <div v-if="draft.advancedOpen" class="advanced">
            <template v-if="isPrecomputed">
              <p class="notice notice-info">
                结果回放读取既有结果文件：n_cells 与 seed 不改变既有结果，已锁定。
                这些是请求参数，不代表已保存结果最初生成参数；本次包的哈希见证据栏。
              </p>
            </template>
            <template v-else>
              <div>
              <label class="label" for="n-cells-input">采样细胞数</label>
              <input
                id="n-cells-input"
                v-model="draft.nCells"
                class="input"
                type="number"
                min="64"
                max="4096"
                step="1"
                inputmode="numeric"
              />
              <p v-if="nCellsError" class="field-error">{{ nCellsError }}</p>
              <p class="field-hint">可选范围 64–4096。</p>
              </div><div>
              <label class="label" for="seed-input" style="margin-top: 10px">随机种子</label>
              <input
                id="seed-input"
                v-model="draft.seed"
                class="input"
                type="number"
                min="0"
                max="2147483647"
                step="1"
                inputmode="numeric"
              />
              <p v-if="seedError" class="field-error">{{ seedError }}</p>
              <p class="field-hint">固定种子便于重现。</p>
              </div>
            </template>
          </div>
        </div>

        <!-- 提交 -->
        <button
          class="btn btn-primary submit-btn"
          type="button"
          :disabled="!canSubmit"
          :title="canSubmit ? undefined : '请先完成上方必填项与可用性检查'"
          @click="submit"
        >
          {{ runs.submitting ? '提交中…' : '开始实验' }}
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
              v-if="runs.submitError.status === 503 && draft.mode === 'online'"
              class="small"
              style="margin: 6px 0 0"
            >
              在线推演暂时不可用。参数已保留；也可以选择结果回放模式查看已保存的真实结果。
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
.horizontal>.card{display:grid;grid-template-columns:1fr 1fr 1.4fr;gap:22px 28px;padding:24px}.horizontal .card-title{grid-column:1/-1;font-size:15px}.horizontal .field{margin:0;min-width:0}.horizontal .choice-group{display:flex;flex-direction:row;flex-wrap:wrap;gap:8px}.horizontal .choice{flex:1;padding:10px;font-size:11px}.horizontal .choice-name{font-size:12px}.horizontal .choice-reason{font-size:10px;line-height:1.6}.horizontal .advanced-field,.horizontal .submit-btn,.horizontal .notice,.horizontal .skeleton-wrap{grid-column:1/-1}.horizontal .submit-btn{width:fit-content;min-width:170px;justify-self:end;font-size:13px;padding:11px 22px}.horizontal .advanced{max-width:500px;display:grid;grid-template-columns:1fr 1fr;gap:6px 16px}.horizontal .advanced label{margin-top:0!important}.horizontal .advanced .notice{grid-column:1/-1}@media(max-width:900px){.horizontal>.card{grid-template-columns:1fr 1fr}.horizontal>.card>.field:nth-of-type(3){grid-column:1/-1}}@media(max-width:600px){.horizontal>.card{grid-template-columns:1fr;padding:18px;gap:20px}.horizontal .submit-btn{width:100%}.horizontal .advanced{display:block}.horizontal .advanced label{margin-top:12px!important}.horizontal .choice{flex:1 1 100px}}
.param-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.cell-choice-group,
.horizontal .cell-choice-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 1fr;
}
.cell-choice-group .choice {
  min-width: 0;
  min-height: 42px;
  align-items: center;
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
.perturbation-box {
  position: relative;
}
.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  max-height: 240px;
  overflow-y: auto;
  background: var(--card);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-lg);
  z-index: 40;
  padding: 4px;
}
.dropdown-item {
  display: block;
  width: 100%;
  text-align: left;
  appearance: none;
  border: none;
  background: none;
  padding: 7px 10px;
  font-size: 13px;
  font-family: var(--font);
  border-radius: 6px;
  cursor: pointer;
  color: var(--ink);
}
.dropdown-item:hover,
.dropdown-item.highlighted {
  background: var(--primary-weak);
  color: var(--primary);
}
.dropdown-note {
  margin: 6px 10px;
  font-size: 12px;
  color: var(--muted);
}
.advanced {
  margin-top: 10px;
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
</style>
