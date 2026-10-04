<script setup lang="ts">
import { ORGANELLES, useSceneStore } from '../../stores/scene'
import UiIcon from '../UiIcon.vue'
const scene = useSceneStore()
</script>
<template>
  <section class="scene-layers" aria-label="场景对象">
    <div class="panel-heading"><h2>场景对象</h2><span class="micro mono">05 LAYERS</span></div>
    <div class="scene-tree">
      <div class="scene-tree-root"><UiIcon name="layers" :size="16" /><span>细胞结构</span><span class="micro">示意</span></div>
      <div v-for="item in ORGANELLES" :key="item.id" class="scene-tree-row" :class="{selected: scene.selected === item.id}">
        <button class="object-select" type="button" :aria-pressed="scene.selected === item.id" @click="scene.select(item.id)"><i :style="{background: item.color}"></i><span>{{ item.name }}</span></button>
        <button class="object-visibility" type="button" :aria-label="`${scene.visible[item.id] ? '隐藏' : '显示'}${item.name}`" :aria-pressed="scene.visible[item.id]" @click="scene.toggleVisible(item.id)"><UiIcon :name="scene.visible[item.id] ? 'eye' : 'hidden'" :size="16" /></button>
      </div>
    </div>
    <label class="scene-slider" for="membrane-opacity"><span>细胞膜不透明度</span><b class="mono">{{ scene.membraneOpacity.toFixed(2) }}</b></label>
    <input id="membrane-opacity" v-model.number="scene.membraneOpacity" type="range" min="0.08" max="0.8" step="0.01" />
    <div class="clip-row"><label for="cell-section"><input id="cell-section" v-model="scene.cutaway" type="checkbox" />剖面</label><span class="micro">显示内部层次</span></div>
    <input v-if="scene.cutaway" v-model.number="scene.cutPosition" type="range" min="0" max="1" step="0.01" aria-label="剖面位置" />
  </section>
</template>
<style scoped>
.scene-layers{padding:20px 18px;border-top:1px solid var(--border)}.scene-tree{border:1px solid var(--border);margin:14px 0 16px;background:#fafbf8}.scene-tree-root{display:flex;align-items:center;gap:9px;padding:10px 12px;font-size:12px;border-bottom:1px solid var(--border)}.scene-tree-root .micro{margin-left:auto}.scene-tree-row{display:flex;align-items:center;border-left:2px solid transparent}.scene-tree-row.selected{background:#e4efea;border-left-color:var(--primary)}.object-select{display:flex;align-items:center;gap:10px;flex:1;padding:9px 12px;font-size:13px;text-align:left}.object-select i{width:8px;height:8px;border-radius:50%;flex:none}.object-select,.object-visibility{border:0;background:transparent;cursor:pointer;color:var(--ink);font-family:inherit}.object-visibility{display:grid;place-items:center;width:36px;padding:9px;color:#6a7c78}.scene-slider{display:flex;justify-content:space-between;font-size:11px;color:var(--muted);margin-bottom:7px}.scene-slider b{font-weight:400;color:var(--ink)}input[type=range]{width:100%;accent-color:var(--primary);cursor:pointer;height:14px}.clip-row{display:flex;align-items:center;justify-content:space-between;margin:13px 0 7px;font-size:12px}.clip-row label{display:flex;align-items:center;gap:6px}
</style>
