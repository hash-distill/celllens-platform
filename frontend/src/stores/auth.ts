import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiFetch, ApiError } from '../api/http'
import type { ResearchUser } from '../types/userData'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<ResearchUser | null>(null), loaded = ref(false), error = ref('')
  let pending: Promise<void> | null = null
  let generation = 0
  async function refresh() {
    if (pending) return pending
    const current = generation
    pending = (async () => {
      try {
        const result = await apiFetch<ResearchUser>('/auth/me')
        if (current === generation) {user.value = result; error.value = ''}
      }
      catch (reason) {
        if (current !== generation) return
        user.value = null
        error.value = reason instanceof ApiError && reason.status === 401 ? '' : reason instanceof Error ? reason.message : '登录状态读取失败'
      } finally {loaded.value = true; pending = null}
    })()
    return pending
  }
  async function login(username: string, password: string) {
    generation++
    user.value = await apiFetch<ResearchUser>('/auth/login', {method: 'POST', body: {username, password}})
    loaded.value = true; error.value = ''
  }
  async function logout() {
    if (user.value) await apiFetch('/auth/logout', {method: 'POST', headers: {'X-CSRF-Token': user.value.csrf_token}})
    generation++; user.value = null
  }
  return {user, loaded, error, refresh, login, logout}
})
