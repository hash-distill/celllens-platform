<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { resourcesApi, type ResourceCatalog, type ResourceCell, type ResourceJob } from '../api/resources'
import { useCatalogStore } from '../stores/catalog'
import { useServiceStore } from '../stores/service'
import { useDraftStore } from '../stores/draft'

const catalog = useCatalogStore(), service = useServiceStore()
const draft = useDraftStore()
const data = ref<ResourceCatalog|null>(null), loading = ref(false), error = ref('')
const accepted = reactive<Partial<Record<ResourceCell,boolean>>>({})
const acting = ref<ResourceCell|null>(null)
const stateLabels: Record<ResourceJob['status'],string> = {idle:'尚未准备',queued:'等待准备',downloading:'正在下载',verifying:'正在核验',preparing_control:'正在准备对照',completed:'准备完成',cancelled:'已取消',interrupted:'上次准备中断',failed:'准备失败'}
const active = (job: ResourceJob) => ['queued','downloading','verifying','preparing_control'].includes(job.status)
const bytes = (value: number) => `${(value/1024**2).toFixed(1)} MiB`
const progress = (job: ResourceJob) => job.total_bytes ? Math.min(100,Math.max(0,(job.downloaded_bytes ?? 0)/job.total_bytes*100)) : 0
let controller: AbortController|undefined, timer: ReturnType<typeof setTimeout>|undefined, alive = true
async function load() {
  if (loading.value) return
  clearTimeout(timer); controller?.abort(); const current = controller = new AbortController()
  loading.value = true; error.value = ''
  try {
    const value = await resourcesApi.list(current.signal)
    if (current.signal.aborted) return
    data.value = value
    if (!value.active_cell) {void catalog.load(); void service.refresh()}
    if ((value.active_cell || value.items.some(pack=>active(pack.job))) && alive) timer = setTimeout(load,document.visibilityState === 'hidden' ? 5000 : 1500)
  } catch(reason) {if (!current.signal.aborted) error.value = reason instanceof Error ? reason.message : '资源状态读取失败'}
  finally {if (!current.signal.aborted) loading.value = false}
}
async function start(cell: ResourceCell) {
  if (!accepted[cell] || acting.value || loading.value || data.value?.active_cell) return
  acting.value=cell;error.value=''
  try {await resourcesApi.start(cell); await load()}
  catch(reason) {error.value=reason instanceof Error ? reason.message : '资源准备启动失败'}
  finally {acting.value=null}
}
async function cancel(cell: ResourceCell) {
  if (acting.value) return
  acting.value=cell;error.value=''
  try {await resourcesApi.cancel(cell); await load()}
  catch(reason) {error.value=reason instanceof Error ? reason.message : '取消失败'}
  finally {acting.value=null}
}
onMounted(load)
onBeforeUnmount(() => {alive=false;clearTimeout(timer);controller?.abort()})
</script>
<template>
  <section id="inference-resources" class="inference-resources" aria-label="推理资源管理">
    <header class="resource-heading"><div><span class="eyebrow">INFERENCE RESOURCES</span><h2>按需准备细胞背景</h2><p>只下载需要的背景。已有有效文件会复用，共享代谢库随源码提供。</p></div><button type="button" class="btn btn-sm" :disabled="loading" @click="load">{{ loading ? '检查资源…' : '刷新资源状态' }}</button></header>
    <p class="location-note">资源保存在运行 CellLens 的电脑或服务器上。权重下载校验后，如缺少对照，将从固定官方数据版本提取该背景的真实对照细胞。</p>
    <p v-if="error" class="notice notice-danger" role="alert">{{ error }}<button class="btn btn-sm" @click="load">重试读取</button></p>
    <p v-if="loading && !data" class="muted" role="status">正在检查本机权重与对照数据…</p>
    <div v-if="data" class="resource-grid">
      <article v-for="pack in data.items" :key="pack.cell_line" class="resource-card" :data-cell="pack.cell_line">
        <header><h3>{{ pack.cell_line }}</h3><span class="pill" :class="pack.ready ? 'pill-ok' : 'pill-neutral'">{{ pack.ready ? '资源已就绪' : '待准备' }}</span></header>
        <dl><dt>模型与配套文件</dt><dd>{{ bytes(pack.size_bytes) }} · {{ pack.files.filter(file=>file.status==='verified').length }} / {{ pack.files.length }} 已核验</dd><dt>真实对照数据</dt><dd>{{ pack.control_ready ? '已核验' : '需要提取' }}</dd><dt>本次需下载</dt><dd>{{ bytes(pack.remaining_bytes) }}<small v-if="!pack.control_ready">，另需范围读取对照</small></dd></dl>
        <template v-if="active(pack.job)"><div class="download-progress" role="status"><strong>{{ stateLabels[pack.job.status] }}</strong><span v-if="pack.job.status !== 'preparing_control'">{{ progress(pack.job).toFixed(0) }}%</span></div><progress v-if="pack.job.status !== 'preparing_control'" :value="progress(pack.job)" max="100" :aria-label="`${pack.cell_line} 下载进度`" /><p class="job-message">{{ pack.job.message }}<template v-if="pack.job.current_file"> · {{ pack.job.current_file }}</template></p><button class="btn btn-sm" type="button" :disabled="acting===pack.cell_line || data.can_cancel===false" @click="cancel(pack.cell_line)">取消准备</button></template>
        <template v-else><p v-if="pack.job.status !== 'idle'" class="job-message" :class="{'job-error':pack.job.status==='failed'}" :role="pack.job.status==='failed' ? 'alert' : undefined">{{ pack.job.message }}</p><label class="license-check"><input v-model="accepted[pack.cell_line]" type="checkbox" :aria-label="`确认 ${pack.cell_line} 资源许可`" /><span>已阅读 <a :href="pack.source_url" target="_blank" rel="noopener noreferrer">官方来源与非商业许可</a></span></label><div class="resource-actions"><button type="button" class="btn" :class="{'btn-primary':!pack.ready}" :disabled="loading || !accepted[pack.cell_line] || !!data.active_cell || !!acting" @click="start(pack.cell_line)">{{ acting===pack.cell_line ? '正在提交…' : pack.ready ? '核验已有资源' : ['cancelled','interrupted','failed'].includes(pack.job.status) ? '重试准备' : '下载并准备' }}</button><RouterLink v-if="pack.ready && catalog.contextFor(pack.cell_line)?.online_ready" to="/workbench" class="resource-workbench" @click="draft.setCellLine(pack.cell_line)">前往工作台 →</RouterLink></div></template>
        <details><summary>资源文件与来源</summary><ul><li v-for="file in pack.files" :key="file.name"><span>{{ file.name }}</span><small>{{ file.status==='verified' ? '已校验' : file.status==='invalid' ? '校验未通过' : '未下载' }}</small></li></ul><p>{{ pack.license }}</p><a :href="pack.source_url" target="_blank" rel="noopener noreferrer">查看固定官方版本 ↗</a></details>
      </article>
    </div>
    <p class="resource-boundary">资源就绪后，还需启用分析服务并安装兼容的推理依赖与 GPU 驱动。这里准备的是在线推理输入；不自动下载全部训练数据，也不把对照准备视为模型准确性验证。</p>
  </section>
</template>
<style scoped>
.inference-resources{margin:28px 0;scroll-margin-top:96px}.resource-heading{display:flex;justify-content:space-between;gap:28px;align-items:center}.resource-heading h2{font-size:23px;font-weight:500;margin:9px 0}.resource-heading p,.location-note,.resource-boundary{font-size:12px;color:var(--muted);line-height:1.9}.location-note{border-left:2px solid var(--primary);padding-left:14px;margin:20px 0}.resource-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.resource-card{background:var(--card);border:1px solid var(--border);padding:23px;min-width:0}.resource-card>header{display:flex;justify-content:space-between;gap:12px;align-items:center}.resource-card h3{font:500 23px var(--font);margin:0}.resource-card dl{display:grid;grid-template-columns:145px minmax(0,1fr);gap:12px;font-size:12px;margin:24px 0;line-height:1.8}.resource-card dt{color:var(--muted)}.resource-card dd{margin:0;font-variant-numeric:tabular-nums}.resource-card dd small{display:block;color:var(--muted);font-size:10px}.license-check{display:flex;align-items:center;gap:9px;font-size:11px;line-height:1.8;margin:20px 0 14px}.license-check input{accent-color:var(--primary);width:15px;height:15px;flex:none}.resource-actions{display:flex;gap:14px;align-items:center;flex-wrap:wrap}.resource-workbench{font-size:12px}.resource-card details{margin-top:24px;padding-top:16px;border-top:1px solid var(--border);font-size:11px}.resource-card summary{cursor:pointer;color:var(--muted)}.resource-card details ul{list-style:none;padding:0;margin:16px 0}.resource-card li{display:flex;gap:12px;justify-content:space-between;padding:6px 0;font-size:10px;overflow-wrap:anywhere}.resource-card li small{color:var(--muted);flex:none}.resource-card details p{font-size:10px;color:var(--muted);line-height:1.8}.download-progress{display:flex;justify-content:space-between;font-size:12px;color:var(--primary)}.resource-card progress{height:7px;width:100%;accent-color:var(--primary);margin:12px 0}.job-message{font-size:11px;color:var(--muted);line-height:1.8;overflow-wrap:anywhere}.job-error{color:var(--danger)}.resource-boundary{margin:20px 0;border-bottom:1px solid var(--border);padding-bottom:24px}
</style>
