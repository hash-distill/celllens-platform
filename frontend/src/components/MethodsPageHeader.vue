<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; description: string }>()
</script>

<template>
  <header class="page-heading methods-page-heading">
    <div><span class="eyebrow">{{ eyebrow }}</span><h1>{{ title }}</h1><p>{{ description }}</p></div>
    <div v-if="$slots.default" class="methods-page-actions"><slot /></div>
  </header>
</template>

<style scoped>
.methods-page-heading{align-items:center;gap:24px}.methods-page-heading>div:first-child{max-width:960px}.methods-page-actions{display:flex;align-items:center;gap:12px;flex:none}.methods-page-heading h1{margin:8px 0}.methods-page-heading p{margin-bottom:0}
</style>
