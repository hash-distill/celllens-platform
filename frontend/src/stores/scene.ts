import { defineStore } from 'pinia'

export type OrganelleId = 'membrane' | 'nucleus' | 'mitochondria' | 'er' | 'golgi'
export type CameraPreset = 'overview' | 'nucleus' | 'mitochondria'
export const ORGANELLES: { id: OrganelleId; name: string; english: string; color: string; description: string }[] = [
  { id: 'membrane', name: '细胞膜', english: 'Plasma membrane', color: '#91b9b1', description: '包围细胞的膜结构。此处展示形态示意，不提供实测厚度或通透性。' },
  { id: 'nucleus', name: '细胞核', english: 'Nucleus', color: '#9d90b2', description: '容纳遗传物质的细胞区室。核与核仁的形态仅用于结构展示。' },
  { id: 'mitochondria', name: '线粒体', english: 'Mitochondria', color: '#c6a26a', description: '内膜折叠形成嵴的细胞器。模型展示结构，表达结果不等同于实测代谢通量。' },
  { id: 'er', name: '内质网', english: 'Endoplasmic reticulum', color: '#6c91a2', description: '位于细胞质中的膜性结构。与核周结构相邻，不由扰动预测改变形态。' },
  { id: 'golgi', name: '高尔基体', english: 'Golgi apparatus', color: '#ba907b', description: '由堆叠膜囊组成的细胞器。此模型的数量和位置均为示意。' },
]

export const useSceneStore = defineStore('cell-scene', {
  state: () => ({
    selected: 'mitochondria' as OrganelleId,
    visible: { membrane: true, nucleus: true, mitochondria: true, er: true, golgi: true } as Record<OrganelleId, boolean>,
    membraneOpacity: 0.32,
    cutaway: true,
    cutPosition: 0.65,
    labels: true,
    rotating: false,
    cameraPreset: 'overview' as CameraPreset,
    resetToken: 0,
    renderStatus: 'initializing' as 'initializing' | 'ready' | 'unavailable',
    errorMessage: '',
  }),
  getters: {
    selectedMeta(state) { return ORGANELLES.find(item => item.id === state.selected)! },
  },
  actions: {
    select(id: OrganelleId) { this.selected = id },
    toggleVisible(id: OrganelleId) { this.visible[id] = !this.visible[id] },
    reset() {
      this.cameraPreset = 'overview'
      this.cutaway = true
      this.cutPosition = 0.65
      this.membraneOpacity = 0.32
      this.rotating = false
      this.resetToken += 1
    },
  },
})
