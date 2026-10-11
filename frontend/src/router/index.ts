import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/workbench', name: 'workbench', component: () => import('../views/WorkbenchView.vue') },
    // tab 通过查询参数记录：/runs/:runId?tab=cell|genes|metabolism|validation
    { path: '/runs/:runId', name: 'run-detail', redirect: to => ({path:'/workbench',query:{run:String(to.params.runId),tab:to.query.tab==='structure'?undefined:to.query.tab}}) },
    { path: '/records', name: 'records', component: () => import('../views/RecordsView.vue') },
    { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue') },
    { path: '/demo', name: 'demo', component: () => import('../views/DemoView.vue') },
    { path: '/about', name: 'about', component: () => import('../views/AboutView.vue') },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
    { path: '/datasets', name: 'datasets', component: () => import('../views/DatasetsView.vue'), meta: {requiresAuth: true} },
    { path: '/analyses/:analysisId', name: 'user-analysis', component: () => import('../views/UserAnalysisView.vue'), meta: {requiresAuth: true} },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
  scrollBehavior(to, from) { if(to.path===from.path && to.query.run===from.query.run)return;return {top:0} },
})

router.beforeEach(async to => {
  if (!to.meta.requiresAuth) return true
  const auth = useAuthStore()
  await auth.refresh()
  if (!auth.user) return {path: '/login', query: {next: to.fullPath}}
  return true
})
