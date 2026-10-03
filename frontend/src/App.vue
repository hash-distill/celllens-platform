<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import AppHeader from './components/AppHeader.vue'
import ConnectionBanner from './components/ConnectionBanner.vue'
import { isMockEnabled } from './api/mockFlag'
import { useServiceStore } from './stores/service'
import { useCatalogStore } from './stores/catalog'
import { useRunStore } from './stores/run'
import { useUiStore } from './stores/ui'

const service = useServiceStore()
const catalog = useCatalogStore()
const runs = useRunStore()
const ui = useUiStore()

/** Mock 样例数据常驻标记（仅显式开关开启时出现） */
const mockOn = isMockEnabled()

let healthTimer: number | null = null

function onVisibilityChange(): void {
  // 页面恢复可见：立即补一次轮询；隐藏时轮询自动降频（间隔在调度时读取）
  if (document.visibilityState === 'visible') runs.wakePolling()
}

onMounted(() => {
  void service.refresh()
  void catalog.load()
  healthTimer = window.setInterval(() => void service.refresh(), 30000)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  if (healthTimer !== null) window.clearInterval(healthTimer)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <AppHeader />
  <div v-if="mockOn" class="mock-banner" role="status">
    Mock 样例数据 · 当前为演示 / 调试模式，全部接口返回固定种子的合成样例，不是真实计算结果。
    可在「使用说明 → Mock 演示模式」关闭。
  </div>
  <ConnectionBanner />
  <main>
    <RouterView />
  </main>

  <!-- 轻量提示 -->
  <div class="toast-stack" aria-live="polite">
    <div
      v-for="toast in ui.toasts"
      :key="toast.id"
      class="toast"
      :class="{
        'notice-ok': toast.kind === 'success',
        'notice-warn': toast.kind === 'warning',
        'notice-danger': toast.kind === 'error',
        'notice-info': toast.kind === 'info',
      }"
    >
      <span style="flex: 1">{{ toast.text }}</span>
      <button class="toast-close" type="button" :aria-label="'关闭提示'" @click="ui.dismiss(toast.id)">×</button>
    </div>
  </div>
</template>

<style scoped>
.mock-banner {
  background: #fef3c7;
  color: #92400e;
  border-bottom: 1px solid #fde68a;
  padding: 7px 24px;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
}
</style>
