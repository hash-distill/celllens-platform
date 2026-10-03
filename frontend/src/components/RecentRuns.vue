<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useRecentStore } from '../stores/recent'
import { MODE_LABEL, shortRunId } from '../utils/format'

/**
 * 最近运行：只记录本浏览器创建或打开过的任务（本浏览器记录）。
 * 另提供「输入运行编号打开」入口。
 */
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })

const router = useRouter()
const recent = useRecentStore()
const manualId = ref('')

function open(runId: string): void {
  const id = runId.trim()
  if (!id) return
  manualId.value = ''
  void router.push({ path: `/runs/${encodeURIComponent(id)}`, query: { tab: 'cell' } })
}
</script>

<template>
  <section class="recent" aria-label="最近运行">
    <div class="flex-between">
      <h3 class="recent-title">最近运行</h3>
      <span class="pill pill-neutral">本浏览器记录</span>
    </div>
    <p v-if="!compact" class="muted small recent-desc">
      仅记录本浏览器创建或打开过的任务，不代表服务器全部历史。
    </p>

    <form class="manual-open" @submit.prevent="open(manualId)">
      <label class="sr-only" for="manual-run-id">输入运行编号打开</label>
      <input
        id="manual-run-id"
        v-model="manualId"
        class="input"
        type="text"
        placeholder="输入运行编号打开，如 run_…"
        autocomplete="off"
      />
      <button class="btn btn-sm" type="submit" :disabled="!manualId.trim()">打开</button>
    </form>

    <p v-if="recent.items.length === 0" class="muted small">暂无记录。提交实验或输入运行编号后出现在这里。</p>

    <ul v-else class="recent-list" :class="{ compact }">
      <li v-for="item in recent.items" :key="item.run_id" class="recent-item">
        <button class="recent-main" type="button" @click="open(item.run_id)">
          <span class="mono recent-id" :title="item.run_id">{{ shortRunId(item.run_id) }}</span>
          <span class="recent-meta">
            {{ item.cell_line }} / {{ item.perturbation }} / {{ MODE_LABEL[item.mode] }}
            <template v-if="item.status === 'completed'"> · 已完成</template>
            <template v-else-if="item.status === 'failed'"> · 失败</template>
          </span>
        </button>
        <button
          class="recent-remove"
          type="button"
          :aria-label="`移除记录 ${item.run_id}`"
          title="从本机记录移除（不影响服务器任务）"
          @click="recent.remove(item.run_id)"
        >
          ×
        </button>
      </li>
    </ul>
    <button
      v-if="recent.items.length > 0"
      class="btn btn-ghost btn-sm"
      type="button"
      @click="recent.clear()"
    >
      清空本机记录
    </button>
  </section>
</template>

<style scoped>
.recent {
  margin-top: 20px;
}
.recent-title {
  font-size: 14px;
}
.recent-desc {
  margin: 6px 0 0;
}
.manual-open {
  display: flex;
  gap: 8px;
  margin: 10px 0;
}
.manual-open .input {
  flex: 1;
}
.recent-list {
  list-style: none;
  margin: 8px 0 4px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.recent-item {
  display: flex;
  align-items: stretch;
  gap: 4px;
}
.recent-main {
  flex: 1;
  min-width: 0;
  text-align: left;
  appearance: none;
  border: 1px solid var(--border);
  background: #fff;
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  cursor: pointer;
  font-family: var(--font);
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.recent-main:hover {
  border-color: var(--primary);
  background: var(--primary-weak);
}
.recent-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}
.recent-meta {
  font-size: 12px;
  color: var(--muted);
}
.recent-remove {
  appearance: none;
  border: 1px solid transparent;
  background: transparent;
  color: var(--faint);
  border-radius: var(--radius-sm);
  cursor: pointer;
  padding: 0 8px;
  font-size: 15px;
}
.recent-remove:hover {
  color: var(--danger);
  background: var(--danger-bg);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>
