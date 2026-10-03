import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/workbench' },
    { path: '/workbench', name: 'workbench', component: () => import('../views/WorkbenchView.vue') },
    // tab 通过查询参数记录：/runs/:runId?tab=cell|genes|metabolism|validation
    { path: '/runs/:runId', name: 'run-detail', component: () => import('../views/RunDetailView.vue') },
    { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue') },
    { path: '/about', name: 'about', component: () => import('../views/AboutView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
  ],
})
