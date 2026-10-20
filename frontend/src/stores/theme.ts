import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'celllens-theme'

function readStoredTheme(): ThemeMode | null {
  if (typeof window === 'undefined') return null
  const value = window.localStorage.getItem(STORAGE_KEY)
  return value === 'dark' || value === 'light' ? value : null
}

function applyTheme(mode: ThemeMode): void {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.theme = mode
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    current: 'light' as ThemeMode,
    ready: false,
  }),
  actions: {
    init(): void {
      if (this.ready) return
      const stored = readStoredTheme()
      this.current = stored ?? 'light'
      applyTheme(this.current)
      this.ready = true
    },
    setTheme(mode: ThemeMode): void {
      this.current = mode
      applyTheme(mode)
      if (typeof window !== 'undefined') window.localStorage.setItem(STORAGE_KEY, mode)
      this.ready = true
    },
    toggle(): void {
      this.setTheme(this.current === 'light' ? 'dark' : 'light')
    },
  },
})
