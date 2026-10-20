import { computed, ref, watch, type ComputedRef } from 'vue'

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const

export function usePagedRows<T>(rows: ComputedRef<T[]>) {
  const page = ref(1)
  const pageSize = ref(20)
  const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / pageSize.value)))
  const visible = computed(() => rows.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
  watch([rows, pageSize], () => { page.value = 1 }, { flush: 'sync' })
  return { page, pageSize, pages, visible }
}
