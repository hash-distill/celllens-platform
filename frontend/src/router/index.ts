import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/data-catalog', name: 'data-catalog', component: () => import('../views/DataCatalogView.vue') },
    { path: '/research', name: 'research', component: () => import('../views/ResearchView.vue') },
    { path: '/measured', name: 'measured', redirect: to => ({path:'/research', query:{...to.query, type:'measured'}, hash:to.hash}) },
    { path: '/measured/:analysisId', name: 'measured-detail', component: () => import('../views/MeasuredAnalysisView.vue') },
    { path: '/workbench', name: 'workbench', redirect: to => typeof to.query.run === 'string'
      ? {path:`/runs/${encodeURIComponent(to.query.run)}`, query:{...to.query, run:undefined}, hash:to.hash}
      : {path:'/research', query:{...to.query, type:'prediction'}, hash:to.hash} },
    // tab 通过查询参数记录：/runs/:runId?tab=cell|genes|metabolism|validation
    { path: '/runs/:runId', name: 'run-detail', component: () => import('../views/WorkbenchView.vue'), props: {resultsOnly:true} },
    { path: '/records', name: 'records', component: () => import('../views/RecordsView.vue') },
    { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue') },
    { path: '/demo', name: 'demo', redirect: to => typeof to.query.run === 'string' ? ({path:`/runs/${encodeURIComponent(to.query.run)}`,query:{...to.query,run:undefined}}) : '/records' },
    { path: '/about', name: 'about', component: () => import('../views/AboutView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
    { path: '/status', name: 'service-status', component: () => import('../views/ServiceStatusView.vue') },
    {
      path: '/methods', component: () => import('../views/MethodsView.vue'),
      children: [
        { path: '', redirect: '/methods/models' },
        { path: 'models', name: 'model-methods', component: () => import('../views/ModelMethodsView.vue') },
        { path: 'backgrounds', name: 'cell-backgrounds', component: () => import('../components/DataOverview.vue') },
        { path: 'coverage', name: 'data-coverage', component: () => import('../views/CoverageView.vue') },
        { path: 'data', redirect: to => ({path:to.query.run || to.query.task ? '/methods/coverage' : '/methods/backgrounds', query:to.query, hash:to.hash}) },
      ],
    },
    { path: '/coverage', name: 'coverage', redirect: to => ({path:'/methods/coverage', query:to.query, hash:to.hash}) },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior(to, from) { if(to.hash)return {el:to.hash,top:90};if(to.path===from.path && to.query.run===from.query.run)return;return {top:0} },
})

// Already-open pages may refer to lazy chunks removed by a production rebuild.
// Reload the intended route once; keep the marker if its import fails again.
const recoveryKey = 'celllens:route-asset-recovery'
router.onError((error, to) => {
  const message = error instanceof Error ? error.message : String(error)
  if (!/Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS/i.test(message)) return
  try {
    const previous = JSON.parse(sessionStorage.getItem(recoveryKey) || 'null') as {path: string; at: number} | null
    if (previous?.path === to.fullPath && Date.now() - previous.at < 30_000) return
    sessionStorage.setItem(recoveryKey, JSON.stringify({path: to.fullPath, at: Date.now()}))
    window.location.assign(router.resolve(to).href)
  } catch { /* Storage unavailable: avoid an unguarded reload loop. */ }
})
router.afterEach((to, _from, failure) => {
  if (failure) return
  try {
    const previous = JSON.parse(sessionStorage.getItem(recoveryKey) || 'null') as {path: string} | null
    if (previous?.path === to.fullPath) sessionStorage.removeItem(recoveryKey)
  } catch { /* Navigation remains usable when browser storage is unavailable. */ }
})
