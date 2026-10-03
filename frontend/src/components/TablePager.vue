<script setup lang="ts">
defineProps<{ page: number; pages: number; total: number }>()
const emit = defineEmits<{ 'update:page': [value: number] }>()
</script>

<template>
  <nav class="pager" aria-label="表格分页">
    <span class="small muted">共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页 · 每页 50 条</span>
    <button class="btn btn-sm" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
    <button class="btn btn-sm" :disabled="page >= pages" @click="emit('update:page', page + 1)">下一页</button>
  </nav>
</template>

<style scoped>
.pager { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
</style>
