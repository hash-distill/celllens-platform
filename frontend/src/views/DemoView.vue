<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRunStore } from '../stores/run'
import { useSceneStore } from '../stores/scene'
import { runSourceLabel } from '../utils/source'
import { fmtDelta, EVIDENCE_LABEL } from '../utils/format'
import DivergingBar from '../charts/DivergingBar.vue'
import ValidationTab from '../components/tabs/ValidationTab.vue'
import UiIcon from '../components/UiIcon.vue'

const CellViewport = defineAsyncComponent(() => import('../components/scene/CellViewport.vue'))
const route = useRoute()
const router = useRouter()
const runs = useRunStore()
const scene = useSceneStore()
const runId = computed(() => typeof route.query.run === 'string' ? route.query.run : '')
const entry = computed(() => runId.value ? runs.entry(runId.value) : null)
const chapters = [
  { name: '细胞结构', title: '从结构，走进细胞。', text: '旋转与剖切细胞，观察细胞核、内质网和线粒体的内部层次。', focus: 'overview' },
  { name: '基因扰动', title: '一次扰动，怎样改变表达？', text: '读取本次实验的平均表达变化，区分对照与预测。', focus: 'nucleus' },
  { name: '代谢响应', title: '从表达变化，追踪功能响应。', text: '任务分数与覆盖证据并列呈现，保留结果的适用边界。', focus: 'mitochondria' },
  { name: '验证与证据', title: '每一个结论，都有出处。', text: '回到本次运行的观测、指标和来源记录。', focus: 'overview' },
] as const
const step = computed(() => {
  const number = Number(route.query.step ?? 0)
  return Number.isInteger(number) && number >= 0 && number < chapters.length ? number : 0
})
const chapter = computed(() => chapters[step.value]!)
const playing = ref(false)
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
let timer: number | undefined
const savedScene = {
  selected: scene.selected, cameraPreset: scene.cameraPreset, cutaway: scene.cutaway,
  rotating: scene.rotating,
}
const source = computed(() => entry.value?.record
  ? runSourceLabel(entry.value.record.request.mode, runId.value) : '未绑定实验 · 结构演示')
const completed = computed(() => entry.value?.record?.status === 'completed')
const genes = computed(() => (entry.value?.summary.data?.top_genes ?? []).slice(0, 8).map(g => ({
  name: g.label, value: g.predicted_delta,
})))
const tasks = computed(() => (entry.value?.tasks.data?.items ?? [])
  .slice().sort((a,b) => Math.abs(b.predicted_delta)-Math.abs(a.predicted_delta)).slice(0,6))

function go(index: number): void {
  void router.replace({ path: '/demo', query: { ...route.query, step: Math.max(0, Math.min(3, index)) } })
}
function stop(): void {
  playing.value = false
  window.clearTimeout(timer)
}
function schedule(): void {
  window.clearTimeout(timer)
  if (!playing.value) return
  timer = window.setTimeout(() => {
    if (step.value >= 3) stop()
    else { go(step.value + 1); schedule() }
  }, 22000)
}
function togglePlay(): void {
  playing.value = !playing.value
  if (playing.value) { if (step.value === 3) go(0); schedule() }
  else window.clearTimeout(timer)
}
function exit(): void {
  stop()
  void router.push(runId.value ? {path: '/runs/'+encodeURIComponent(runId.value), query:{tab:'structure'}} : '/workbench')
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
  scene.cameraPreset = chapter.value.focus
  scene.cutaway = true
  scene.rotating = false
  scene.selected = step.value === 1 ? 'nucleus' : 'mitochondria'
  if (completed.value && runId.value) {
    if (step.value === 2) runs.ensureTabData(runId.value, 'metabolism')
    if (step.value === 3) runs.ensureTabData(runId.value, 'validation')
  }
}, {immediate:true})
onMounted(() => {
  window.addEventListener('keydown', keydown)
  document.addEventListener('visibilitychange', visibility)
})
onBeforeUnmount(() => {
  stop()
  window.removeEventListener('keydown', keydown)
  document.removeEventListener('visibilitychange', visibility)
  Object.assign(scene, savedScene)
  runs.leaveRun()
})
</script>

<template>
  <main class="demo-page">
    <header class="demo-top">
      <div><span class="micro">CELLLENS / PRESENTATION</span><span class="demo-source">{{ source }}</span></div>
      <div class="demo-controls">
        <button class="btn btn-sm" type="button" :aria-pressed="playing" @click="togglePlay"><UiIcon :name="playing ? 'pause':'play'" :size="14" />{{ playing ? '暂停演示':'自动播放' }}</button>
        <button class="btn btn-sm" type="button" @click="exit"><UiIcon name="back" :size="14" />返回工作台</button>
      </div>
    </header>
    <div class="demo-title"><span class="demo-number">0{{ step+1 }}</span><div><h1>{{ chapter.title }}</h1><p>{{ chapter.text }}</p></div><span class="micro demo-scope">结构示意 · 非实测形态</span></div>
    <div class="demo-stage" :class="{'demo-stage--split':step===1||step===2}">
      <CellViewport v-if="step < 3" :presentation="true" />
      <section v-if="step > 0" class="demo-result">
        <div v-if="!runId" class="demo-empty"><span class="micro">NO EXPERIMENT SELECTED</span><h2>为结果，选择一次实验。</h2><p>当前仅展示细胞结构。完成实验后，在结果页点击「演示本次实验」读取本次数据。</p><RouterLink to="/workbench" class="btn btn-primary">开始实验</RouterLink></div>
        <div v-else-if="entry?.notFound" class="demo-empty"><h2>运行不存在</h2><p>请检查运行编号；结构演示仍可操作。</p></div>
        <div v-else-if="!completed" class="demo-empty"><h2>{{ entry?.record?.status === 'failed' ? '本次计算失败' : '等待本次实验完成' }}</h2><p>结果就绪后自动显示，不使用替代样例。</p></div>
        <template v-else-if="step===1">
          <span class="micro">EXPRESSION RESPONSE</span><h2>{{ entry?.record?.request.perturbation }} / 基因响应</h2>
          <p v-if="entry?.summary.status==='idle'||entry?.summary.status==='loading'" class="muted">正在读取基因摘要…</p>
          <div v-else-if="entry?.summary.status==='error'" class="notice notice-warn">基因摘要读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId,'summary')">重试</button></div>
          <DivergingBar v-else-if="genes.length" :items="genes" category-name="基因" value-label="预测变化" :height="360" />
          <p v-else class="muted">本次运行未提供基因摘要。</p>
          <p class="small muted">预测减对照的平均归一化表达差。细胞器外形保持结构示意，不随数值变形。</p>
        </template>
        <template v-else-if="step===2">
          <span class="micro">METABOLIC RESPONSE</span><h2>任务分数变化</h2>
          <div v-if="entry?.tasks.status==='error'" class="notice notice-warn">任务结果读取失败。<button class="btn btn-sm" @click="runs.retryBlock(runId,'tasks')">重试</button></div>
          <p v-else-if="entry?.tasks.status==='loading'" class="muted">正在读取任务结果…</p>
          <div v-for="task in tasks" :key="task.id" class="demo-task"><span>{{ task.label }}<small>{{ EVIDENCE_LABEL[task.evidence_level] }} · 覆盖 {{ Math.round(task.coverage*100) }}%</small></span><strong :class="task.predicted_delta>=0?'up':'down'">{{ fmtDelta(task.predicted_delta) }}</strong></div>
          <p v-if="entry?.tasks.status==='ok'&&!tasks.length" class="muted">本次运行没有任务结果。</p>
          <p class="small muted">当前为已加载记录中变化幅度最大的 {{ tasks.length }} 项。任务分数不等同于实测通量，尚未建立细胞器与任务映射。</p>
        </template>
        <template v-else><ValidationTab :run-id="runId" /><RouterLink :to="{path:'/runs/'+runId,query:{tab:'validation'}}" class="btn">打开完整验证与来源记录 →</RouterLink></template>
      </section>
    </div>
    <footer class="demo-bottom">
      <button class="btn btn-sm" :disabled="step===0" @click="stop();go(step-1)">← 上一章</button>
      <nav aria-label="演示章节"><button v-for="(item,index) in chapters" :key="item.name" :class="{active:step===index}" :aria-current="step===index?'step':undefined" @click="stop();go(index)"><span>0{{ index+1 }}</span>{{ item.name }}</button></nav>
      <button class="btn btn-sm" :disabled="step===3" @click="stop();go(step+1)">下一章 →</button>
    </footer>
    <p class="demo-keyhint">← / → 切换章节 · 空格播放或暂停 · Esc 返回 · 每章 22 秒{{ reducedMotion ? ' · 已启用减少动态':'' }}</p>
  </main>
</template>
<style scoped>
.demo-page{padding:20px 36px 18px;max-width:1900px;margin:auto}.demo-top{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);padding-bottom:18px;gap:16px}.demo-source{display:block;font-size:11px;color:var(--muted);margin-top:4px}.demo-controls{display:flex;gap:8px}.demo-controls .btn{display:flex;align-items:center;gap:7px}.demo-title{display:flex;align-items:center;gap:24px;padding:30px 0 26px}.demo-number{font-size:58px;line-height:1;color:#aebbb2;font-weight:300;font-family:Georgia,serif}.demo-title h1{font-size:29px;font-weight:500;letter-spacing:-.02em}.demo-title p{font-size:12px;margin:10px 0 0;color:var(--muted)}.demo-scope{margin-left:auto}.demo-stage{min-width:0}.demo-stage--split{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(300px,1fr);gap:18px}.demo-stage :deep(.cell-viewport){height:clamp(500px,calc(100vh - 350px),740px);min-height:500px}.demo-result{border:1px solid var(--border);padding:28px;background:var(--card);min-width:0}.demo-result h2{font-size:21px;font-weight:500;margin:10px 0 20px}.demo-empty{padding:50px 10px}.demo-empty p{font-size:13px;color:var(--muted);max-width:360px;margin-bottom:24px}.demo-task{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);font-size:13px}.demo-task small{display:block;font-size:10px;color:var(--muted);margin-top:6px}.demo-task strong{font-size:21px;font-weight:400}.up{color:var(--delta-up)}.down{color:var(--delta-down)}.demo-bottom{display:flex;align-items:center;justify-content:space-between;margin-top:22px;gap:15px}.demo-bottom nav{display:flex;gap:6px}.demo-bottom nav button{display:flex;align-items:center;gap:9px;background:none;border:0;border-top:2px solid var(--border);padding:14px 20px 4px;color:var(--muted);cursor:pointer;font-size:12px}.demo-bottom nav button.active{border-color:var(--primary);color:var(--primary)}.demo-bottom nav span{font-size:10px;color:var(--faint)}.demo-keyhint{text-align:center;font-size:10px;color:var(--faint);margin:16px 0 0}
@media(max-width:1000px){.demo-page{padding:16px}.demo-stage--split{grid-template-columns:1fr}.demo-title h1{font-size:24px}.demo-scope{display:none}.demo-bottom nav button{padding:10px;font-size:10px}.demo-stage :deep(.cell-viewport){height:500px}.demo-result{padding:20px}}
@media(max-width:600px){.demo-title{gap:14px}.demo-number{font-size:40px}.demo-title h1{font-size:20px}.demo-bottom{flex-wrap:wrap}.demo-bottom nav{order:-1;width:100%;justify-content:space-between}.demo-bottom nav button{padding:10px 3px;gap:3px}.demo-stage :deep(.cell-viewport){height:440px;min-height:440px}.demo-controls .btn{font-size:10px}.demo-top{gap:6px}}
</style>
