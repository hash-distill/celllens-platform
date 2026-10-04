<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import ParamPanel from '../components/ParamPanel.vue'
import RecentRuns from '../components/RecentRuns.vue'
import CandidateTray from '../components/CandidateTray.vue'
import InstrumentRail from '../components/InstrumentRail.vue'
import SceneLayers from '../components/scene/SceneLayers.vue'
import ObjectInspector from '../components/scene/ObjectInspector.vue'
import ExperimentDock from '../components/ExperimentDock.vue'
import { useDraftStore } from '../stores/draft'
const CellViewport = defineAsyncComponent(() => import('../components/scene/CellViewport.vue'))
const draft = useDraftStore()
</script>
<template>
  <div class="instrument-page">
    <div class="context-bar"><div><span class="micro">EXPERIMENT / NEW</span><h1>{{ draft.cellLine }}<span class="context-slash">/</span>{{ draft.perturbation || '新建实验' }}</h1></div><span class="context-note">细胞结构示意 · 非实测形态</span></div>
    <div class="instrument-grid">
      <InstrumentRail />
      <aside class="experiment-panel"><ParamPanel /><SceneLayers /><div class="recent-dock"><RecentRuns compact /></div></aside>
      <section class="workspace-center"><CellViewport /><ExperimentDock /></section>
      <ObjectInspector />
    </div>
    <footer class="instrument-status"><span>STRUCTURE / SCHEMATIC</span><span>拖动旋转 · 滚轮缩放 · 点击选择区室</span><span>CellLens</span></footer>
    <CandidateTray />
  </div>
</template>
