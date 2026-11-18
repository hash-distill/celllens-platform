<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 38 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 48 48" fill="none" aria-hidden="true" class="celllens-brand-mark">
    <path d="M40 15C46 25 39 40 26 43C13 45 3 36 4 23C5 11 14 3 26 5C32 5 37 9 40 15Z" fill="#e3eee4" stroke="#6eaa87" stroke-width="1.6" />
    <path d="M34 16C39 23 35 33 26 36C17 39 10 32 11 24C11 15 17 10 25 11C29 11 32 13 34 16Z" fill="#c9dfce" stroke="#367d59" />
    <ellipse cx="23" cy="24" rx="6.4" ry="6.8" fill="#2d7556" />
    <circle cx="22" cy="22" r="2" fill="#b5d5ad" />
    <path d="M30 14C33 13 35 15 33 17C31 19 29 17 30 14Z" fill="#c4a45f" />
    <path d="M13 29C16 28 18 30 16 33C14 35 12 33 13 29Z" fill="#78a78a" />
    <circle cx="32" cy="30" r="1.5" fill="#579375" />
  </svg>
</template>
