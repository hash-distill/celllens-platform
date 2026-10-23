import { computed, ref } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'
const themeKey = 'celllens.theme'
let savedTheme = ''
try { savedTheme = localStorage.getItem(themeKey) ?? '' } catch { /* Use system appearance. */ }
export const theme = ref<ThemePreference>(['light', 'dark', 'system'].includes(savedTheme) ? savedTheme as ThemePreference : 'system')
const media = window.matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
export const isDark = computed(() => theme.value === 'dark' || (theme.value === 'system' && systemDark.value))
export function applyTheme() { document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light' }
media.addEventListener('change', event => { systemDark.value = event.matches; applyTheme() })
applyTheme()
export function setTheme(value: ThemePreference): boolean {
  theme.value = value
  applyTheme()
  try { localStorage.setItem(themeKey, value); return true } catch { return false }
}
