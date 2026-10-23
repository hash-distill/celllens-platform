<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import SectionNavigation from './components/SectionNavigation.vue'
import UtilityRail from './components/UtilityRail.vue'
import FloatingAssistant from './components/FloatingAssistant.vue'
import { assistantOpen, assistantSource } from './stores/assistantSource'
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
const route = useRoute()

/** 开发数据来源标记（生产构建不启用） */
const mockOn = isMockEnabled()

function onVisibilityChange(): void {
  // 页面恢复可见：立即补一次轮询；隐藏时轮询自动降频（间隔在调度时读取）
  if (document.visibilityState === 'visible') runs.wakePolling()
}

onMounted(() => {
  void service.refresh()
  void catalog.load()
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <AppHeader />
  <div v-if="mockOn" class="mock-banner" role="status">
    示例数据模式 · 当前显示合成示例。
  </div>
  <ConnectionBanner />
  <main :class="{'research-main': route.path !== '/', 'assistant-docked': assistantOpen && assistantSource}">
    <SectionNavigation />
    <RouterView />
  </main>
  <UtilityRail />
  <FloatingAssistant />

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
main.assistant-docked{margin-right:516px;min-width:0}
.assistant-docked :deep(.active-experiment),.assistant-docked :deep(.state-heading),.assistant-docked :deep(.figure-toolbar){flex-wrap:wrap}
.assistant-docked :deep(.state-feature-controls){flex-wrap:wrap}
.assistant-docked :deep(.figure-insight){align-items:flex-start}
.assistant-docked :deep(.active-experiment>div){min-width:0}
.assistant-docked :deep(.page){padding-left:24px;padding-right:20px}
.mock-banner {
  background: var(--mock-banner-bg);
  color: var(--mock-banner-ink);
  border-bottom: 1px solid var(--mock-banner-border);
  padding: 7px 24px;
  font-size: 13px;
  font-weight: 600;
  text-align: center;
}
</style>
