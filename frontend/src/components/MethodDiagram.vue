<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue'
import StateArchitecture from './methods/StateArchitecture.vue'
import ScCellFieArchitecture from './methods/ScCellFieArchitecture.vue'

const props = defineProps<{ kind: 'state' | 'sccellfie' }>()
const id = useId()
const preview = ref<HTMLButtonElement | null>(null)
const dialog = ref<HTMLDialogElement | null>(null)
const expanded = ref(false)
const canvas = computed(() => props.kind === 'state' ? StateArchitecture : ScCellFieArchitecture)
const figure = computed(() => props.kind === 'state' ? {
  title: 'STATE · 细胞集合扰动预测架构',
  filename: 'CellLens-STATE-ST-HVG-architecture.svg',
  explanation: '表达、扰动与批次分别编码；集合注意力建模细胞间关系，表达编码经残差支路参与解码。图中标出当前 2,000 基因 ST-HVG 配置及其下游分析。',
} : {
  title: 'scCellFie · 基因、反应与任务评分机制',
  filename: 'CellLens-scCellFie-human-Recon2-architecture.svg',
  explanation: '按阈值生成基因分数，经 GPR 逻辑和决定基因特异性校正得到反应分数，再按关联反应取均值。知识库的三类规则与独立覆盖核查用不同线型标示。',
})
async function openFigure() {
  expanded.value = true
  await nextTick()
  dialog.value?.showModal()
}
function closeFigure() { dialog.value?.close() }
function afterClose() { expanded.value = false; preview.value?.focus() }
function onBackdrop(event: MouseEvent) {
  const modal = dialog.value
  if (!modal || event.target !== modal) return
  const bounds = modal.getBoundingClientRect()
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) closeFigure()
}
function downloadSvg() {
  const svg = preview.value?.querySelector('svg')
  if (!svg) return
  // The figure includes its own styles, markers and editable text; no bitmap is embedded.
  const source = '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svg)
  const url = URL.createObjectURL(new Blob([source], { type: 'image/svg+xml;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = figure.value.filename
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
onBeforeUnmount(() => dialog.value?.close())
</script>

<template>
  <figure class="method-diagram">
    <button ref="preview" type="button" class="diagram-preview" :aria-label="'放大查看 ' + figure.title" @click="openFigure">
      <component :is="canvas" class="method-figure-image" />
      <span class="diagram-zoom">放大查看 <span aria-hidden="true">↗</span></span>
    </button>
    <figcaption>
      <div class="diagram-caption"><strong>{{ figure.title }}</strong><button type="button" class="diagram-download" @click="downloadSvg">下载 SVG 架构图 ↓</button></div>
      <p>{{ figure.explanation }}</p>
      <p class="diagram-provenance">依据原论文机制与当前接入代码，使用组件重绘；矩阵仅示意数据维度，不代表实验数值。下载文件中的文字、形状和线条均可编辑。</p>
    </figcaption>
    <dialog ref="dialog" class="diagram-modal" :aria-labelledby="`${id}-figure-title`" @cancel.prevent="closeFigure" @close="afterClose" @click="onBackdrop">
      <header><h2 :id="`${id}-figure-title`">{{ figure.title }}</h2><div><button type="button" class="diagram-download" @click="downloadSvg">下载 SVG ↓</button><button type="button" class="diagram-close" aria-label="关闭架构图" @click="closeFigure">×</button></div></header>
      <div v-if="expanded" class="diagram-expanded"><component :is="canvas" /></div>
    </dialog>
  </figure>
</template>

<style scoped>
.method-diagram{margin:28px 0 0;border:1px solid var(--border);background:var(--figure-soft-bg);border-radius:6px;overflow:hidden}.diagram-preview{position:relative;display:block;width:100%;padding:0 0 34px;border:0;background:#fff;cursor:zoom-in;color:var(--ink)}.method-figure-image{display:block;width:100%;height:auto}.diagram-zoom{position:absolute;right:20px;bottom:10px;display:flex;align-items:center;gap:14px;color:#426b6b;font:12px var(--font)}.diagram-preview:focus-visible{outline:3px solid var(--primary);outline-offset:-4px}figcaption{padding:19px 24px 18px;border-top:1px solid var(--border)}.diagram-caption{display:flex;align-items:center;justify-content:space-between;gap:24px;font-size:14px}.diagram-caption strong{font-weight:500;color:var(--ink)}.diagram-download{padding:2px 0;border:0;background:none;color:var(--primary);font:12px var(--font);white-space:nowrap;cursor:pointer}.diagram-download:hover{text-decoration:underline;text-underline-offset:4px}.diagram-download:focus-visible{outline:2px solid var(--primary);outline-offset:4px}figcaption p{font-size:12px;color:var(--muted);line-height:1.9;margin:10px 0 0}figcaption .diagram-provenance{font-size:11px;margin-top:5px}.diagram-modal{width:min(1700px,calc(100vw - 64px));max-width:none;max-height:calc(100vh - 56px);margin:auto;padding:0;border:1px solid var(--border-strong);border-radius:6px;background:#fff;color:var(--ink);overflow:auto}.diagram-modal::backdrop{background:#102a2bd9}.diagram-modal header{position:sticky;top:0;display:flex;align-items:center;justify-content:space-between;gap:24px;padding:14px 20px;background:var(--card);border-bottom:1px solid var(--border);z-index:1}.diagram-modal h2{font-size:16px;font-weight:500;margin:0}.diagram-modal header>div{display:flex;align-items:center;gap:24px}.diagram-close{display:grid;place-items:center;width:32px;height:32px;padding:0;border:1px solid var(--border);border-radius:50%;background:var(--card);color:var(--ink);font:22px var(--font);cursor:pointer}.diagram-close:hover{background:var(--primary-weak);color:var(--primary)}.diagram-close:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.diagram-expanded{min-width:1100px}.diagram-expanded>svg{display:block;width:100%;height:auto}
</style>
