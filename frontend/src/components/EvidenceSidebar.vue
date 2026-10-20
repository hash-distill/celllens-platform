<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore, type RunEntry } from '../stores/run'
import { useCatalogStore } from '../stores/catalog'
import { useUiStore } from '../stores/ui'
import { fmtPercent, fmtServerTime, MODE_LABEL } from '../utils/format'
import { buildDiagnostics, copyText } from '../utils/diagnostics'
import { isSyntheticResult, runSourceLabel } from '../utils/source'

/**
 * 固定证据栏：运行编号、请求参数、模型背景、覆盖信息、警告与错误码、
 * 溯源占位与「复制诊断信息」。
 */

const props = defineProps<{ entry: RunEntry }>()

const runs = useRunStore()
const catalog = useCatalogStore()
const ui = useUiStore()

const record = computed(() => props.entry.record)

const context = computed(() =>
  record.value ? catalog.contextFor(record.value.request.cell_line) : null,
)

const coverage = computed(() => props.entry.summary.data?.coverage ?? null)
const provenance = computed(() => props.entry.provenance)

/** 汇总本运行最近一次错误（用于诊断信息） */
const latestError = computed(() => {
  const blocks = [
    props.entry.recordError,
    props.entry.summary.error,
    props.entry.projection.error,
    props.entry.genes.error,
    props.entry.tasks.error,
    props.entry.reactions.error,
  ]
  return blocks.find((e) => e !== null && e !== undefined) ?? null
})

async function copyDiagnostics(): Promise<void> {
  const rec = record.value
  const err = latestError.value
  const text = buildDiagnostics({
    endpoint: err?.endpoint ?? (rec ? `GET /runs/${rec.run_id}` : undefined),
    httpStatus: err?.status ?? undefined,
    runId: rec?.run_id ?? props.entry.runId,
    params: rec?.request,
    errorCode: err?.code ?? rec?.error_code ?? undefined,
    message: err?.message ?? rec?.error_message ?? undefined,
    extraLines: rec
      ? [
          `运行状态: ${rec.status}`,
          `模式: ${rec.request.mode}`,
          `警告数: ${rec.warnings.length}`,
        ]
      : [],
  })
  const ok = await copyText(text)
  ui.push(ok ? 'success' : 'error', ok ? '诊断信息已复制' : '复制失败，请手动记录')
}
</script>

<template>
  <aside class="evidence" aria-label="证据栏">
    <section class="card">
      <div class="flex-between">
        <h2 class="card-title" style="margin-bottom: 0">证据与参数</h2>
        <span
          v-if="isSyntheticResult(record?.request.mode, record?.run_id, record?.result_kind)"
          class="pill pill-synthetic"
          title="此历史记录展示的是示例数据，用于预览页面与结果结构"
        >
          示例数据（历史记录）
        </span>
      </div>

      <template v-if="record">
        <h3 class="evidence-section">请求参数</h3>
        <dl class="evidence-list">
          <dt>运行编号</dt>
          <dd class="mono">{{ record.run_id }}</dd>
          <dt>模式</dt>
          <dd>{{ MODE_LABEL[record.request.mode] }}（{{ record.request.mode }}）</dd>
          <dt>来源</dt>
          <dd>{{ runSourceLabel(record.request.mode, record.run_id, record.result_kind) }}</dd>
          <dt>细胞背景</dt>
          <dd>{{ record.request.cell_line }}</dd>
          <dt>扰动</dt>
          <dd>{{ record.request.perturbation }}</dd>
          <dt>n_cells</dt>
          <dd>{{ record.request.n_cells }}</dd>
          <dt>seed</dt>
          <dd>{{ record.request.seed }}</dd>
          <dt>创建时间</dt>
          <dd>{{ fmtServerTime(record.created_at) }}</dd>
          <dt>更新时间</dt>
          <dd>{{ fmtServerTime(record.updated_at) }}</dd>
        </dl>

        <h3 class="evidence-section">模型背景</h3>
        <dl class="evidence-list">
          <dt>注册模型</dt>
          <dd>
            <template v-if="context?.model_id">
              <span class="mono">{{ context.model_id }}</span>
              <span class="muted small">（当前背景注册模型）</span>
            </template>
            <template v-else>未提供</template>
          </dd>
        </dl>
        <p class="muted small" style="margin: 6px 0 0">
          注册模型代表当前配置；本次运行使用的模型与哈希见下方溯源，二者可能不同。
        </p>

        <h3 class="evidence-section">覆盖信息</h3>
        <template v-if="coverage">
          <dl class="evidence-list">
            <dt>对齐基因</dt>
            <dd>{{ fmtPercent(coverage.state_gene_fraction) }}（占参考面板比例）</dd>
            <dt>代谢库基因</dt>
            <dd>{{ fmtPercent(coverage.metabolic_gene_fraction) }}（覆盖率）</dd>
            <dt>反应覆盖</dt>
            <dd>{{ fmtPercent(coverage.reaction_fraction) }}（所需基因平均覆盖）</dd>
            <dt>任务数</dt>
            <dd>
              覆盖支持 {{ coverage.supported_tasks }} / 探索性
              {{ coverage.exploratory_tasks }} / 证据不足 {{ coverage.insufficient_tasks }}
            </dd>
          </dl>
        </template>
        <p v-else class="muted small" style="margin: 4px 0 0">覆盖摘要未提供（任务未完成或无代谢结果）。</p>

        <h3 class="evidence-section">限制与警告</h3>
        <template v-if="record.warnings.length > 0">
          <ul class="warning-list">
            <li v-for="(warning, i) in record.warnings" :key="i">{{ warning }}</li>
          </ul>
        </template>
        <p v-else class="muted small" style="margin: 4px 0 0">本次运行没有返回警告。</p>
        <p v-if="record.error_code" class="small" style="margin: 6px 0 0">
          错误码：<span class="mono">{{ record.error_code }}</span>
        </p>

        <h3 class="evidence-section">溯源</h3>
        <template v-if="provenance.data">
          <dl class="evidence-list">
            <dt>历史模型</dt><dd class="mono">{{ provenance.data.assets.model_id ?? '未记录（合成包或旧运行）' }}</dd>
            <dt>历史数据</dt><dd class="mono">{{ provenance.data.assets.dataset_id ?? '未记录' }}</dd>
            <template v-if="provenance.data.source_run_id">
              <dt>原始真实运行</dt><dd><RouterLink :to="{path:'/workbench',query:{run:provenance.data.source_run_id}}">{{ provenance.data.source_run_id }}</RouterLink></dd>
            </template>
            <dt>完成时间</dt><dd>{{ fmtServerTime(provenance.data.completed_at) }}</dd>
          </dl>
          <details class="hashes">
            <summary>查看运行文件哈希</summary>
            <dl>
              <dt>manifest SHA-256</dt><dd class="mono">{{ provenance.data.manifest_sha256 }}</dd>
              <dt>执行代码 SHA-256</dt><dd class="mono">{{ provenance.data.code_sha256 ?? '未记录' }}</dd>
              <dt v-if="provenance.data.source_manifest_sha256">回放文件清单 SHA-256</dt>
              <dd v-if="provenance.data.source_manifest_sha256" class="mono">{{ provenance.data.source_manifest_sha256 }}</dd>
              <dt v-if="provenance.data.original_manifest_sha256">原真实运行 manifest SHA-256</dt>
              <dd v-if="provenance.data.original_manifest_sha256" class="mono">{{ provenance.data.original_manifest_sha256 }}</dd>
              <template v-for="(value, key) in provenance.data.assets" :key="key">
                <template v-if="String(key).endsWith('_sha256')">
                  <dt>{{ key }}</dt><dd class="mono">{{ value ?? '未记录' }}</dd>
                </template>
              </template>
            </dl>
          </details>
          <p class="muted small">哈希来自本次运行 manifest；展示记录不等于重新核验所有大型文件。</p>
        </template>
        <p v-else-if="provenance.status === 'loading'" class="muted small">正在读取运行溯源…</p>
        <p v-else class="muted small">{{ provenance.error?.status === 404 ? '本次记录未保存可核对的运行来源' : '溯源暂不可用' }}</p>
        <button v-if="provenance.status === 'error' && provenance.error?.status !== 404" class="btn btn-sm" @click="runs.retryBlock(entry.runId, 'provenance')">重试溯源</button>

        <div class="btn-row" style="margin-top: 14px">
          <button class="btn btn-sm" type="button" @click="copyDiagnostics">复制诊断信息</button>
          <button
            class="btn btn-ghost btn-sm"
            type="button"
            :disabled="entry.polling === false && record.status !== 'completed' && record.status !== 'failed'"
            title="重新读取运行记录"
            @click="runs.refreshRecord(entry.runId)"
          >
            刷新状态
          </button>
        </div>
      </template>

      <p v-else class="muted small">运行记录尚未加载。</p>
    </section>
  </aside>
</template>

<style scoped>
.evidence-section {
  font-size: 13px;
  color: var(--muted);
  margin: 16px 0 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.warning-list {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--warn);
}
.hashes { margin-top: 8px; font-size: 12px; }
.hashes dd { margin: 4px 0 10px; overflow-wrap: anywhere; }
</style>
