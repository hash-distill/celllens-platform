<script setup lang="ts">
import { useSceneStore } from '../stores/scene'
import UiIcon from './UiIcon.vue'
const scene = useSceneStore()
</script>
<template>
  <nav class="instrument-rail" aria-label="工作区工具">
    <RouterLink to="/workbench" class="rail-tool" title="实验工作台"><UiIcon name="cube" :size="23" /><span>实验</span></RouterLink>
    <button class="rail-tool" type="button" :aria-pressed="scene.cutaway" title="切换结构剖面" @click="scene.cutaway = !scene.cutaway"><UiIcon name="cut" :size="22" /><span>剖面</span></button>
    <button class="rail-tool" type="button" title="复位三维视角" @click="scene.reset()"><UiIcon name="reset" :size="22" /><span>复位</span></button>
    <RouterLink to="/compare" class="rail-tool" title="实验比较"><UiIcon name="compare" :size="22" /><span>比较</span></RouterLink>
    <RouterLink to="/demo" class="rail-tool" title="结构演示"><UiIcon name="play" :size="22" /><span>演示</span></RouterLink>
    <RouterLink to="/about" class="rail-tool rail-help" title="方法与来源"><UiIcon name="help" :size="22" /><span>方法</span></RouterLink>
  </nav>
</template>
