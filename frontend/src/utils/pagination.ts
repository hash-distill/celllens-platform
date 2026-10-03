import { computed, ref, watch, type ComputedRef } from 'vue'

export function usePagedRows<T>(rows: ComputedRef<T[]>) {
  const page = ref(1)
  const pages = computed(() => Math.max(1, Math.ceil(rows.value.length / 50)))
  const visible = computed(() => rows.value.slice((page.value - 1) * 50, page.value * 50))
  watch(rows, () => { page.value = 1 }, { flush: 'sync' })
  return { page, pages, visible }
}
