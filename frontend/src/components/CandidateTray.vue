<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useCandidatesStore } from '../stores/candidates'
import { MODE_LABEL, shortRunId } from '../utils/format'

/**
 * 底部候选托盘：以 run_id 去重、最多 4 个，本机存储（本浏览器记录）。
 */
const router = useRouter()
const candidates = useCandidatesStore()
</script>

<template>
  <div class="tray" :class="{ collapsed: !candidates.expanded }" role="region" aria-label="候选托盘">
    <div class="tray-bar">
      <button
        class="tray-toggle"
        type="button"
        :aria-expanded="candidates.expanded"
        @click="candidates.toggleExpanded()"
      >
        <span aria-hidden="true">{{ candidates.expanded ? '▾' : '▴' }}</span>
        已选候选 {{ candidates.items.length }} / 4
      </button>
      <span class="pill pill-neutral">本浏览器记录</span>
      <span class="tray-spacer"></span>
      <button
        class="btn btn-sm"
        type="button"
        :disabled="candidates.items.length === 0"
        title="并排查看候选运行的描述性比较"
        @click="router.push('/compare')"
      >
        查看比较
      </button>
      <button
        class="btn btn-ghost btn-sm"
        type="button"
        :disabled="candidates.items.length === 0"
        @click="candidates.clear()"
      >
        清空
      </button>
    </div>
    <div v-if="candidates.expanded" class="tray-body">
      <p v-if="candidates.items.length === 0" class="muted small" style="margin: 0">
        还没有候选。打开运行详情后可「加入候选」，最多 4 个，以 run_id 去重；仅保存在本浏览器。
      </p>
      <ul v-else class="tray-chips">
        <li v-for="item in candidates.items" :key="item.run_id" class="tray-chip">
          <button
            class="chip-main"
            type="button"
            :title="`打开运行 ${item.run_id}`"
            @click="router.push({ path: `/runs/${encodeURIComponent(item.run_id)}`, query: { tab: 'cell' } })"
          >
            <span class="mono chip-id">{{ shortRunId(item.run_id) }}</span>
            <span class="chip-meta">
              {{ item.request.cell_line }} / {{ item.request.perturbation }} /
              {{ MODE_LABEL[item.request.mode] }}
            </span>
            <span v-if="item.request.mode === 'precomputed'" class="pill pill-synthetic">合成演示</span>
          </button>
          <button
            class="chip-remove"
            type="button"
            :aria-label="`移除候选 ${item.run_id}`"
            title="从候选托盘移除（本机操作，不影响服务器任务）"
            @click="candidates.remove(item.run_id)"
          >
            ×
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.tray {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 45;
  background: #ffffff;
  border-top: 1px solid var(--border);
  box-shadow: 0 -2px 10px rgba(15, 23, 42, 0.05);
}
.tray-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  padding: 0 20px;
  max-width: 1680px;
  margin: 0 auto;
}
.tray-toggle {
  appearance: none;
  border: none;
  background: none;
  font-family: var(--font);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  cursor: pointer;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  padding: 4px 6px;
}
.tray-spacer {
  flex: 1;
}
.tray-body {
  padding: 4px 20px 12px;
  max-width: 1680px;
  margin: 0 auto;
  max-height: 130px;
  overflow-y: auto;
}
.tray-chips {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 0;
}
.tray-chip {
  display: inline-flex;
  align-items: stretch;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
  background: #fff;
}
.chip-main {
  appearance: none;
  border: none;
  background: none;
  font-family: var(--font);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  cursor: pointer;
  font-size: 12px;
}
.chip-main:hover {
  background: var(--primary-weak);
}
.chip-id {
  font-weight: 600;
  color: var(--ink);
}
.chip-meta {
  color: var(--muted);
}
.chip-remove {
  appearance: none;
  border: none;
  border-left: 1px solid var(--border);
  background: none;
  color: var(--faint);
  cursor: pointer;
  padding: 0 8px;
  font-size: 14px;
}
.chip-remove:hover {
  color: var(--danger);
  background: var(--danger-bg);
}
</style>
