<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import WorkbenchView from './WorkbenchView.vue'
const route = useRoute()
const bound = computed(() => typeof route.query.run === 'string' && Boolean(route.query.run))
</script>
<template>
  <WorkbenchView v-if="bound" results-only />
  <div v-else class="page">
    <section class="card result-selection">
      <span class="eyebrow">SELECT AN EXPERIMENT</span>
      <h1>选择一个实验，查看分析结果。</h1>
      <p>在线推演可从实验记录直接打开，查看本次实验的状态、表达与代谢结果。</p>
      <RouterLink to="/records" class="btn btn-primary">选择实验</RouterLink>
    </section>
  </div>
</template>
<style scoped>
.result-selection{padding:48px}.result-selection h1{font-size:26px;font-weight:500;margin:18px 0}.result-selection p{color:var(--muted);font-size:13px;line-height:1.9;margin:0 0 24px}@media(max-width:600px){.result-selection{padding:24px}.result-selection h1{font-size:21px}}
</style>
