<template>
  <div class="page methods-page">
    <RouterView />
  </div>
</template>

<style scoped>
.methods-page{width:100%;max-width:1440px;min-width:0;margin:0 auto;padding:30px clamp(72px,5.5vw,80px) 50px}
@media(max-width:900px){.methods-page{padding-inline:24px}}
@media(max-width:680px){.methods-page{padding:23px 16px 35px}}
</style>
