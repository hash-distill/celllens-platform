<script setup lang="ts">
import { useServiceStore } from '../stores/service'
import { useCatalogStore } from '../stores/catalog'

const service = useServiceStore()
const catalog = useCatalogStore()

async function reconnect(): Promise<void> {
  await service.refresh()
  if (!service.networkDown) await catalog.load()
}
</script>

<template>
  <div v-if="service.networkDown" class="connection-banner" role="alert">
    <span>后端连接异常：已保留当前页面已有结果，任务状态不会被改写。恢复后可继续操作。</span>
    <button class="btn btn-sm" :disabled="service.checking" @click="reconnect">
      {{ service.checking ? '重连中…' : '重新连接' }}
    </button>
  </div>
</template>

<style scoped>
.connection-banner {
  background: var(--danger-bg);
  color: var(--danger);
  border-bottom: 1px solid #fecaca;
  padding: 8px 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  font-size: 13px;
  flex-wrap: wrap;
}
</style>
