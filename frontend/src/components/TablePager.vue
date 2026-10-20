<script setup lang="ts">
import { PAGE_SIZE_OPTIONS } from '../utils/pagination'
defineProps<{ page: number; pageSize: number; pages: number; total: number }>()
const emit = defineEmits<{ 'update:page': [value: number]; 'update:pageSize': [value: number] }>()
function changeSize(event: Event) {
  emit('update:pageSize', Number((event.target as HTMLSelectElement).value))
  emit('update:page', 1)
}
</script>

<template>
  <nav class="pager" aria-label="表格分页">
    <span class="small muted">共 {{ total }} 条 · 第 {{ page }} / {{ pages }} 页</span>
    <select class="select page-size" aria-label="每页条数" :value="pageSize" @change="changeSize"><option v-for="size in PAGE_SIZE_OPTIONS" :key="size" :value="size">{{ size }} 条 / 页</option></select>
    <button class="btn btn-sm" :disabled="page <= 1" @click="emit('update:page', page - 1)">上一页</button>
    <button class="btn btn-sm" :disabled="page >= pages" @click="emit('update:page', page + 1)">下一页</button>
  </nav>
</template>

<style scoped>
.pager { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.pager .page-size { width: auto; min-width: 95px; min-height: 32px; margin: 0; font-size: 11px; }
</style>
