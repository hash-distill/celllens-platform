<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRunStore } from '../stores/run'
import { runSourceLabel } from '../utils/source'
import ResponseWorkspace from '../components/response/ResponseWorkspace.vue'
import ResponseIntro from '../components/response/ResponseIntro.vue'
import EvidenceSidebar from '../components/EvidenceSidebar.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import UiIcon from '../components/UiIcon.vue'

const route = useRoute()
const router = useRouter()
const runs = useRunStore()
const runId = computed(() => typeof route.query.run === 'string' ? route.query.run : '')
const entry = computed(() => runId.value ? runs.entry(runId.value) : null)
const chapters = [
  { name: '实验问题', title: '一次扰动，会带来什么变化？', text: '给定细胞背景与基因扰动，从预测表达追踪潜在代谢响应。', focus: 'overview' },
  { name: '状态与表达', title: '一次扰动，怎样改变表达？', text: '先比较单细胞状态分布，再查看群体表达变化，区分对照与预测。', focus: 'nucleus' },
  { name: '代谢功能', title: '从表达变化，追踪功能响应。', text: '任务分数与覆盖证据并列呈现，保留结果的适用边界。', focus: 'mitochondria' },
  { name: '证据与验证', title: '每一个结论，都有出处。', text: '回到本次运行的观测、指标和来源记录。', focus: 'overview' },
] as const
const step = computed(() => {
  const number = Number(route.query.step ?? 0)
  return Number.isInteger(number) && number >= 0 && number < chapters.length ? number : 0
})
const chapter = computed(() => chapters[step.value]!)
/** 每章自动播放时长；演示讲稿的手动节奏不受影响。 */
const CHAPTER_MS = 10000
const playing = ref(false)
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
let timer: number | undefined
let progressTimer: number | undefined
/** 0–1，按真实经过时间推进，供进度条与倒计时共用。 */
const autoplayProgress = ref(0)
const source = computed(() => entry.value?.record
  ? runSourceLabel(entry.value.record.request.mode, runId.value) : '未绑定实验 · 分析流程介绍')
const completed = computed(() => entry.value?.record?.status === 'completed')

function go(index: number): void {
  void router.replace({ path: '/demo', query: { ...route.query, step: Math.max(0, Math.min(3, index)) } })
}
function clearTimer(): void {
  window.clearTimeout(timer)
  timer = undefined
  window.clearInterval(progressTimer)
  progressTimer = undefined
}
function stop(): void {
  playing.value = false
  clearTimer()
}
function schedule(): void {
  clearTimer()
  if (!playing.value) return
  // 无反馈的等待会让人以为按钮失效，所以进度条与倒计时都按真实时间推进。
  const started = performance.now()
  autoplayProgress.value = 0
  progressTimer = window.setInterval(() => {
    autoplayProgress.value = Math.min(1, (performance.now() - started) / CHAPTER_MS)
  }, 100)
  timer = window.setTimeout(() => {
    if (step.value >= 3) stop()
    else { go(step.value + 1); schedule() }
  }, CHAPTER_MS)
}
function togglePlay(): void {
  playing.value = !playing.value
  if (playing.value) { if (step.value === 3) go(0); schedule() }
  else clearTimer()
}
function exit(): void {
  stop()
  void router.push(runId.value ? {path: '/workbench', query:{run:runId.value}} : '/workbench')
}
function keydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') { exit(); return }
  const target = event.target as HTMLElement | null
  if (target?.closest('input,select,textarea,[contenteditable="true"]')) return
  if (event.key === 'ArrowRight') { stop(); go(step.value + 1) }
  if (event.key === 'ArrowLeft') { stop(); go(step.value - 1) }
  if (event.code === 'Space' && !target?.closest('button,a')) { event.preventDefault(); togglePlay() }
}
function visibility(): void { if (document.hidden) stop() }
watch(runId, id => { if (id) runs.openRun(id); else runs.leaveRun() }, {immediate:true})
watch([step, () => entry.value?.record?.status], () => {
  if (completed.value && runId.value) {
    if (step.value === 2) runs.ensureTabData(runId.value, 'metabolism')
    if (step.value === 3) runs.ensureTabData(runId.value, 'validation')
  }
}, {immediate:true})
// 手动切章后从零重新计时，进度条不会显示上一章的残留进度。
watch(step, () => { if (playing.value) schedule() })
onMounted(() => {
  window.addEventListener('keydown', keydown)
  document.addEventListener('visibilitychange', visibility)
})
onBeforeUnmount(() => {
  stop()
  window.removeEventListener('keydown', keydown)
  document.removeEventListener('visibilitychange', visibility)
  runs.leaveRun()
})
</script>

<template>
  <div class="page demo-page">
    <header class="demo-top">
      <div><span class="micro">CELLLENS / PRESENTATION</span><span class="demo-source">{{ source }}</span></div>
      <div class="demo-controls">
        <button class="btn btn-sm" type="button" :aria-pressed="playing" @click="togglePlay"><UiIcon :name="playing ? 'pause':'play'" :size="14" />{{ playing ? '暂停演示':'自动播放' }}</button>
        <button class="btn btn-sm" type="button" @click="exit"><UiIcon name="back" :size="14" />返回工作台</button>
      </div>
    </header>
    <div class="demo-title"><span class="demo-number">0{{ step+1 }}</span><div><h1>{{ chapter.title }}</h1><p>{{ chapter.text }}</p></div><span class="micro demo-scope">预测 · 功能 · 证据</span></div>
    <div class="demo-progress" aria-hidden="true"><span :style="{transform:`scaleX(${playing ? autoplayProgress : 0})`}" /></div>
    <p v-if="playing" class="demo-progress-note" role="status">自动播放中 · 第 {{ step + 1 }}/4 章 · {{ Math.max(1, Math.ceil(CHAPTER_MS / 1000 * (1 - autoplayProgress))) }} 秒后进入下一章</p>
    <div class="demo-stage">
      <template v-if="step === 0">
        <div v-if="entry?.record" class="demo-experiment"><span class="micro">本次实验</span><h2>{{ entry.record.request.cell_line }} / {{ entry.record.request.perturbation }}</h2><p>{{ entry.record.request.n_cells }} 个采样细胞 · 随机种子 {{ entry.record.request.seed }} · {{ source }}</p><code>{{ runId }}</code></div>
        <ResponseIntro />
      </template>
      <section v-else-if="!runId" class="demo-result demo-empty"><h2>选择一次实验，查看实际响应。</h2><p>当前只介绍分析流程。完成运行后，从工作台点击“演示本次实验”。</p><RouterLink to="/workbench" class="btn btn-primary">打开工作台</RouterLink></section>
      <section v-else-if="entry?.notFound" class="demo-result demo-empty"><h2>运行不存在</h2><p>请检查运行编号。</p></section>
      <section v-else-if="!completed" class="demo-result demo-empty"><h2>{{ entry?.record?.status === 'failed' ? '本次计算失败' : '等待本次实验完成' }}</h2><p>{{ entry?.recordError?.message || entry?.record?.error_message || '结果就绪后自动显示，不使用替代样例。' }}</p></section>
      <ResponseWorkspace v-else-if="step === 1 || step === 2" :key="runId + ':' + step" :run-id="runId" :focus="step === 1 ? 'genes' : 'tasks'" />
      <section v-else class="demo-result"><ValidationTab :run-id="runId" /><EvidenceSidebar v-if="entry" :entry="entry" /><RouterLink :to="{path:'/runs/'+runId,query:{tab:'validation'}}" class="btn">打开完整验证与来源记录 →</RouterLink></section>
    </div>
    <footer class="demo-bottom">
      <button class="btn btn-sm" :disabled="step===0" @click="stop();go(step-1)">← 上一章</button>
      <nav aria-label="演示章节"><button v-for="(item,index) in chapters" :key="item.name" :class="{active:step===index}" :aria-current="step===index?'step':undefined" @click="stop();go(index)"><span>0{{ index+1 }}</span>{{ item.name }}</button></nav>
      <button class="btn btn-sm" :disabled="step===3" @click="stop();go(step+1)">下一章 →</button>
    </footer>
    <p class="demo-keyhint">← / → 切换章节 · 空格播放或暂停 · Esc 返回 · 自动播放每章 {{ Math.round(CHAPTER_MS / 1000) }} 秒{{ reducedMotion ? ' · 已启用减少动态':'' }}</p>
  </div>
</template>
<style scoped>
.demo-experiment{padding:20px 24px;border:1px solid var(--border);background:var(--card);margin-bottom:18px}.demo-experiment h2{font-size:24px;font-weight:500;margin:8px 0}.demo-experiment p,.demo-experiment code{font-size:11px;color:var(--muted)}.demo-page{padding-top:32px}.demo-top{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:18px;gap:16px}.demo-source{display:block;font-size:11px;color:var(--muted);margin-top:4px}.demo-controls{display:flex;gap:8px}.demo-controls .btn{display:flex;align-items:center;gap:7px}.demo-title{display:flex;align-items:center;gap:24px;padding:30px 0 26px}.demo-number{font-size:58px;line-height:1;color:#aebbb2;font-weight:300;font-family:Georgia,serif}.demo-title h1{font-size:29px;font-weight:500;letter-spacing:-.02em}.demo-title p{font-size:12px;margin:10px 0 0;color:var(--muted)}.demo-scope{margin-left:auto}.demo-progress{height:2px;background:var(--border);overflow:hidden}.demo-progress span{display:block;height:100%;background:var(--primary);transform:scaleX(0);transform-origin:left center}.demo-progress-note{font-size:11px;color:var(--primary);margin:8px 0 0;font-variant-numeric:tabular-nums}.demo-stage{min-width:0}.demo-stage--split{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(300px,1fr);gap:18px}.demo-stage :deep(.cell-viewport){height:clamp(500px,calc(100vh - 350px),740px);min-height:500px}.demo-result{border:1px solid var(--border);padding:28px;background:var(--card);min-width:0}.demo-result h2{font-size:21px;font-weight:500;margin:10px 0 20px}.demo-empty{padding:50px 10px}.demo-empty p{font-size:13px;color:var(--muted);max-width:360px;margin-bottom:24px}.demo-task{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);font-size:13px}.demo-task small{display:block;font-size:10px;color:var(--muted);margin-top:6px}.demo-task strong{font-size:21px;font-weight:400}.up{color:var(--delta-up)}.down{color:var(--delta-down)}.demo-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:22px;gap:15px}.demo-bottom nav{display:flex;gap:6px}.demo-bottom nav button{display:flex;align-items:center;gap:9px;background:none;border:0;border-top:2px solid var(--border);padding:14px 20px 4px;color:var(--muted);cursor:pointer;font-size:12px}.demo-bottom nav button.active{border-color:var(--primary);color:var(--primary)}.demo-bottom nav span{font-size:10px;color:var(--faint)}.demo-keyhint{text-align:center;font-size:10px;color:var(--faint);margin:16px 0 0}
@media(max-width:1000px){.demo-page{padding:16px}.demo-stage--split{grid-template-columns:1fr}.demo-title h1{font-size:24px}.demo-scope{display:none}.demo-bottom nav button{padding:10px;font-size:10px}.demo-stage :deep(.cell-viewport){height:500px}.demo-result{padding:20px}}
@media(max-width:600px){.demo-title{gap:14px}.demo-number{font-size:40px}.demo-title h1{font-size:20px}.demo-bottom{flex-wrap:wrap}.demo-bottom nav{order:-1;width:100%;justify-content:space-between}.demo-bottom nav button{padding:10px 3px;gap:3px}.demo-stage :deep(.cell-viewport){height:440px;min-height:440px}.demo-controls .btn{font-size:10px}.demo-top{gap:6px}}
</style>
