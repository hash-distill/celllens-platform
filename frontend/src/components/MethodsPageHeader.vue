<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; description: string; index?: string }>()
</script>

<template>
  <header class="page-heading methods-page-heading">
    <div class="methods-heading-copy"><span class="eyebrow">{{ eyebrow }}</span><div class="methods-title-line"><h1>{{ title }}</h1><span v-if="index" class="atlas-page-index" aria-hidden="true">{{ index }}<i> / 04</i></span></div><p>{{ description }}</p></div>
    <div v-if="$slots.default" class="methods-page-actions"><slot /></div>
  </header>
</template>

<style scoped>
.methods-page-heading{display:flex;align-items:center;justify-content:space-between;gap:28px;margin:0 0 27px;padding:0 0 23px;border-bottom:1px solid var(--border)}
.methods-heading-copy{min-width:0;flex:1}.methods-page-heading .eyebrow{color:var(--primary);font:10px Consolas,monospace;letter-spacing:.14em}.methods-title-line{display:flex;align-items:center;gap:24px}.methods-page-heading h1{font-size:32px;font-weight:500;letter-spacing:-.025em;line-height:1.4;margin:9px 0 10px}.methods-page-heading p{max-width:850px;font-size:13px;line-height:1.85;color:var(--muted);margin:0}.atlas-page-index{font:28px Georgia,serif;color:var(--primary);white-space:nowrap}.atlas-page-index i{font:12px Consolas,monospace;color:var(--faint)}.methods-page-actions{display:flex;align-items:center;gap:12px;flex:none}
@media(max-width:650px){.methods-page-heading{flex-wrap:wrap;gap:15px;margin-bottom:22px;padding-bottom:20px}.methods-page-heading h1{font-size:27px}.methods-heading-copy{flex-basis:100%}.atlas-page-index{font-size:24px}.methods-title-line{justify-content:space-between}.methods-page-heading p{font-size:13px}}
</style>
