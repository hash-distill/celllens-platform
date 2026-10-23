<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { apiFetch } from '../api/http'
import { isMockEnabled } from '../api/mockFlag'
import { useServiceStore } from '../stores/service'
import type { SystemStatus } from '../types/system'
import InferenceResources from '../components/InferenceResources.vue'

const service = useServiceStore()
const data = ref<SystemStatus | null>(null), loading = ref(false), error = ref('')
const mock = isMockEnabled()
let controller: AbortController | undefined
const bytes = (value: number | null | undefined) => value == null ? '未获取' : `${(value / 1024 ** 3).toFixed(1)} GiB`
const percentage = (used: number | null, total: number | null) => used == null || !total ? null : Math.max(0, Math.min(100, used / total * 100))
const resources = computed(() => data.value ? [
  {name: '系统内存', ...data.value.system.memory},
  {name: '数据所在磁盘', ...data.value.system.storage},
] : [])
const workerLabel = (enabled: boolean, running: boolean) => running ? '运行中' : enabled ? '已启用 · 未运行' : '未启用'
async function refresh() {
  if (loading.value) return
  controller?.abort(); const current = new AbortController(); controller = current
  loading.value = true; error.value = ''
  try {
    if (mock) {data.value = null; error.value = '示例模式不提供实时服务状态。'; return}
    const result = await apiFetch<SystemStatus>('/system-status', {signal: current.signal, timeoutMs: 15000})
    if (!current.signal.aborted) data.value = result
  } catch (reason) {
    if (!current.signal.aborted) {data.value = null; error.value = reason instanceof Error ? reason.message : '服务状态读取失败'}
  } finally {if (!current.signal.aborted) loading.value = false}
}
function check() {void service.refresh(); void refresh()}
onMounted(check)
onBeforeUnmount(() => controller?.abort())
</script>
<template>
  <div class="page status-page">
    <header class="page-heading"><div><span class="eyebrow">SERVICE & ENVIRONMENT</span><h1>服务状态</h1><p>查看服务连接、计算资源与分析任务状态。</p></div><button class="btn btn-primary" :disabled="loading || service.checking" @click="check">{{ loading ? '检查中…' : '重新检查' }}</button></header>
    <div v-if="error" class="notice notice-danger" role="alert">{{ error }}<button class="btn btn-sm" @click="check">重试</button></div>
    <div v-if="loading && !data" class="card" role="status">正在检测服务环境…</div>
    <InferenceResources v-if="!mock" />
    <template v-if="data">
      <section class="status-overview" aria-label="服务连接概览"><div class="overall"><span class="eyebrow">CURRENT SERVICE</span><h2><i :class="service.level" />{{ service.levelLabel }}</h2><p>采集于 {{ new Date(data.checked_at).toLocaleString() }}</p></div><div><span>数据库连接</span><strong :class="{warning: !data.database.connected}">{{ data.database.connected ? '已连接' : '不可用' }}</strong><small>{{ data.database.latency_ms == null ? '延迟未获取' : `${data.database.latency_ms} ms 响应延迟` }}</small></div><div><span>GPU 设备</span><strong>{{ data.gpu.devices.length }} <small>张</small></strong><small>{{ data.gpu.configured ? 'GPU 推演：已启用' : 'GPU 推演：未启用' }}</small></div><div><span>CPU 逻辑核心</span><strong>{{ data.system.cpu_logical_cores ?? '—' }}</strong><small>{{ data.system.architecture }}</small></div></section>
      <div class="status-grid">
        <section class="card gpu-panel" aria-label="GPU 配置"><div class="section-heading"><div><span class="eyebrow">COMPUTE / GPU</span><h2>图形计算资源</h2></div><span class="pill pill-neutral">{{ data.gpu.detected ? '已检测' : '未获取' }}</span></div>
          <p v-if="!data.gpu.devices.length" class="muted">{{ data.gpu.message }}</p>
          <article v-for="gpu in data.gpu.devices" :key="gpu.index" class="gpu-device"><div class="device-heading"><h3>{{ gpu.name }}</h3><span class="mono">GPU {{ gpu.index }}</span></div><dl><dt>驱动版本</dt><dd>{{ gpu.driver_version }}</dd><dt>总显存</dt><dd>{{ bytes(gpu.memory_total_bytes) }}</dd><dt>已用显存</dt><dd>{{ bytes(gpu.memory_used_bytes) }}</dd><dt>温度</dt><dd>{{ gpu.temperature_c == null ? '未获取' : `${gpu.temperature_c} °C` }}</dd></dl>
            <div class="meter-heading"><span>显存使用</span><strong>{{ percentage(gpu.memory_used_bytes, gpu.memory_total_bytes)?.toFixed(1) ?? '—' }}%</strong></div><progress v-if="percentage(gpu.memory_used_bytes, gpu.memory_total_bytes) !== null" max="100" :value="percentage(gpu.memory_used_bytes, gpu.memory_total_bytes) ?? 0" :aria-label="`${gpu.name} 显存使用率`" />
            <div class="meter-heading"><span>GPU 利用率</span><strong>{{ gpu.utilization_percent == null ? '未获取' : `${gpu.utilization_percent}%` }}</strong></div><progress v-if="gpu.utilization_percent !== null" max="100" :value="gpu.utilization_percent" :aria-label="`${gpu.name} 利用率`" />
          </article>
        </section>
        <section class="card" aria-label="系统资源"><span class="eyebrow">HOST / RESOURCES</span><h2>系统资源</h2><p class="muted cpu-model">{{ data.system.cpu_model ?? 'CPU 型号未获取' }}</p><article v-for="resource in resources" :key="resource.name" class="resource"><div class="meter-heading"><h3>{{ resource.name }}</h3><strong>{{ percentage(resource.used_bytes, resource.total_bytes)?.toFixed(1) ?? '—' }}%</strong></div><progress v-if="percentage(resource.used_bytes, resource.total_bytes) !== null" max="100" :value="percentage(resource.used_bytes, resource.total_bytes) ?? 0" :aria-label="`${resource.name}使用率`" /><p class="muted">已用 {{ bytes(resource.used_bytes) }} / 总量 {{ bytes(resource.total_bytes) }}</p></article><p class="muted">实时资源使用情况。</p></section>
        <section class="card" aria-label="数据库配置"><span class="eyebrow">STORAGE / DATABASE</span><h2>数据库配置</h2><dl><dt>数据库引擎</dt><dd>{{ data.database.engine }}</dd><dt>服务端版本</dt><dd>{{ data.database.version ?? '未获取' }}</dd><dt>连接池大小</dt><dd>{{ data.database.pool_size ?? '未获取' }}</dd><dt>借出的连接</dt><dd>{{ data.database.checked_out ?? '未获取' }}</dd><dt>连接状态</dt><dd>{{ data.database.connected ? '连接正常' : '连接不可用' }}</dd></dl></section>
        <section class="card" aria-label="分析服务"><span class="eyebrow">PIPELINE / WORKERS</span><h2>分析服务</h2><div class="worker-row"><div><h3>在线扰动推演</h3><p>STATE → 表达响应 → scCellFie</p></div><span :class="{warning: !data.workers.online_running}">{{ workerLabel(data.workers.online_enabled, data.workers.online_running) }}</span></div><dl><dt>在线待完成任务</dt><dd>{{ data.workers.online_pending ?? '未获取' }}</dd></dl></section>
      </div>
      <section class="card environment" aria-label="运行环境"><span class="eyebrow">RUNTIME / CONFIGURATION</span><h2>运行环境与依赖</h2><p class="muted">查看系统与分析引擎版本。</p><div class="environment-grid"><dl><dt>操作系统</dt><dd>{{ data.system.os }} {{ data.system.os_release }}<template v-if="data.system.os_display_version"> · {{ data.system.os_display_version }}</template></dd><dt>系统构建版本</dt><dd class="mono">{{ data.system.os_version }}</dd><dt>Python</dt><dd>{{ data.system.python }}</dd></dl><dl><template v-for="(version, name) in data.versions" :key="name"><dt>{{ name }}</dt><dd class="mono">{{ version ?? '未安装' }}</dd></template></dl></div></section>
    </template>
  </div>
</template>
<style scoped>
.status-page h2{font-size:21px;font-weight:500;margin:10px 0 22px}.status-page h3{font-size:13px;font-weight:500;margin:0}.status-overview{display:grid;grid-template-columns:1.4fr repeat(3,1fr);border:1px solid var(--border);background:var(--card);margin-bottom:24px}.status-overview>div{padding:26px;border-right:1px solid var(--border);display:flex;flex-direction:column;justify-content:center;gap:12px}.status-overview>div:last-child{border:0}.status-overview span,.status-overview small{font-size:11px;color:var(--muted)}.status-overview strong{font:27px Georgia,serif;color:var(--primary)}.status-overview h2{display:flex;align-items:center;gap:12px;margin:0}.overall i{width:9px;height:9px;border-radius:50%;background:var(--faint)}.overall i.ok{background:var(--ok)}.overall i.down{background:var(--danger)}.overall i.degraded{background:var(--warn)}.overall p{font-size:10px;color:var(--muted);margin:0}.status-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:24px}.status-grid>.card{margin:0;min-width:0}.section-heading,.device-heading,.meter-heading{display:flex;justify-content:space-between;align-items:center;gap:16px}.section-heading h2{margin-bottom:14px}.device-heading{padding:15px 0;border-top:1px solid var(--border)}.device-heading h3{font-size:17px}.device-heading span{font-size:10px;color:var(--muted)}dl{display:grid;grid-template-columns:minmax(100px,.8fr) minmax(0,1.3fr);gap:13px 20px;font-size:12px;line-height:1.7;margin:12px 0 24px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.meter-heading{font-size:11px;margin:20px 0 10px}.meter-heading strong{font-weight:500;color:var(--primary);font-variant-numeric:tabular-nums}progress{display:block;width:100%;height:8px;border:0;border-radius:0;background:var(--surface-soft);accent-color:var(--primary)}progress::-webkit-progress-bar{background:var(--surface-soft)}progress::-webkit-progress-value{background:var(--primary)}progress::-moz-progress-bar{background:var(--primary)}.muted{color:var(--muted);font-size:11px;line-height:1.9}.cpu-model{min-height:36px}.resource{padding:8px 0 12px;border-bottom:1px solid var(--border)}.worker-row{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:18px 0;border-bottom:1px solid var(--border)}.worker-row p{font-size:10px;color:var(--muted);margin:8px 0 0}.worker-row>span{font-size:11px;color:var(--ok);text-align:right}.warning{color:var(--warn)!important}.environment{margin-top:24px}.environment-grid{display:grid;grid-template-columns:1.25fr 1fr;gap:48px}.status-page>.notice{margin-bottom:24px}
</style>
