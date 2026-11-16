<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { CellRegionKey, CellSceneController } from '../lib/cellScene'
import UiIcon from './UiIcon.vue'

const props = withDefaults(defineProps<{
  selected?: CellRegionKey | null
  interactive?: boolean
  compact?: boolean
  showControls?: boolean
}>(), { selected: null, interactive: true, compact: false, showControls: true })
const emit = defineEmits<{ select: [key: CellRegionKey] }>()
const regions: { key: CellRegionKey; label: string; english: string }[] = [
  { key: 'nucleus', label: '细胞核', english: 'NUCLEUS' },
  { key: 'mitochondria', label: '线粒体', english: 'MITOCHONDRIA' },
  { key: 'er', label: '内质网', english: 'ENDOPLASMIC RETICULUM' },
  { key: 'golgi', label: '高尔基体', english: 'GOLGI APPARATUS' },
  { key: 'membrane', label: '细胞膜', english: 'CELL MEMBRANE' },
  { key: 'cytoplasm', label: '细胞质', english: 'CYTOPLASM' },
]
const canvasHost = ref<HTMLElement | null>(null)
const selected = ref<CellRegionKey | null>(props.selected)
const mode = ref<'3d' | '2d'>('3d')
const unavailable = ref(false)
const loading = ref(true)
const moving = ref(false)
const zoom = ref(1)
const uid = useId().replace(/:/g, '')
const selectedRegion = computed(() => regions.find(region => region.key === selected.value))
let scene: CellSceneController | null = null
let alive = true
let generation = 0
let reducedMotion: MediaQueryList | null = null
function updateReducedMotion(event: MediaQueryListEvent) {
  if (event.matches) { moving.value = false; scene?.setMotion(false) }
}

function selectRegion(key: CellRegionKey) {
  if (!props.interactive) return
  selected.value = key
  scene?.select(key)
  emit('select', key)
}
async function mountScene() {
  const attempt = ++generation
  scene?.dispose()
  scene = null
  if (mode.value !== '3d') { loading.value = false; return }
  loading.value = true
  await nextTick()
  try {
    const { mountCellScene } = await import('../lib/cellScene')
    if (!alive || attempt !== generation || mode.value !== '3d' || !canvasHost.value) return
    scene = mountCellScene(canvasHost.value, {
      compact: props.compact,
      interactive: props.interactive,
      onSelect: selectRegion,
      onUnavailable: () => { unavailable.value = true; mode.value = '2d' },
      onZoomChange: value => { zoom.value = value },
    })
    if (!scene) { unavailable.value = true; mode.value = '2d'; return }
    scene.setMotion(moving.value)
    scene.setZoom(zoom.value)
    scene.select(selected.value)
  } catch {
    if (alive && attempt === generation) { unavailable.value = true; mode.value = '2d' }
  } finally {
    if (alive && attempt === generation) loading.value = false
  }
}
function toggleMotion() {
  if (scene) moving.value = scene.toggleMotion()
}
function reset() { scene?.reset(); scene?.select(selected.value) }
function changeZoom(factor: number) { if (scene) zoom.value = scene.setZoom(zoom.value * factor) }
watch(() => props.selected, value => { selected.value = value; scene?.select(value) })
watch(mode, mountScene)
onMounted(() => {
  reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
  moving.value = !reducedMotion.matches
  reducedMotion.addEventListener('change', updateReducedMotion)
  void mountScene()
})
onBeforeUnmount(() => { alive = false; generation++; reducedMotion?.removeEventListener('change', updateReducedMotion); scene?.dispose() })
</script>

<template>
  <div class="cl-cell-scene" :class="{ 'is-compact': compact, 'is-2d': mode === '2d' }">
    <div class="cl-scene-overline"><span>CELLULAR LANDSCAPE</span><span>{{ mode === '3d' ? '3D' : '2D' }} / STRUCTURE EXPLORER</span></div>
    <div v-if="mode === '3d'" ref="canvasHost" class="cl-canvas-host" />
    <svg v-else class="cl-cell-map" viewBox="0 0 620 430" role="img" aria-label="细胞结构二维示意。通过下方分区按钮选择相同细胞器。">
      <defs>
        <radialGradient :id="`${uid}-shell`"><stop stop-color="#80bfa0" stop-opacity=".05"/><stop offset=".8" stop-color="#75c9a4" stop-opacity=".2"/><stop offset="1" stop-color="#b1e8c5" stop-opacity=".6"/></radialGradient>
        <radialGradient :id="`${uid}-nucleus`"><stop stop-color="#7bbca5"/><stop offset="1" stop-color="#27796d"/></radialGradient>
      </defs>
      <ellipse cx="310" cy="218" rx="277" ry="178" fill="none" stroke="#8bbba0" stroke-opacity=".3" stroke-dasharray="2 6"/>
      <path :class="{ selected: selected === 'membrane' }" class="cl-map-part" d="M89 223C67 113 170 50 318 62S567 144 548 248S407 384 265 365S105 315 89 223Z" :fill="`url(#${uid}-shell)`" stroke="#a2e0b4" stroke-width="3" @click="selectRegion('membrane')"/>
      <g class="cl-map-part" :class="{ selected: selected === 'cytoplasm' }" fill="#b3d0a9" @click="selectRegion('cytoplasm')"><circle v-for="i in 23" :key="i" :cx="128 + ((i * 73) % 355)" :cy="105 + ((i * 53) % 207)" r="3" opacity=".75"/></g>
      <g class="cl-map-part" :class="{ selected: selected === 'er' }" fill="none" stroke="#82ba9a" stroke-width="9" opacity=".8" @click="selectRegion('er')"><path d="M291 126Q419 91 438 224"/><path d="M291 141Q403 112 422 224"/><path d="M291 156Q389 130 406 223"/><path d="M291 172Q375 150 391 222"/></g>
      <g class="cl-map-part" :class="{ selected: selected === 'nucleus' }" @click="selectRegion('nucleus')"><ellipse cx="276" cy="213" rx="83" ry="76" :fill="`url(#${uid}-nucleus)`" stroke="#9ed7b7" stroke-width="3"/><ellipse cx="263" cy="199" rx="22" ry="18" fill="#c9dba5"/><path d="M220 239Q265 260 312 226M222 173Q270 153 319 189" stroke="#b8d9bc" stroke-width="2" fill="none" opacity=".55"/></g>
      <g class="cl-map-part" :class="{ selected: selected === 'mitochondria' }" fill="#c69d5d" stroke="#ecd09a" stroke-width="2" @click="selectRegion('mitochondria')"><ellipse cx="438" cy="269" rx="47" ry="18" transform="rotate(-25 438 269)"/><ellipse cx="165" cy="160" rx="42" ry="18" transform="rotate(40 165 160)"/><ellipse cx="185" cy="297" rx="43" ry="18" transform="rotate(-30 185 297)"/><path d="m405 285 9-19 11 16 8-25 13 14 7-18M144 143l14-1-2 18 17-3-2 18M154 311l10-18 13 11 8-20 14 6" fill="none" stroke-width="2.5"/></g>
      <g class="cl-map-part" :class="{ selected: selected === 'golgi' }" fill="none" stroke="#c5a088" stroke-width="7" stroke-linecap="round" @click="selectRegion('golgi')"><path d="M302 305Q340 289 365 303M307 318Q340 302 362 315M312 331Q340 316 359 328"/></g>
    </svg>
    <div v-if="loading" class="cl-scene-loading" role="status">正在载入结构示意…</div>
    <div v-if="selectedRegion" class="cl-scene-selection" aria-live="polite"><span>{{ selectedRegion.english }}</span><strong>{{ selectedRegion.label }}</strong></div>
    <div v-if="showControls" class="cl-scene-controls">
      <button v-if="mode === '3d'" type="button" class="cl-scene-control" aria-label="缩小细胞结构" title="缩小结构（最小 65%）" :disabled="zoom <= .65" @click="changeZoom(1 / 1.15)">−</button>
      <button v-if="mode === '3d'" type="button" class="cl-scene-control" aria-label="放大细胞结构" title="放大结构（最大 160%）" :disabled="zoom >= 1.6" @click="changeZoom(1.15)">+</button>
      <button v-if="mode === '3d'" type="button" class="cl-scene-control" :aria-label="moving ? '暂停结构动画' : '继续结构动画'" :title="moving ? '暂停结构动画' : '继续结构动画'" @click="toggleMotion"><UiIcon :name="moving ? 'pause' : 'play'" :size="14" /></button>
      <button v-if="mode === '3d'" type="button" class="cl-scene-control" aria-label="重置细胞视角" title="重置细胞视角" @click="reset"><UiIcon name="reset" :size="14" /></button>
      <button type="button" class="cl-scene-control cl-mode-control" :disabled="unavailable" @click="mode = mode === '3d' ? '2d' : '3d'">{{ mode === '3d' ? '二维视图' : unavailable ? '二维备用视图' : '三维视图' }}</button>
    </div>
    <div class="cl-scene-disclaimer">结构示意 · 非实测形态<span v-if="mode === '3d' && interactive"> · {{ Math.round(zoom * 100) }}%</span></div>
    <div v-if="interactive" class="cl-region-list" aria-label="细胞结构分区，可使用键盘选择"><button v-for="region in regions" :key="region.key" type="button" :aria-pressed="selected === region.key" :class="{ active: selected === region.key }" @click="selectRegion(region.key)">{{ region.label }}</button></div>
  </div>
</template>

<style scoped>
.cl-cell-scene{position:relative;height:100%;min-height:340px;isolation:isolate;color:#d9e9d8;overflow:hidden;background:radial-gradient(ellipse at 50% 48%,#78ad7040,transparent 65%)}
.cl-canvas-host,.cl-cell-map{position:absolute;inset:22px 0 56px;width:100%;height:calc(100% - 78px)}.cl-cell-map{padding:10px}.cl-scene-overline{position:absolute;top:22px;right:25px;z-index:1;font:9px/1.8 Bahnschrift,'Segoe UI',sans-serif;letter-spacing:1.4px;text-align:right;color:#a9c7ad;pointer-events:none}.cl-scene-overline span{display:block}.cl-scene-selection{position:absolute;top:28px;left:25px;pointer-events:none}.cl-scene-selection span{display:block;font:8px Bahnschrift,sans-serif;letter-spacing:1px;color:#a9c7ad;max-width:155px}.cl-scene-selection strong{display:block;margin-top:8px;font-size:14px;font-weight:500}.cl-scene-controls{position:absolute;left:20px;bottom:52px;display:flex;gap:6px}.cl-scene-control{display:inline-flex;align-items:center;justify-content:center;background:#123c2bd9;border:1px solid #b4d1b433;border-radius:6px;color:#d7e6cc;padding:6px;min-width:27px;min-height:27px;cursor:pointer}.cl-scene-control:hover{background:#316545}.cl-mode-control{font-size:10px;padding:5px 9px}.cl-scene-disclaimer{position:absolute;right:20px;bottom:59px;font-size:9px;color:#c4d6bb;background:#1a3d2eaa;border-radius:4px;padding:4px 6px;pointer-events:none}.cl-region-list{position:absolute;bottom:13px;left:20px;right:20px;display:flex;justify-content:center;gap:5px;flex-wrap:wrap}.cl-region-list button{font-size:10px;color:#c1d2bc;background:#143b2a80;border:1px solid #9fb99d36;border-radius:20px;padding:5px 10px;cursor:pointer}.cl-region-list button.active,.cl-region-list button:hover{color:#173f2b;background:#d9e5bd;border-color:#d9e5bd}.cl-scene-loading{position:absolute;inset:0;display:grid;place-items:center;font-size:12px;color:#b6ceb1;background:#193f32c0}.cl-map-part{cursor:pointer;transition:filter .2s}.cl-map-part.selected{filter:drop-shadow(0 0 7px #ecdfa0)}.cl-scene-control:focus-visible,.cl-region-list button:focus-visible{outline:2px solid #e5ca83;outline-offset:3px}.is-compact{min-height:300px}.is-compact .cl-scene-overline{font-size:8px}.is-compact .cl-scene-selection{top:25px;left:18px}.is-compact .cl-region-list{left:10px;right:10px;gap:4px}.is-compact .cl-region-list button{padding:4px 7px;font-size:9px}@media(max-width:500px){.cl-scene-disclaimer{bottom:88px;right:12px}.cl-scene-controls{bottom:48px}.cl-region-list{bottom:9px;left:8px;right:8px}.cl-region-list button{padding:4px 7px}.cl-scene-selection{top:22px;left:17px}.cl-scene-overline{right:17px;font-size:8px}.cl-cell-scene{min-height:320px}}
.cl-scene-control:disabled{opacity:.45;cursor:default}.cl-scene-controls{bottom:61px}.cl-scene-disclaimer{bottom:99px;font-size:11px}.cl-region-list button,.is-compact .cl-region-list button{font-size:11px;padding:5px 8px}.cl-scene-selection span{font-size:10px}.cl-scene-overline{font-size:10px}.cl-canvas-host{bottom:100px;height:calc(100% - 122px)}@media(max-width:500px){.cl-scene-controls{bottom:79px;left:12px}.cl-scene-disclaimer{bottom:117px;left:12px;right:auto}.cl-region-list{bottom:10px}.cl-scene-overline{top:14px;right:12px;max-width:45%;font-size:8px}.cl-scene-selection{top:18px;left:12px;max-width:42%}.cl-scene-selection span{font-size:9px}}
</style>
