<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { useServiceStore } from '../stores/service'

const route = useRoute()
const service = useServiceStore()

const dotColor = computed(() => {
  switch (service.level) {
    case 'ok':
      return '#047857'
    case 'degraded':
      return '#b45309'
    case 'down':
      return '#dc2626'
    default:
      return '#94a3b8'
  }
})

const statusTitle = computed(() => {
  const parts = [`服务状态：${service.levelLabel}`]
  if (service.checks) {
    parts.push(
      `数据库 ${service.checks.database ? '正常' : '异常'} / Worker ${service.checks.worker ? '正常' : '异常'} / GPU ${service.checks.gpu ? '可用' : '不可用'}`,
    )
  }
  if (service.lastCheckedAt) parts.push(`检查时间：${new Date(service.lastCheckedAt).toLocaleTimeString()}`)
  parts.push('点击查看服务状态详情')
  return parts.join('；')
})

function isActive(path: string): boolean {
  if (path === '/workbench') return route.path === '/workbench' || route.path.startsWith('/runs/')
  return route.path.startsWith(path)
}
</script>

<template>
  <header class="app-header">
    <div class="header-inner">
      <RouterLink to="/workbench" class="brand">
        <img class="brand-mark" src="/favicon.png" width="32" height="32" alt="" aria-hidden="true" />
        <span class="brand-name">细胞知镜</span>
        <span class="brand-sub">CellLens</span>
      </RouterLink>
      <nav class="header-nav" aria-label="主导航">
        <RouterLink to="/workbench" class="nav-link" :class="{ active: isActive('/workbench') }">
          工作台
        </RouterLink>
        <RouterLink to="/compare" class="nav-link" :class="{ active: isActive('/compare') }">
          候选比较
        </RouterLink>
        <RouterLink to="/about" class="nav-link" :class="{ active: isActive('/about') }">
          使用说明
        </RouterLink>
      </nav>
      <RouterLink
        to="/about"
        class="service-indicator"
        :title="statusTitle"
        :aria-label="`服务状态：${service.levelLabel}`"
      >
        <span class="dot" :style="{ background: dotColor }" aria-hidden="true"></span>
        <span class="service-text">{{ service.levelLabel }}</span>
      </RouterLink>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: 56px;
  background: #ffffff;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 50;
}
.header-inner {
  height: 56px;
  max-width: 1680px;
  margin: 0 auto;
  padding: 0 24px;
  display: flex;
  align-items: center;
  gap: 28px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  text-decoration: none;
}
.brand:hover {
  text-decoration: none;
}
.brand-mark {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  object-fit: contain;
  display: block;
}
.brand-name {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.brand-sub {
  color: var(--faint);
  font-size: 12px;
  font-weight: 500;
}
.header-nav {
  display: flex;
  gap: 4px;
  flex: 1;
}
.nav-link {
  color: var(--muted);
  padding: 6px 12px;
  border-radius: 8px;
  font-size: 14px;
  text-decoration: none;
}
.nav-link:hover {
  color: var(--ink);
  background: #f1f5f9;
  text-decoration: none;
}
.nav-link.active {
  color: var(--primary);
  background: var(--primary-weak);
  font-weight: 600;
}
.service-indicator {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--muted);
  font-size: 13px;
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  text-decoration: none;
  white-space: nowrap;
}
.service-indicator:hover {
  text-decoration: none;
  border-color: var(--border-strong);
}
@media (max-width: 700px) {
  .brand-sub,
  .service-text {
    display: none;
  }
  .header-inner {
    gap: 12px;
    padding: 0 14px;
  }
}
</style>
