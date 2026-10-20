<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { TaskTraceResponse } from '../../types/trace'
import { fmtDelta } from '../../utils/format'

const props = defineProps<{ data: TaskTraceResponse; selectedReaction: string }>()
const emit = defineEmits<{ select: [id: string] }>()
const host = ref<HTMLDivElement>()
const error = ref('')
const description = ref('点击节点查看数值；点击反应同步下方关联基因。')
const counts = ref({ reactions: 0, genes: 0 })
const labels = ref<Array<{key: string; text: string; x: number; y: number; kind: string}>>([])
let renderer: THREE.WebGLRenderer | undefined
let camera: THREE.PerspectiveCamera
let scene: THREE.Scene
let controls: OrbitControls
let group: THREE.Group
let resizeObserver: ResizeObserver
let themeObserver: MutationObserver | undefined
let frame = 0
let disposed = false
const clickable: THREE.Mesh[] = []
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
let start = { x: 0, y: 0 }

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function draw() {
  if (disposed || !renderer || !host.value) return
  renderer.render(scene, camera)
  const {width,height} = host.value.getBoundingClientRect()
  const selectedGenes = new Set(props.data.reactions.find(r => r.id === props.selectedReaction)?.genes.slice(0,10).map(g => g.id) ?? [])
  labels.value = clickable.filter(node => node.userData.kind !== 'gene' || selectedGenes.has(node.userData.id)).map(node => {
    const p = node.getWorldPosition(new THREE.Vector3()).project(camera)
    return {key:node.userData.kind+node.userData.id,text:node.userData.label,kind:node.userData.kind,
      x:Math.max(65,Math.min(width-65,(p.x*.5+.5)*width)),y:(-.5*p.y+.5)*height+13}
  }).filter(label => label.y>0 && label.y<height-20)
}
function clear() {
  if (!group) return
  group.traverse(object => {
    if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
      object.geometry.dispose()
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) material.dispose()
    }
  })
  scene.remove(group)
  clickable.length = 0
}
function build() {
  if (!renderer) return
  clear()
  group = new THREE.Group()
  group.scale.x = Math.min(2, Math.max(1, camera.aspect))
  scene.add(group)
  // Keep readable, deterministic layers; this is feature association space, not cellular anatomy.
  const reactions = props.data.reactions.slice(0, 8)
  const selected = props.data.reactions.find(r => r.id === props.selectedReaction)
  if (selected && !reactions.some(r => r.id === selected.id)) reactions[reactions.length - 1] = selected
  const geneMap = new Map(reactions.flatMap(r => r.genes.slice(0, 10).map(g => [g.id, g] as const)))
  const genes = [...geneMap.values()]
  counts.value = {reactions: reactions.length, genes: genes.length}
  const maxima = {
    task: Math.max(1e-9, Math.abs(props.data.task.predicted_delta ?? 0)),
    reaction: Math.max(1e-9, ...reactions.map(r => Math.abs(r.predicted_delta ?? 0))),
    gene: Math.max(1e-9, ...genes.map(g => Math.abs(g.predicted_delta ?? 0))),
  }
  const points = new Map<string, THREE.Vector3>()
  function node(id: string, label: string, value: number | null, kind: 'gene' | 'reaction' | 'task', position: THREE.Vector3) {
    const key = kind + ':' + id
    points.set(key, position)
    const neutral = new THREE.Color(cssVar('--scene-node-neutral', '#aab6b0'))
    const color = value === null ? neutral : neutral.clone().lerp(new THREE.Color(value > 0 ? cssVar('--delta-up', '#c47654') : cssVar('--primary', '#247a70')), Math.abs(value) / maxima[kind])
    const mesh = new THREE.Mesh(new THREE.SphereGeometry(kind === 'task' ? .26 : kind === 'reaction' ? .14 : .075, 18, 12), new THREE.MeshBasicMaterial({color}))
    mesh.position.copy(position)
    if (kind === 'reaction' && id === props.selectedReaction) mesh.scale.setScalar(1.4)
    mesh.userData = {id, label, value, kind}
    group.add(mesh); clickable.push(mesh)
  }
  node(props.data.task.id, props.data.task.label, props.data.task.predicted_delta, 'task', new THREE.Vector3(3.2, 0, 0))
  reactions.forEach((r, i) => node(r.id, r.label, r.predicted_delta, 'reaction', new THREE.Vector3(0, (i - (reactions.length - 1) / 2) * .62, Math.sin(i * 1.7) * .6)))
  genes.forEach((g,i) => node(g.id,g.label,g.predicted_delta,'gene',new THREE.Vector3(-3.2,(i % 12 - Math.min(11,genes.length-1)/2)*.38,(Math.floor(i/12)-(Math.ceil(genes.length/12)-1)/2)*.55)))
  function edge(a: string, b: string, highlighted: boolean) {
    const from = points.get(a), to = points.get(b)
    if (!from || !to) return
    const geometry = new THREE.BufferGeometry().setFromPoints([from,to])
    group.add(new THREE.Line(geometry,new THREE.LineBasicMaterial({color:highlighted ? cssVar('--primary', '#247a70') : cssVar('--scene-line-idle', '#a5b6ac'),transparent:true,opacity:highlighted ? .75 : .3})))
  }
  for (const r of reactions) {
    edge('reaction:'+r.id,'task:'+props.data.task.id,r.id === props.selectedReaction)
    for (const g of r.genes.slice(0,10)) edge('gene:'+g.id,'reaction:'+r.id,r.id === props.selectedReaction)
  }
  draw()
}
function pick(event: PointerEvent) {
  if (!renderer || Math.hypot(event.clientX-start.x,event.clientY-start.y)>5) return
  const bounds = renderer.domElement.getBoundingClientRect()
  pointer.set((event.clientX-bounds.left)/bounds.width*2-1,-(event.clientY-bounds.top)/bounds.height*2+1)
  raycaster.setFromCamera(pointer,camera)
  const hit = raycaster.intersectObjects(clickable)[0]
  if (!hit) return
  const node = hit.object.userData
  const unit = node.kind === 'gene' ? '表达变化' : node.kind === 'reaction' ? '反应分数变化' : '任务分数变化'
  description.value = node.label+' · '+unit+' '+fmtDelta(node.value)
  if (node.kind === 'reaction') emit('select',node.id)
}
function down(event: PointerEvent) { start = {x:event.clientX,y:event.clientY} }
function contextLost(event: Event) { event.preventDefault(); error.value='三维渲染不可用，仍可使用下方完整关联列表。' }
function reset() { camera.position.set(0, 1.4, 8.5); controls.target.set(0,0,0); controls.update(); draw() }
watch(() => [props.data,props.selectedReaction], build)
onMounted(() => {
  try {
    if (!host.value) return
    scene = new THREE.Scene(); scene.background = new THREE.Color(cssVar('--figure-soft-bg', '#f4f6f0'))
    camera = new THREE.PerspectiveCamera(43,1,.1,100)
    renderer = new THREE.WebGLRenderer({antialias:true})
    renderer.setPixelRatio(Math.min(window.devicePixelRatio,2))
    renderer.domElement.setAttribute('aria-label','任务、反应与基因的三维关联网络；同一数据可在下方列表操作')
    renderer.domElement.setAttribute('role','img')
    host.value.appendChild(renderer.domElement)
    controls = new OrbitControls(camera,renderer.domElement)
    controls.enableDamping = false; controls.minDistance = 6; controls.maxDistance = 20
    controls.addEventListener('change',draw)
    renderer.domElement.addEventListener('pointerdown',down)
    renderer.domElement.addEventListener('pointerup',pick)
    renderer.domElement.addEventListener('webglcontextlost',contextLost)
    resizeObserver = new ResizeObserver(() => {
      if (!host.value || !renderer) return
      const {width,height} = host.value.getBoundingClientRect()
      if (!width || !height) return
      renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix()
      if (group) group.scale.x=Math.min(2,Math.max(1,camera.aspect))
      draw()
    })
    resizeObserver.observe(host.value)
    themeObserver = new MutationObserver(() => {
      if (!scene) return
      scene.background = new THREE.Color(cssVar('--figure-soft-bg', '#f4f6f0'))
      build()
    })
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    reset();build();frame=requestAnimationFrame(draw)
  } catch { error.value = '当前设备不支持三维视图，请使用下方关联列表。' }
})
onBeforeUnmount(() => {
  disposed=true;cancelAnimationFrame(frame);resizeObserver?.disconnect();themeObserver?.disconnect();controls?.dispose()
  renderer?.domElement.removeEventListener('pointerdown',down)
  renderer?.domElement.removeEventListener('pointerup',pick)
  renderer?.domElement.removeEventListener('webglcontextlost',contextLost)
  clear();renderer?.dispose();renderer?.domElement.remove()
})
</script>
<template>
  <div class="spatial-trace">
    <div class="spatial-heading"><span>基因 → 反应 → 代谢任务</span><button class="btn btn-sm" @click="reset" :disabled="!!error">复位视角</button></div>
    <p v-if="error" class="notice notice-warn">{{ error }}</p>
    <div v-show="!error" ref="host" class="spatial-canvas"><span v-for="label in labels" :key="label.key" class="node-label" :class="label.kind" :style="{left:label.x+'px',top:label.y+'px'}">{{ label.text }}</span></div>
    <p class="spatial-description" aria-live="polite">{{ description }}</p>
    <p class="spatial-note">显示 {{ counts.reactions }} / {{ data.total_reactions }} 个关联反应、{{ counts.genes }} 个关联基因；每个反应最多展示 10 个基因。拖动旋转，滚轮缩放。空间位置为展示布局；橙色上升、绿色下降、灰色为零或缺失（点击区分），各类分数独立缩放。</p>
  </div>
</template>
<style scoped>
.spatial-trace{border:1px solid var(--border);margin:20px 0;background:var(--figure-soft-bg);min-width:0}.spatial-heading{display:flex;justify-content:space-between;align-items:center;padding:12px 18px;font-size:11px;color:var(--primary)}.spatial-canvas{height:350px;width:100%;overflow:hidden;position:relative}.spatial-canvas :deep(canvas){display:block;touch-action:none}.node-label{position:absolute;z-index:1;pointer-events:none;transform:translateX(-50%);font:10px Consolas,monospace;color:var(--ink);text-align:center;max-width:130px;line-height:1.4;background:color-mix(in srgb, var(--figure-soft-bg) 86%, transparent);padding:2px 4px}.node-label.task{font-family:var(--font);font-size:11px}.spatial-description{font-size:12px;padding:12px 18px;margin:0;border-top:1px solid var(--border);overflow-wrap:anywhere}.spatial-note{font-size:10px;color:var(--muted);padding:0 18px 14px;line-height:1.8;margin:0}@media(max-width:600px){.spatial-canvas{height:260px}}
</style>
