<script setup lang="ts">
import { computed } from 'vue'
import type { RunRecord, RunStatus } from '../types/run'
import { STATUS_LABEL } from '../utils/format'

/**
 * 阶段进度条：只显示后端 stage_progress 阶段值，
 * 不使用计时器伪造平滑增长的百分比。
 */

const props = defineProps<{
  record: RunRecord
  /** 轮询中的临时问题说明（网络重试等），不改变运行状态 */
  pollIssue?: string | null
}>()

const STAGE_ORDER: RunStatus[] = [
  'queued',
  'state_running',
  'adapting',
  'metabolic_running',
  'validating',
  'completed',
]

const STAGE_HINT: Partial<Record<RunStatus, string>> = {
  queued: '没有队列位置信息，不显示虚构排位或剩余时间',
  state_running: '仅显示后端返回的阶段进度',
  adapting: '该阶段可能很快，不要求每步都被轮询捕获',
  metabolic_running: '可能产出转录结果及代谢降级警告',
  validating: '正在核对来源、计算 PCA / UMAP 并保存默认科研图；图形准备完成后才显示分析完成，不代表实测验证通过',
}

const currentIndex = computed(() => {
  if (props.record.status === 'failed') return -1
  return STAGE_ORDER.indexOf(props.record.status)
})

const statusText = computed(() => {
  const base = STATUS_LABEL[props.record.status]
  if (props.record.status === 'completed' && props.record.warnings.length > 0) {
    return `${base}（含限制说明）`
  }
  return base
})

const fillClass = computed(() => {
  if (props.record.status === 'failed') return 'failed'
  if (props.record.status === 'completed') return 'done'
  return ''
})
</script>

<template>
  <section class="card" aria-label="运行阶段">
    <div class="flex-between">
      <h2 class="card-title" style="margin-bottom: 0">阶段进度</h2>
      <span
        class="pill"
        :class="{
          'pill-danger': record.status === 'failed',
          'pill-ok': record.status === 'completed' && record.warnings.length === 0,
          'pill-warn': record.status === 'completed' && record.warnings.length > 0,
          'pill-info':
            record.status !== 'completed' && record.status !== 'failed',
        }"
      >
        {{ statusText }}
      </span>
    </div>

    <div class="progress-row">
      <div
        class="progress-track"
        role="progressbar"
        :aria-valuenow="record.stage_progress"
        aria-valuemin="0"
        aria-valuemax="100"
        :aria-label="`阶段进度 ${record.stage_progress}%`"
      >
        <div
          class="progress-fill"
          :class="fillClass"
          :style="{ width: `${record.stage_progress}%` }"
        ></div>
      </div>
      <span class="progress-value mono">{{ record.stage_progress }}%</span>
    </div>

    <ol class="stage-steps" aria-label="阶段列表">
      <li
        v-for="(stage, index) in STAGE_ORDER"
        :key="stage"
        class="stage-step"
        :class="{
          active: index === currentIndex,
          passed: currentIndex > index,
          failed: record.status === 'failed' && index === Math.max(0, STAGE_ORDER.length - 2),
        }"
      >
        <span class="stage-dot" aria-hidden="true"></span>
        <span class="stage-name">{{ STATUS_LABEL[stage] }}</span>
      </li>
    </ol>
    <p v-if="STAGE_HINT[record.status]" class="muted small" style="margin: 8px 0 0">
      {{ STAGE_HINT[record.status] }}
    </p>

    <div v-if="pollIssue" class="notice notice-warn" style="margin-top: 10px">{{ pollIssue }}</div>

    <div v-if="record.status === 'failed'" class="notice notice-danger" style="margin-top: 10px">
      <strong>分析失败</strong>
      <p style="margin: 4px 0 0">
        错误码：<span class="mono">{{ record.error_code ?? '未提供' }}</span>
      </p>
      <p style="margin: 2px 0 0">{{ record.error_message ?? '服务端未返回详细错误信息' }}</p>
      <p class="small" style="margin: 6px 0 0">
        失败记录已保留，可携带运行编号与诊断信息反馈；「重新提交」会以相同参数再次创建任务。
      </p>
    </div>

    <div
      v-else-if="record.warnings.length > 0"
      class="notice notice-warn"
      style="margin-top: 10px"
    >
      <strong>限制与警告（{{ record.warnings.length }}）：</strong>
      <ul class="warning-list">
        <li v-for="(warning, i) in record.warnings" :key="i">{{ warning }}</li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.progress-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}
.progress-track {
  flex: 1;
}
.progress-value {
  color: var(--muted);
  font-size: 13px;
  min-width: 42px;
  text-align: right;
}
.stage-steps {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 14px 0 0;
  padding: 0;
}
.stage-step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--faint);
}
.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-strong);
}
.stage-step.passed {
  color: var(--muted);
}
.stage-step.passed .stage-dot {
  background: var(--ok);
}
.stage-step.active {
  color: var(--primary);
  font-weight: 600;
}
.stage-step.active .stage-dot {
  background: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-weak);
}
.warning-list {
  margin: 6px 0 0;
  padding-left: 18px;
}
</style>
