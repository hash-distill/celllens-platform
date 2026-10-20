<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FunctionWorkspace from './FunctionWorkspace.vue'
import MetabolismTab from '../tabs/MetabolismTab.vue'
defineProps<{ runId: string }>()
const route = useRoute(), router = useRouter()
const dataView = computed(() => route.query.view === 'data')
function select(view: 'function'|'data') { void router.replace({path:route.path,query:{...route.query,tab:'metabolism',view}}) }
</script>
<template>
  <section aria-label="代谢功能工作区">
    <div class="metabolism-views" aria-label="代谢功能视图">
      <button class="btn btn-sm" :aria-pressed="!dataView" @click="select('function')">功能前后对比</button>
      <button class="btn btn-sm" :aria-pressed="dataView" @click="select('data')">任务与反应分数</button>
    </div>
    <div v-if="dataView" class="card"><MetabolismTab :run-id="runId" /></div>
    <FunctionWorkspace v-else :run-id="runId" />
  </section>
</template>
<style scoped>
.metabolism-views{display:flex;gap:8px;flex-wrap:wrap}.metabolism-views button[aria-pressed=true]{background:var(--primary);color:var(--on-primary);border-color:var(--primary)}
</style>
