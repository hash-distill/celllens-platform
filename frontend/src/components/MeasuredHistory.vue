<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { measuredApi } from '../api/measured'
import { fmtServerTime } from '../utils/format'
import type { MeasuredAnalysis, MeasuredPage, MeasuredStatus } from '../types/measured'
const data = ref<MeasuredPage<MeasuredAnalysis> | null>(null), page = ref(1), loading = ref(false), error = ref('')
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / 10)))
const labels: Record<MeasuredStatus,string> = {queued:'等待分析',preparing:'准备数据',analysing:'分析中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'}
let controller: AbortController | undefined
async function refresh() {
  controller?.abort(); const current = controller = new AbortController(); loading.value = true; error.value = ''
  try { const result = await measuredApi.list(10, (page.value - 1) * 10, current.signal); if (!current.signal.aborted) data.value = result }
  catch (reason) { if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '记录读取失败' }
  finally { if (!current.signal.aborted) loading.value = false }
}
watch(page, refresh, {immediate:true})
onBeforeUnmount(() => controller?.abort())
defineExpose({refresh})
</script>
<template>
  <section class="card measured-history" aria-label="实测分析记录"><header><h2>实测分析记录</h2><button class="btn btn-sm" :disabled="loading" @click="refresh">刷新记录</button></header>
    <p v-if="loading" role="status">正在读取记录…</p><p v-else-if="error" role="alert">{{ error }}</p><p v-else-if="!data?.items.length">暂无实测分析记录。</p>
    <div v-else class="history-list"><RouterLink v-for="record in data.items" :key="record.id" :to="`/measured/${record.id}`"><strong>{{ record.cell_line }} / {{ record.perturbation }}</strong><span>实测数据 · {{ labels[record.status] }}</span><small>{{ fmtServerTime(record.created_at) }}</small><span>{{ record.status === 'completed' ? '结果解读 →' : '查看状态 →' }}</span></RouterLink></div>
    <footer v-if="data?.total"><span>共 {{ data.total }} 条 · {{ page }} / {{ pages }}</span><button class="btn btn-sm" :disabled="page <= 1 || loading" @click="page--">上一页</button><button class="btn btn-sm" :disabled="page >= pages || loading" @click="page++">下一页</button></footer>
  </section>
</template>
<style scoped>
header,footer{display:flex;align-items:center;gap:16px;justify-content:space-between}h2{font-size:18px;font-weight:500}.history-list a{display:grid;grid-template-columns:1fr 1fr 1fr auto;gap:16px;align-items:center;padding:20px 0;border-top:1px solid var(--border);color:var(--ink);text-decoration:none;font-size:12px}.history-list a:hover{color:var(--primary)}small,footer{font-size:11px;color:var(--muted)}footer{justify-content:flex-end;margin-top:16px}footer>span{margin-right:auto}@media(max-width:700px){.history-list a{grid-template-columns:1fr 1fr}}
</style>
