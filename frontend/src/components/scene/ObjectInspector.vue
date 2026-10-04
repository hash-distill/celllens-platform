<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useSceneStore } from '../../stores/scene'
import { useRunStore } from '../../stores/run'
import { runSourceLabel } from '../../utils/source'
import UiIcon from '../UiIcon.vue'
const props = defineProps<{ runId?: string }>()
const scene = useSceneStore()
const runs = useRunStore()
const router = useRouter()
const entry = computed(() => props.runId ? runs.entry(props.runId) : null)
const completed = computed(() => entry.value?.record?.status === 'completed')
const source = computed(() => entry.value?.record ? runSourceLabel(entry.value.record.request.mode, props.runId) : '尚未打开运行')
function showResults() { if (props.runId) void router.push({path: `/runs/${encodeURIComponent(props.runId)}`, query: {tab:'metabolism'}}) }
</script>
<template>
  <aside class="object-inspector" aria-label="对象属性">
    <div class="panel-heading"><h2>对象属性</h2><UiIcon name="cube" :size="15" /></div>
    <div class="object-specimen" :style="{'--specimen-color': scene.selectedMeta.color}">
      <svg viewBox="0 0 180 115" class="specimen-symbol" aria-hidden="true">
        <g v-if="scene.selected === 'mitochondria'" transform="rotate(-18 90 57)"><path d="M35 59C25 22 69 14 106 21s48 32 35 56-43 23-76 12S40 78 35 59Z" fill="currentColor" fill-opacity=".15" stroke="currentColor" stroke-width="2"/><path d="M45 59c13-31 13 22 26 0s10-27 20-1 12-28 22-1 13 0 19-13" fill="none" stroke="currentColor" stroke-width="3"/><path d="M42 54C38 29 78 25 109 31s32 32 24 43-30 21-62 8S45 70 42 54Z" fill="none" stroke="currentColor" stroke-width="1"/></g>
        <g v-else-if="scene.selected === 'nucleus'"><ellipse cx="90" cy="57" rx="47" ry="41" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="2"/><circle cx="100" cy="62" r="16" fill="currentColor" fill-opacity=".4"/><path d="m60 40 23 11-14 18 24-4 14 16 12-27-27-20Z" fill="none" stroke="currentColor"/></g>
        <g v-else-if="scene.selected === 'membrane'"><ellipse cx="90" cy="57" rx="61" ry="41" fill="currentColor" fill-opacity=".07" stroke="currentColor" stroke-width="2"/><ellipse cx="90" cy="57" rx="55" ry="35" fill="none" stroke="currentColor" stroke-dasharray="2 4"/></g>
        <g v-else><path v-for="i in 5" :key="i" :d="`M40 ${25+i*10} C65 ${5+i*10} 115 ${45+i*10} 142 ${20+i*10}`" fill="none" stroke="currentColor" :stroke-width="scene.selected === 'golgi' ? 6 : 3" stroke-linecap="round"/></g>
      </svg>
      <span class="micro">SCHEMATIC STRUCTURE</span>
    </div>
    <h3 class="object-name">{{ scene.selectedMeta.name }}</h3>
    <p class="object-english">{{ scene.selectedMeta.english }}</p>
    <p class="object-description">{{ scene.selectedMeta.description }}</p>
    <section class="inspector-section">
      <div class="panel-heading"><h2>关联结果</h2><span class="micro">待映射</span></div>
      <div class="inspector-empty"><UiIcon name="layers" :size="22" /><p>尚未建立区室与任务映射</p><span>可查看本次运行的完整任务结果。</span></div>
      <button class="btn btn-sm inspector-action" type="button" :disabled="!completed" @click="showResults">查看任务结果 <UiIcon name="arrow" :size="14" /></button>
    </section>
    <section class="inspector-section">
      <h2 class="inspector-title">数据来源</h2>
      <dl class="source-list"><dt>结构</dt><dd>程序化示意模型</dd><dt>结果</dt><dd>{{ source }}</dd><dt>验证</dt><dd>以本次验证记录为准</dd></dl>
    </section>
    <p class="inspector-footnote"><UiIcon name="help" :size="14" /><span>结构示意不代表模型预测的细胞形态。</span></p>
  </aside>
</template>
<style scoped>
.object-inspector{padding:22px 20px;min-width:0;background:var(--card);border-left:1px solid var(--border)}.object-specimen{height:147px;margin:20px 0 14px;border:1px solid var(--border);background:#f7f7f2;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--specimen-color)}.specimen-symbol{width:160px;height:105px}.object-specimen .micro{font-size:8px;letter-spacing:.16em;color:var(--muted)}.object-name{font-size:25px;font-weight:500;letter-spacing:.04em}.object-english{font-size:11px;margin:5px 0 14px;color:var(--muted);letter-spacing:.06em}.object-description{font-size:12px;color:var(--muted);line-height:1.9;margin:0}.inspector-section{border-top:1px solid var(--border);padding-top:20px;margin-top:24px}.inspector-empty{text-align:center;padding:20px 0;color:#87928d}.inspector-empty p{font-size:12px;margin:10px 0 5px;color:var(--muted)}.inspector-empty span{font-size:10px}.inspector-action{width:100%;display:flex;justify-content:space-between;align-items:center}.inspector-title{font-size:12px}.source-list{display:grid;grid-template-columns:46px 1fr;gap:13px 8px;font-size:11px;margin:17px 0 0}.source-list dt{color:var(--muted)}.source-list dd{margin:0;overflow-wrap:anywhere}.inspector-footnote{display:flex;align-items:flex-start;gap:8px;font-size:10px;line-height:1.8;color:var(--muted);margin:24px 0 0}
</style>
