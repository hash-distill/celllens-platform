import { computed, reactive, ref } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'system'
export interface ModelPreferences {base_url: string; model: string; max_tokens: number; token_parameter: 'max_completion_tokens' | 'max_tokens'}
const themeKey = 'celllens.theme', modelKey = 'celllens.model', secretKey = 'celllens.api-key'
function read(storage: Storage, key: string): string {try {return storage.getItem(key) ?? ''} catch {return ''}}
const savedTheme = read(localStorage, themeKey)
export const theme = ref<ThemePreference>(['light','dark','system'].includes(savedTheme) ? savedTheme as ThemePreference : 'system')
const media = window.matchMedia('(prefers-color-scheme: dark)')
const systemDark = ref(media.matches)
export const isDark = computed(() => theme.value === 'dark' || (theme.value === 'system' && systemDark.value))
export function applyTheme() {document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'}
media.addEventListener('change', event => {systemDark.value = event.matches; applyTheme()})
applyTheme()
export function setTheme(value: ThemePreference): boolean {
  theme.value = value; applyTheme()
  try {localStorage.setItem(themeKey, value); return true} catch {return false}
}
export const modelPreferences = reactive<ModelPreferences>({base_url: 'https://api.openai.com/v1', model: '', max_tokens: 2048, token_parameter: 'max_completion_tokens'})
try {
  const saved = JSON.parse(read(localStorage, modelKey)) as Partial<ModelPreferences>
  if (typeof saved?.base_url === 'string') modelPreferences.base_url = saved.base_url
  if (typeof saved?.model === 'string') modelPreferences.model = saved.model
  if (typeof saved?.max_tokens === 'number' && saved.max_tokens >= 256 && saved.max_tokens <= 8192) modelPreferences.max_tokens = saved.max_tokens
  if (saved?.token_parameter === 'max_tokens') modelPreferences.token_parameter = saved.token_parameter
} catch { /* No saved preferences. */ }
export const apiKey = ref(read(sessionStorage, secretKey))
export const modelReady = computed(() => Boolean(modelPreferences.model.trim() && apiKey.value.trim()))
export function saveModel(preferences: ModelPreferences, key: string): boolean {
  Object.assign(modelPreferences, preferences)
  apiKey.value = key.trim()
  try {
    localStorage.setItem(modelKey, JSON.stringify({...modelPreferences}))
    if (apiKey.value) sessionStorage.setItem(secretKey, apiKey.value)
    else sessionStorage.removeItem(secretKey)
    return true
  } catch {return false}
}
export function clearKey() {apiKey.value = ''; try {sessionStorage.removeItem(secretKey)} catch { /* Memory cleared. */ }}
export function modelConnection() {return {...modelPreferences, api_key: apiKey.value}}
