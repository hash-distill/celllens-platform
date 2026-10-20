<script lang="ts">
/** 结果块五态：加载 / 正常 / 无数据 / 不可用 / 请求失败 */
export type BlockDisplay = 'loading' | 'ok' | 'empty' | 'unavailable' | 'error'
</script>

<script setup lang="ts">
import { computed } from 'vue'
import { ApiError } from '../api/http'

/**
 * 结果块五态包装。
 * 局部失败不清空整页，错误块保留局部重试入口。
 */

const props = withDefaults(
  defineProps<{
    display: BlockDisplay
    error?: ApiError | null
    loadingText?: string
    emptyText?: string
    emptyHint?: string
    unavailableText?: string
    unavailableHint?: string
    /** 骨架屏行数 */
    skeletonRows?: number
  }>(),
  {
    error: null,
    loadingText: '正在加载…',
    emptyText: '无数据',
    emptyHint: '',
    unavailableText: '本次结果未提供',
    unavailableHint: '',
    skeletonRows: 4,
  },
)

const emit = defineEmits<{ retry: [] }>()

const rows = computed(() => Array.from({ length: props.skeletonRows }, (_, i) => i))
</script>

<template>
  <div class="block-state">
    <template v-if="display === 'loading'">
      <div class="skeleton-wrap" role="status" :aria-label="loadingText">
        <div v-for="row in rows" :key="row" class="skeleton skeleton-line"></div>
        <p class="muted small">{{ loadingText }}</p>
      </div>
    </template>

    <template v-else-if="display === 'ok'">
      <slot></slot>
    </template>

    <template v-else-if="display === 'empty'">
      <div class="state-box" role="status">
        <p class="state-title">{{ emptyText }}</p>
        <p v-if="emptyHint" class="muted small">{{ emptyHint }}</p>
        <slot name="empty-extra"></slot>
      </div>
    </template>

    <template v-else-if="display === 'unavailable'">
      <div class="state-box state-unavailable" role="status">
        <p class="state-title">{{ unavailableText }}</p>
        <p v-if="unavailableHint" class="muted small">{{ unavailableHint }}</p>
        <div v-if="error" class="muted small mono">
          {{ error.status ? `HTTP ${error.status}` : '' }}
          {{ error.code ? ` · ${error.code}` : '' }}
        </div>
        <button v-if="error" class="btn btn-sm state-retry" @click="emit('retry')">重试</button>
      </div>
    </template>

    <template v-else>
      <div class="state-box state-error" role="alert">
        <p class="state-title">请求失败</p>
        <p class="small">{{ error?.message ?? '未知错误' }}</p>
        <p v-if="error?.code" class="muted small mono">错误码：{{ error.code }}</p>
        <button class="btn btn-sm state-retry" @click="emit('retry')">重新加载</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.skeleton-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0;
}
.skeleton-line {
  height: 18px;
}
.skeleton-line:first-child {
  width: 60%;
}
.state-box {
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 22px 18px;
  text-align: center;
  color: var(--muted);
  background: var(--coverage-bg);
}
.state-title {
  margin: 0 0 4px;
  font-weight: 600;
  color: var(--ink);
}
.state-unavailable {
  border-color: var(--warn-border);
  background: var(--warn-bg);
}
.state-unavailable .state-title {
  color: var(--warn);
}
.state-error {
  border-color: var(--danger-border);
  background: var(--danger-bg);
}
.state-error .state-title {
  color: var(--danger);
}
.state-retry {
  margin-top: 10px;
}
</style>
