<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { createCellModel, type CellModel } from '../../scene/cellModel'
import { ORGANELLES, useSceneStore, type CameraPreset, type OrganelleId } from '../../stores/scene'

withDefaults(defineProps<{ presentation?: boolean }>(), { presentation: false })
const store = useSceneStore()
const viewport = ref<HTMLElement>()
const canvasHost = ref<HTMLElement>()
const fullscreen = ref(false)
const captureMessage = ref('')
const reducedMotion = ref(false)
const labels = ref<Record<OrganelleId, { x: number; y: number; visible: boolean }>>({
  membrane: { x: 0, y: 0, visible: false }, nucleus: { x: 0, y: 0, visible: false },
  mitochondria: { x: 0, y: 0, visible: false }, er: { x: 0, y: 0, visible: false }, golgi: { x: 0, y: 0, visible: false },
})
const axis = ref({ x: { x: 25, y: 0 }, y: { x: 0, y: -25 }, z: { x: -18, y: 18 } })
const available = computed(() => store.renderStatus === 'ready')
let renderer: THREE.WebGLRenderer | undefined
let scene: THREE.Scene | undefined
let camera: THREE.PerspectiveCamera | undefined
let controls: OrbitControls | undefined
let model: CellModel | undefined
let resizeObserver: ResizeObserver | undefined
let intersectionObserver: IntersectionObserver | undefined
let motionQuery: MediaQueryList | undefined
let frame = 0
let previousTime = 0
let width = 1
let height = 1
let inView = true
let disposed = false
let lost = false
let captureTimer: ReturnType<typeof setTimeout> | undefined
let activeBlobUrl: string | undefined
let transition: { start: number; from: THREE.Vector3; to: THREE.Vector3; fromTarget: THREE.Vector3; target: THREE.Vector3 } | undefined
const raycaster = new THREE.Raycaster()
const pointer = new THREE.Vector2()
const pointerStart = { x: 0, y: 0, time: 0 }
const projection = new THREE.Vector3()
const presets: Record<CameraPreset, { position: [number, number, number]; target: [number, number, number] }> = {
  overview: { position: [2.5, 1.6, 11.1], target: [0, 0, 0] },
  nucleus: { position: [0.3, 1.5, 6.2], target: [-0.58, 0.32, 0.2] },
  mitochondria: { position: [3.1, 1.65, 4.7], target: [2.18, 1.06, 0.58] },
}

function fail(message: string) {
  store.renderStatus = 'unavailable'
  store.errorMessage = message
  if (frame) cancelAnimationFrame(frame)
  frame = 0
}

function updateOverlay() {
  if (!camera || !model) return
  const next = { ...labels.value }
  for (const organelle of ORGANELLES) {
    projection.copy(model.anchors[organelle.id]).applyMatrix4(model.root.matrixWorld).project(camera)
    next[organelle.id] = {
      x: (projection.x * 0.5 + 0.5) * width,
      y: (-projection.y * 0.5 + 0.5) * height,
      visible: store.visible[organelle.id] && projection.z > -1 && projection.z < 1 && Math.abs(projection.x) < 0.94 && Math.abs(projection.y) < 0.88,
    }
  }
  labels.value = next
  const rotation = new THREE.Matrix4().extractRotation(camera.matrixWorldInverse)
  const projectedAxis = (v: THREE.Vector3) => {
    v.applyMatrix4(rotation)
    return { x: v.x * 26, y: -v.y * 26 }
  }
  axis.value = { x: projectedAxis(new THREE.Vector3(1, 0, 0)), y: projectedAxis(new THREE.Vector3(0, 1, 0)), z: projectedAxis(new THREE.Vector3(0, 0, 1)) }
}

function invalidate() {
  if (disposed || lost || !inView || document.hidden || frame || !renderer) return
  frame = requestAnimationFrame(renderFrame)
}

function renderFrame(time: number) {
  frame = 0
  if (disposed || lost || !inView || document.hidden || !renderer || !camera || !scene || !controls) return
  const delta = previousTime ? Math.min((time - previousTime) / 1000, 0.05) : 0
  previousTime = time
  const autoRotate = store.rotating && !reducedMotion.value
  controls.autoRotate = autoRotate
  let moving = false
  if (transition) {
    const progress = Math.min(1, (time - transition.start) / 850)
    const eased = progress * progress * (3 - 2 * progress)
    camera.position.lerpVectors(transition.from, transition.to, eased)
    controls.target.lerpVectors(transition.fromTarget, transition.target, eased)
    if (progress >= 1) transition = undefined
    else moving = true
  }
  const changed = controls.update(delta)
  try {
    renderer.render(scene, camera)
    if (renderer.getContext().isContextLost()) return
    if (store.renderStatus !== 'ready') {
      store.renderStatus = 'ready'
      store.errorMessage = ''
    }
    updateOverlay()
  } catch (error) {
    fail(error instanceof Error ? `3D 渲染失败：${error.message}` : '3D 渲染失败，已切换为二维结构示意。')
    return
  }
  if (moving || changed || autoRotate) invalidate()
}

function applySceneState() {
  if (!model) return
  for (const organelle of ORGANELLES) model.groups[organelle.id].visible = store.visible[organelle.id]
  model.membrane.opacity = Math.max(0.05, Math.min(0.9, store.membraneOpacity))
  model.setCut(store.cutaway, store.cutPosition)
  model.select(store.selected)
  invalidate()
}

function moveCamera(preset: CameraPreset) {
  if (!camera || !controls) return
  const data = presets[preset]
  const position = new THREE.Vector3(...data.position)
  const target = new THREE.Vector3(...data.target)
  if (reducedMotion.value) {
    camera.position.copy(position)
    controls.target.copy(target)
    transition = undefined
  } else {
    transition = { start: performance.now(), from: camera.position.clone(), to: position, fromTarget: controls.target.clone(), target }
  }
  invalidate()
}

function onResize() {
  if (!canvasHost.value || !renderer || !camera) return
  const rect = canvasHost.value.getBoundingClientRect()
  width = Math.max(1, rect.width)
  height = Math.max(1, rect.height)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  renderer.setSize(width, height)
  camera.aspect = width / height
  // Preserve the overview's horizontal field of view in tall/narrow columns.
  camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(19)) / Math.min(1, camera.aspect)))
  camera.updateProjectionMatrix()
  invalidate()
}

function onPointerDown(event: PointerEvent) {
  pointerStart.x = event.clientX
  pointerStart.y = event.clientY
  pointerStart.time = performance.now()
  transition = undefined
}

function onPointerUp(event: PointerEvent) {
  if (!camera || !model || !renderer || event.button !== 0 || performance.now() - pointerStart.time > 550) return
  if (Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 5) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1)
  raycaster.setFromCamera(pointer, camera)
  // Prefer exposed interior structures to the transparent enclosing membrane.
  const internal = ORGANELLES.filter(item => item.id !== 'membrane' && store.visible[item.id]).map(item => model!.groups[item.id])
  const hits = raycaster.intersectObjects(internal, true)
  const id = hits[0]?.object.userData.organelle as OrganelleId | undefined
  if (id) store.select(id)
  else if (store.visible.membrane) {
    const membraneHits = raycaster.intersectObject(model.groups.membrane, true)
    const hit = membraneHits.find(item => !store.cutaway || model!.cutPlane.distanceToPoint(item.point) >= 0)
    if (hit) store.select('membrane')
  }
}

function onContextLost(event: Event) {
  event.preventDefault()
  lost = true
  fail('WebGL 上下文已中断，当前显示二维结构示意；恢复后将重新渲染。')
}

function onContextRestored() {
  lost = false
  store.renderStatus = 'initializing'
  store.errorMessage = ''
  previousTime = 0
  invalidate()
}

function onVisibilityChange() {
  previousTime = 0
  if (document.hidden && frame) {
    cancelAnimationFrame(frame)
    frame = 0
  } else invalidate()
}

function onMotionChange() {
  reducedMotion.value = motionQuery?.matches ?? false
  if (controls) controls.enableDamping = !reducedMotion.value
  if (reducedMotion.value && transition && camera && controls) {
    camera.position.copy(transition.to)
    controls.target.copy(transition.target)
    transition = undefined
  }
  invalidate()
}

function onFullscreenChange() {
  fullscreen.value = document.fullscreenElement === viewport.value
  onResize()
}

async function toggleFullscreen() {
  if (!viewport.value) return
  try {
    if (document.fullscreenElement === viewport.value) await document.exitFullscreen()
    else await viewport.value.requestFullscreen()
  } catch {
    captureMessage.value = '当前浏览器不支持全屏显示。'
  }
}

function captureScreenshot() {
  if (!renderer || !scene || !camera || !available.value) return
  try {
    // Capture freshly rendered geometry, independent of the surrounding DOM overlays.
    renderer.render(scene, camera)
    renderer.domElement.toBlob(blob => {
      if (disposed) return
      if (!blob) { captureMessage.value = '截图生成失败，请重试。'; return }
      if (activeBlobUrl) URL.revokeObjectURL(activeBlobUrl)
      activeBlobUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = activeBlobUrl
      link.download = `CellLens-结构示意-非实测形态-${new Date().toISOString().slice(0, 10)}.png`
      link.click()
      captureMessage.value = '已导出当前三维画面（结构示意）。'
      if (captureTimer) clearTimeout(captureTimer)
      captureTimer = setTimeout(() => {
        captureMessage.value = ''
        if (activeBlobUrl) URL.revokeObjectURL(activeBlobUrl)
        activeBlobUrl = undefined
      }, 4000)
    }, 'image/png')
  } catch { captureMessage.value = '当前画面无法导出，请重试。' }
}

watch(() => [store.selected, store.membraneOpacity, store.cutaway, store.cutPosition, ...Object.values(store.visible)], applySceneState)
watch(() => store.cameraPreset, moveCamera)
watch(() => store.resetToken, () => moveCamera('overview'))
watch(() => [store.labels, store.rotating], invalidate)

onMounted(() => {
  if (!canvasHost.value) return
  store.renderStatus = 'initializing'
  store.errorMessage = ''
  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  reducedMotion.value = motionQuery.matches
  motionQuery.addEventListener('change', onMotionChange)
  document.addEventListener('visibilitychange', onVisibilityChange)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  try {
    // On-demand rendering keeps idle GPU use low; preserve its last frame for browser captures.
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'default' })
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.22
    renderer.localClippingEnabled = true
    renderer.setClearColor('#132024')
    renderer.domElement.setAttribute('aria-label', '可交互的细胞结构三维示意，拖动旋转、滚轮缩放。可用标签按钮选择细胞器。')
    renderer.domElement.setAttribute('role', 'img')
    canvasHost.value.appendChild(renderer.domElement)
    scene = new THREE.Scene()
    scene.background = new THREE.Color('#132024')
    scene.add(new THREE.HemisphereLight('#e0ece7', '#28303c', 2.15))
    const key = new THREE.DirectionalLight('#f3e2cf', 3.1)
    key.position.set(-3, 6, 7)
    scene.add(key)
    const fill = new THREE.DirectionalLight('#b1d4e4', 1.65)
    fill.position.set(5, 2, -4)
    scene.add(fill)
    const rim = new THREE.DirectionalLight('#a6c8bf', 1.6)
    rim.position.set(-5, -1, -2)
    scene.add(rim)
    const grid = new THREE.GridHelper(24, 36, '#34504e', '#233737')
    grid.position.y = -3.25
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material]
    for (const material of gridMaterials) { material.transparent = true; material.opacity = 0.32; material.depthWrite = false }
    scene.add(grid)
    model = createCellModel()
    scene.add(model.root)
    camera = new THREE.PerspectiveCamera(38, 1, 0.1, 60)
    camera.position.set(...presets[store.cameraPreset].position)
    controls = new OrbitControls(camera, renderer.domElement)
    controls.target.set(...presets[store.cameraPreset].target)
    controls.enableDamping = !reducedMotion.value
    controls.dampingFactor = 0.08
    controls.minDistance = 3.1
    controls.maxDistance = 18
    controls.enablePan = true
    controls.autoRotateSpeed = 0.55
    controls.addEventListener('change', invalidate)
    controls.addEventListener('start', () => { transition = undefined })
    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)
    renderer.domElement.addEventListener('webglcontextlost', onContextLost)
    renderer.domElement.addEventListener('webglcontextrestored', onContextRestored)
    resizeObserver = new ResizeObserver(onResize)
    resizeObserver.observe(canvasHost.value)
    intersectionObserver = new IntersectionObserver(entries => {
      inView = entries[0]?.isIntersecting ?? true
      previousTime = 0
      if (!inView && frame) { cancelAnimationFrame(frame); frame = 0 }
      else invalidate()
    })
    intersectionObserver.observe(canvasHost.value)
    onResize()
    applySceneState()
    invalidate()
  } catch (error) {
    fail(error instanceof Error ? `浏览器无法启动 WebGL 2：${error.message}` : '浏览器无法启动 WebGL 2，当前显示二维结构示意。')
  }
})

onBeforeUnmount(() => {
  disposed = true
  if (frame) cancelAnimationFrame(frame)
  if (captureTimer) clearTimeout(captureTimer)
  if (activeBlobUrl) URL.revokeObjectURL(activeBlobUrl)
  resizeObserver?.disconnect()
  intersectionObserver?.disconnect()
  motionQuery?.removeEventListener('change', onMotionChange)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  controls?.removeEventListener('change', invalidate)
  controls?.dispose()
  if (renderer) {
    renderer.domElement.removeEventListener('pointerdown', onPointerDown)
    renderer.domElement.removeEventListener('pointerup', onPointerUp)
    renderer.domElement.removeEventListener('webglcontextlost', onContextLost)
    renderer.domElement.removeEventListener('webglcontextrestored', onContextRestored)
  }
  model?.dispose()
  scene?.traverse(object => {
    if (object instanceof THREE.LineSegments) {
      object.geometry.dispose()
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) material.dispose()
    }
  })
  scene?.clear()
  renderer?.dispose()
  renderer?.forceContextLoss()
  renderer?.domElement.remove()
})

defineExpose({ captureScreenshot })
</script>

<template>
  <section ref="viewport" class="cell-viewport" :class="{ 'cell-viewport--presentation': presentation }" aria-label="细胞结构视口">
    <div ref="canvasHost" class="cell-viewport__canvas" :class="{ 'is-unavailable': store.renderStatus === 'unavailable' }" />
    <div class="viewport-toolbar">
      <div class="viewport-title"><span class="viewport-cube">⬡</span><span>细胞结构</span><span class="viewport-live" :class="{ ready: available }">{{ available ? '3D' : store.renderStatus === 'initializing' ? '加载中' : '2D 示意' }}</span></div>
      <div class="viewport-actions" aria-label="视口控制">
        <button type="button" :aria-pressed="store.rotating" :disabled="!available || reducedMotion" :title="reducedMotion ? '已遵循系统减少动态效果设置' : '自动旋转'" @click="store.rotating = !store.rotating"><span aria-hidden="true">↻</span><span class="control-label">旋转</span></button>
        <button type="button" :aria-pressed="store.cutaway" :disabled="!available" title="膜壳剖切" @click="store.cutaway = !store.cutaway"><span aria-hidden="true">◩</span><span class="control-label">剖切</span></button>
        <button type="button" :aria-pressed="store.labels" title="结构标签" @click="store.labels = !store.labels"><span aria-hidden="true">⌖</span><span class="control-label">标签</span></button>
        <button type="button" title="重置视角与剖切" :disabled="!available" @click="store.reset()"><span aria-hidden="true">⟲</span><span class="control-label">重置</span></button>
        <button type="button" title="下载当前三维画面" aria-label="下载当前三维画面" :disabled="!available" @click="captureScreenshot"><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M3 6h3l1-2h6l1 2h3v10H3Z"/><circle cx="10" cy="11" r="3"/></svg></button>
        <button type="button" :title="fullscreen ? '退出全屏' : '全屏显示'" :aria-label="fullscreen ? '退出全屏' : '全屏显示'" :aria-pressed="fullscreen" @click="toggleFullscreen"><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M3 7V3h4m6 0h4v4M3 13v4h4m6 0h4v-4"/></svg></button>
      </div>
    </div>
    <div v-if="store.renderStatus === 'initializing'" class="viewport-loading" role="status"><span class="loading-orbit" />正在构建细胞结构…</div>
    <div v-if="store.renderStatus === 'unavailable'" class="viewport-fallback">
      <svg viewBox="0 0 640 460" role="img" aria-label="二维细胞结构示意，当前浏览器未渲染三维模型">
        <ellipse v-if="store.visible.membrane" cx="320" cy="230" rx="230" ry="176" fill="#87b5aa" fill-opacity=".08" stroke="#87b5aa" stroke-width="4"/>
        <g v-if="store.visible.er" fill="none" stroke="#62899e" stroke-width="10"><path d="M195 144C110 226 160 342 296 345M185 165C129 238 181 320 282 323M208 132C327 72 405 168 374 270M224 110C355 65 427 163 399 289"/></g>
        <g v-if="store.visible.nucleus"><circle cx="268" cy="211" r="76" fill="#9d8caf" fill-opacity=".65" stroke="#c1b6d1" stroke-width="2"/><circle cx="253" cy="225" r="22" fill="#756c91"/></g>
        <g v-if="store.visible.mitochondria" fill="#bb955c" fill-opacity=".3" stroke="#d8b573" stroke-width="3"><ellipse cx="438" cy="174" rx="54" ry="24" transform="rotate(-40 438 174)"/><path d="M407 191l6-22 13 12 5-26 12 13 5-22 13 11"/><ellipse cx="201" cy="327" rx="47" ry="21" transform="rotate(22 201 327)"/><path d="M167 317l9 20 8-15 10 20 8-15 10 18 9-14"/></g>
        <g v-if="store.visible.golgi" fill="none" stroke="#c8957b" stroke-width="8"><path d="M363 285q45 36 95-8M359 301q49 36 104-8M358 318q49 36 108-7M364 334q47 34 99-5"/></g>
      </svg>
      <p><strong>二维结构示意</strong><span>{{ store.errorMessage }}</span></p>
      <div class="fallback-options"><button v-for="item in ORGANELLES" :key="item.id" type="button" :aria-pressed="store.selected === item.id" @click="store.select(item.id)"><i :style="{ background: item.color }"/>{{ item.name }}</button></div>
    </div>
    <div v-if="available && store.labels" class="organelle-labels" aria-label="选择细胞器">
      <button v-for="item in ORGANELLES" v-show="labels[item.id].visible" :key="item.id" type="button" class="organelle-label" :class="{ selected: store.selected === item.id }" :style="{ left: `${labels[item.id].x}px`, top: `${labels[item.id].y}px`, '--organelle-color': item.color }" :aria-pressed="store.selected === item.id" @click="store.select(item.id)"><span class="label-leader"/><i/>{{ item.name }}</button>
    </div>
    <div class="viewport-footer"><span class="schematic-tag">结构示意 · 非实测形态</span><span v-if="available" class="orbit-help">拖动旋转 · 滚轮缩放 · 点击选择</span></div>
    <svg v-if="available" class="viewport-axis" viewBox="0 0 88 88" aria-label="三维坐标方向"><circle cx="44" cy="44" r="2" fill="#78908e"/><g v-for="(value, name) in axis" :key="name" :stroke="name === 'x' ? '#bc8575' : name === 'y' ? '#80b09c' : '#88a5c2'"><line x1="44" y1="44" :x2="44 + value.x" :y2="44 + value.y" stroke-width="1.5"/><text :x="44 + value.x * 1.28" :y="48 + value.y * 1.28" stroke="none" :fill="name === 'x' ? '#bc8575' : name === 'y' ? '#80b09c' : '#88a5c2'">{{ name.toUpperCase() }}</text></g></svg>
    <p v-if="captureMessage" class="viewport-message" role="status">{{ captureMessage }}</p>
  </section>
</template>

<style scoped>
.cell-viewport { position: relative; width: 100%; height: auto; min-height: 480px; overflow: hidden; background: #132024; border: 1px solid #263c3e; border-radius: 7px; color: #dce7e3; isolation: isolate; }
.cell-viewport:fullscreen { width: 100vw; height: 100vh; border: 0; border-radius: 0; }
.cell-viewport__canvas { position: absolute; inset: 0; }
.cell-viewport__canvas :deep(canvas) { display: block; width: 100%; height: 100%; touch-action: none; }
.cell-viewport__canvas.is-unavailable { visibility: hidden; }
.viewport-toolbar { position: absolute; z-index: 3; top: 0; left: 0; right: 0; display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 55px; margin: 0 17px; border-bottom: 1px solid #a2b8b31a; background: linear-gradient(#132024ea, #132024b5); }
.viewport-title { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.viewport-cube { font-size: 22px; color: #a3c4b9; }
.viewport-live { font: 9px 'Consolas', monospace; letter-spacing: .05em; color: #8a9f9e; border: 1px solid #526762; border-radius: 3px; padding: 2px 4px; }
.viewport-live.ready { color: #a1cabe; border-color: #6d968655; }
.viewport-actions { display: flex; align-items: center; gap: 2px; }
.viewport-actions button { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 8px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: #b4c5c1; cursor: pointer; font-size: 11px; white-space: nowrap; }
.viewport-actions button > span:first-child { font-size: 17px; line-height: 1; }
.viewport-actions button:hover { background: #b5d2c812; color: #e1ede8; }
.viewport-actions button[aria-pressed='true'] { border-color: #87b5aa44; background: #87b5aa13; color: #c7e0d5; }
.viewport-actions button:disabled { opacity: .35; cursor: default; }
.viewport-actions svg { fill: none; stroke: currentColor; stroke-width: 1.3; }
.viewport-actions button:focus-visible, .organelle-label:focus-visible, .fallback-options button:focus-visible { outline: 2px solid #afd2c4; outline-offset: 3px; }
.viewport-footer { position: absolute; left: 17px; right: 90px; bottom: 17px; z-index: 2; display: flex; align-items: center; justify-content: space-between; gap: 12px; pointer-events: none; }
.schematic-tag { padding: 6px 9px; border: 1px solid #abc7bc36; border-radius: 4px; font-size: 10px; color: #bfd1c9; background: #132024aa; }
.orbit-help { font-size: 10px; color: #93aaa3; }
.organelle-labels { position: absolute; inset: 0; z-index: 2; pointer-events: none; }
.organelle-label { position: absolute; display: inline-flex; align-items: center; gap: 6px; transform: translate(12px, -50%); padding: 6px 9px; border: 1px solid #8baca547; border-radius: 3px; background: #132024d6; color: #c2d0cb; font-size: 11px; cursor: pointer; white-space: nowrap; pointer-events: auto; box-shadow: 0 3px 18px #08121430; }
.organelle-label i, .fallback-options i { display: inline-block; flex: 0 0 auto; width: 5px; height: 5px; border-radius: 50%; background: var(--organelle-color); }
.organelle-label.selected { color: #fff0d6; border-color: var(--organelle-color); background: #302c23e6; }
.label-leader { position: absolute; width: 19px; height: 1px; left: -19px; top: 50%; background: var(--organelle-color); opacity: .85; }
.label-leader::before { position: absolute; left: -2px; top: -2px; width: 4px; height: 4px; border: 1px solid var(--organelle-color); border-radius: 50%; content: ''; }
.viewport-axis { position: absolute; right: 12px; bottom: 9px; width: 74px; height: 74px; pointer-events: none; }
.viewport-axis text { font: 10px 'Consolas', monospace; text-anchor: middle; }
.viewport-message { position: absolute; left: 50%; bottom: 65px; z-index: 5; max-width: 90%; transform: translateX(-50%); margin: 0; padding: 10px 14px; border: 1px solid #abc7bc36; border-radius: 4px; background: #172b2df5; font-size: 12px; color: #d4e6de; }
.viewport-loading { position: absolute; inset: 60px 0 50px; display: flex; align-items: center; justify-content: center; gap: 12px; color: #a8c0b8; font-size: 12px; pointer-events: none; }
.loading-orbit { width: 20px; height: 20px; border: 1px solid #668e8055; border-top-color: #afd2c4; border-radius: 50%; animation: orbit-spin 1.4s linear infinite; }
.viewport-fallback { position: absolute; inset: 58px 0 58px; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 12px 25px; }
.viewport-fallback > svg { width: 100%; max-width: 560px; min-height: 0; flex: 1 1 auto; }
.viewport-fallback p { max-width: 500px; margin: 4px 0 12px; text-align: center; font-size: 11px; color: #8fa9a0; }
.viewport-fallback strong { display: block; margin-bottom: 5px; font-weight: 500; color: #c5d9d0; }
.fallback-options { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; }
.fallback-options button { display: flex; align-items: center; gap: 6px; border: 1px solid #4f69614d; border-radius: 3px; background: #20322c; color: #c0d0c8; padding: 5px 8px; font-size: 10px; cursor: pointer; }
.fallback-options button[aria-pressed='true'] { border-color: #abc7bc; }
.cell-viewport--presentation { min-height: 600px; }
@keyframes orbit-spin { to { transform: rotate(360deg); } }
@media (max-width: 720px) { .cell-viewport { min-height: 420px; } .viewport-toolbar { margin: 0 11px; gap: 6px; } .control-label, .orbit-help { display: none; } .viewport-actions button { padding: 0 6px; } .viewport-title { font-size: 11px; gap: 5px; } .organelle-label { font-size: 10px; padding: 5px 6px; } .viewport-footer { left: 11px; bottom: 14px; } }
@media (prefers-reduced-motion: reduce) { .loading-orbit { animation: none; } }
</style>
