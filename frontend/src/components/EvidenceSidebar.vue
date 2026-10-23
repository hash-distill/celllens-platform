<script setup lang="ts">
import { computed } from 'vue'
import { useRunStore, type RunEntry } from '../stores/run'
import { useUiStore } from '../stores/ui'
import { fmtServerTime, MODE_LABEL } from '../utils/format'
import { buildDiagnostics, copyText } from '../utils/diagnostics'
import { isSyntheticResult, runSourceLabel } from '../utils/source'

/**
 * 固定证据栏：运行编号、实验参数、模型背景、覆盖信息、警告与错误码、
 * 溯源占位与「复制诊断信息」。
 */

const props = defineProps<{ entry: RunEntry }>()

const runs = useRunStore()
const ui = useUiStore()

const record = computed(() => props.entry.record)


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
  <aside class="evidence" aria-label="实验信息">
    <section class="card">
      <div class="flex-between">
        <h2 class="card-title" style="margin-bottom: 0">实验信息</h2>
        <span
          v-if="isSyntheticResult(record?.request.mode, record?.run_id, record?.result_kind)"
          class="pill pill-synthetic"
          title="历史合成数据"
        >
          合成数据（历史记录）
        </span>
      </div>

      <template v-if="record">
        <h3 class="evidence-section">实验参数</h3>
        <dl class="evidence-list">
          <dt>运行编号</dt>
          <dd class="mono">{{ record.run_id }}</dd>
          <dt>模式</dt>
          <dd>{{ MODE_LABEL[record.request.mode] }}</dd>
          <dt>来源</dt>
          <dd>{{ runSourceLabel(record.request.mode, record.run_id, record.result_kind) }}</dd>
          <dt>细胞背景</dt>
          <dd>{{ record.request.cell_line }}</dd>
          <dt>扰动</dt>
          <dd>{{ record.request.perturbation }}</dd>
          <dt>预测细胞数</dt>
          <dd>{{ record.request.n_cells }}</dd>
          <dt>随机种子</dt>
          <dd>{{ record.request.seed }}</dd>
          <dt>创建时间</dt>
          <dd>{{ fmtServerTime(record.created_at) }}</dd>
          <dt>更新时间</dt>
          <dd>{{ fmtServerTime(record.updated_at) }}</dd>
        </dl>

        <RouterLink :to="{path:'/coverage',query:{run:record.run_id}}" class="muted small">查看基因与任务范围 ↗</RouterLink>

        <h3 v-if="record.warnings.length" class="evidence-section">运行提示</h3>
        <template v-if="record.warnings.length > 0">
          <ul class="warning-list">
            <li v-for="(warning, i) in record.warnings" :key="i">{{ warning }}</li>
          </ul>
        </template>

        <p v-if="record.error_code" class="small" style="margin: 6px 0 0">
          错误码：<span class="mono">{{ record.error_code }}</span>
        </p>

        <h3 class="evidence-section">模型与数据来源</h3>
        <template v-if="provenance.data">
          <dl class="evidence-list">
            <dt>使用模型</dt><dd class="mono">{{ provenance.data.assets.model_id ?? '暂无信息' }}</dd>
            <dt>对照数据</dt><dd class="mono">{{ provenance.data.assets.dataset_id ?? '未记录' }}</dd>
            <template v-if="provenance.data.source_run_id">
              <dt>原始实验</dt><dd><RouterLink :to="{path:'/demo',query:{run:provenance.data.source_run_id}}">{{ provenance.data.source_run_id }}</RouterLink></dd>
            </template>
            <dt>完成时间</dt><dd>{{ fmtServerTime(provenance.data.completed_at) }}</dd>
          </dl>

        </template>
        <p v-else-if="provenance.status === 'loading'" class="muted small">正在读取数据来源…</p>
        <p v-else class="muted small">{{ provenance.error?.status === 404 ? '暂无数据来源信息' : '数据来源暂不可用' }}</p>
        <button v-if="provenance.status === 'error' && provenance.error?.status !== 404" class="btn btn-sm" @click="runs.retryBlock(entry.runId, 'provenance')">重新加载来源</button>

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
