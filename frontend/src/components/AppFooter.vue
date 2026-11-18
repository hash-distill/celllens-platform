<script setup lang="ts">
import BrandMark from './BrandMark.vue'
</script>

<template>
  <footer class="site-footer" aria-label="版权与开发团队">
    <div class="site-footer-inner">
      <span class="footer-brand"><BrandMark :size="24"/><span>© CellLens</span><i>细胞知镜</i></span>
      <p class="footer-credit">AI for Science 团队 <span class="team-name">代谢不对队</span> 开发</p>
    </div>
  </footer>
</template>

<style scoped>
.site-footer{flex-shrink:0;color:var(--muted);border-top:1px solid var(--border)}
.site-footer-inner{max-width:1440px;width:100%;margin:0 auto;padding:23px clamp(72px,5.5vw,80px);display:grid;grid-template-columns:1fr;justify-items:center;align-items:center;gap:8px}
.footer-brand{display:flex;align-items:center;gap:8px;color:var(--ink);font:15px Georgia,serif;white-space:nowrap}
.footer-brand i{font:normal 12px var(--font);letter-spacing:1px}
.footer-credit{grid-column:1;justify-self:center;margin:0;font-size:12px;line-height:2;display:flex;align-items:center;gap:6px;flex-wrap:wrap;justify-content:center}
.team-name{position:relative;display:inline-block;padding:0 4px;color:inherit;line-height:1.5;white-space:nowrap}
.team-name::before,.team-name::after{content:'';position:absolute;width:5px;height:5px;border-color:currentColor;border-style:solid;pointer-events:none}
.team-name::before{top:0;left:0;border-width:1px 0 0 1px}
.team-name::after{bottom:0;right:0;border-width:0 1px 1px 0}
@media(min-width:1600px){.site-footer.assistant-docked{margin-right:596px}}
@media(max-width:900px){.site-footer-inner{padding-inline:24px}}
@media(max-width:680px){.site-footer-inner{padding:20px 16px;gap:8px;grid-template-columns:1fr}.footer-credit{grid-column:1;font-size:11px}}
</style>
