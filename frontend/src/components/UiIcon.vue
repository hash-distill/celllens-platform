<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })
const paths: Record<string, string> = {
  cube: 'M12 3 3 8v9l9 5 9-5V8l-9-5Zm0 0v9m-9-4 9 4 9-4m-9 4v10',
  layers: 'm12 3 9 5-9 5-9-5 9-5ZM3 12l9 5 9-5M3 16l9 5 9-5',
  chart: 'M4 3v17h17M8 16v-5m5 5V6m5 10V9',
  play: 'm8 4 12 8-12 8V4Z',
  pause: 'M8 4v16M16 4v16',
  arrow: 'M4 12h16m-6-6 6 6-6 6',
  back: 'M20 12H4m6-6-6 6 6 6',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm10-3a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  hidden: 'm3 3 18 18M9 5c1-.3 2-.4 3-.4 6 0 10 7.4 10 7.4s-1.2 2.2-3.4 4M6 6C3.5 8.2 2 12 2 12s4 7 10 7c1.4 0 2.7-.4 4-1',
  reset: 'M3 10a9 9 0 1 1 1 8M3 4v6h6',
  cut: 'M4 4h16v16H4V4Zm8 0v16m-8-8h16',
  help: 'M9 9a3 3 0 1 1 5 2c-1.3.7-2 1.1-2 3m0 3v.1M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
  export: 'M12 3v12m-4-8 4-4 4 4M4 14v7h16v-7',
  file: 'M5 3h9l5 5v13H5V3Zm9 0v6h5M8 13h8m-8 4h8',
  compare: 'M4 4h6v16H4V4Zm10 0h6v16h-6V4Z',
  search: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6',
  check: 'm5 12 4 4 10-11',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10 2 2M5 19l2-2M17 7l2-2',
  moon: 'M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11Z',
  settings: 'M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1 1-3Zm3 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  top: 'M5 4h14M12 20V8m-5 5 5-5 5 5',
  bottom: 'M5 20h14M12 4v12m-5-5 5 5 5-5',
  sparkle: 'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] ?? paths.cube" /></svg></template>
