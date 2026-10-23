import { computed, reactive, ref } from 'vue'
import type { ModelPreferences } from '../types/assistant'
import { cleanPreferences, DEFAULT_MODEL } from '../utils/modelConfig'

export { applyTheme, isDark, setTheme, theme, type ThemePreference } from './appearance'
export type { ModelPreferences } from '../types/assistant'
export interface ConnectionProfile extends ModelPreferences {id:string; name:string}
const modelKey = 'celllens.model', secretKey = 'celllens.api-key', profilesKey = 'celllens.connection-profiles'
function read(storage: Storage, key: string): string {try {return storage.getItem(key) ?? ''} catch {return ''}}
let initial = {...DEFAULT_MODEL}
let migratedLengths = false
try {
  initial = cleanPreferences({...JSON.parse(read(localStorage,modelKey)),max_tokens:null,context_window:null})
  migratedLengths = true
} catch { /* Use defaults if old settings are invalid. */ }
export const connectionProfiles = ref<ConnectionProfile[]>([{...initial,id:'default',name:'默认连接'}])
export const activeConnectionId = ref('default')
const secrets: Record<string,string> = Object.create(null) as Record<string,string>
let profilesLoaded = false
try {
  const saved = JSON.parse(read(localStorage,profilesKey)) as {version:number; active_id:string; connections:ConnectionProfile[]}
    if ([1,2].includes(saved.version) && Array.isArray(saved.connections) && saved.connections.length > 0 && saved.connections.length <= 20) {
    const profiles = saved.connections.map(item => {
      if (typeof item.id !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(item.id) || typeof item.name !== 'string' || !item.name.trim() || item.name.length > 64) throw new Error('Invalid profile')
      return {...cleanPreferences(saved.version === 1 ? {...item,max_tokens:null,context_window:null} : item),id:item.id,name:item.name}
    })
    if (new Set(profiles.map(item => item.id)).size !== profiles.length) throw new Error('Duplicate profile')
    connectionProfiles.value = profiles
    activeConnectionId.value = profiles.find(item => item.id === saved.active_id)?.id ?? profiles[0]!.id
    profilesLoaded = true
    migratedLengths = saved.version === 1
  }
} catch { /* Legacy single-connection settings remain usable. */ }
try {
  const saved = JSON.parse(read(sessionStorage,secretKey+'.profiles')) as Record<string,unknown>
  for (const profile of connectionProfiles.value) if (typeof saved[profile.id] === 'string') secrets[profile.id] = saved[profile.id] as string
} catch { /* No session keys saved. */ }
const active = connectionProfiles.value.find(item => item.id === activeConnectionId.value)!
if (!profilesLoaded) secrets[active.id] = read(sessionStorage,secretKey)
export const modelPreferences = reactive<ModelPreferences>(cleanPreferences(active))
export const apiKey = ref(secrets[active.id] ?? '')
export const modelReady = computed(() => Boolean(modelPreferences.model.trim() && modelPreferences.base_url.trim() && (modelPreferences.provider === 'custom' || apiKey.value.trim())))
function persist(): boolean {
  let stored = true
  try {
    localStorage.setItem(modelKey,JSON.stringify({...modelPreferences}))
    localStorage.setItem(profilesKey,JSON.stringify({version:2,active_id:activeConnectionId.value,connections:connectionProfiles.value}))
  } catch {stored = false}
  try {
    sessionStorage.setItem(secretKey+'.profiles',JSON.stringify(secrets))
    if (apiKey.value) sessionStorage.setItem(secretKey,apiKey.value)
    else sessionStorage.removeItem(secretKey)
  } catch {stored = false}
  return stored
}
export function saveModel(preferences: ModelPreferences, key: string, name?: string): boolean {
  Object.assign(modelPreferences,cleanPreferences(preferences))
  const index = connectionProfiles.value.findIndex(item => item.id === activeConnectionId.value)
  const label = name?.trim().slice(0,64) || connectionProfiles.value[index]?.name || '我的 API'
  connectionProfiles.value[index] = {...modelPreferences,id:activeConnectionId.value,name:label}
  apiKey.value = key.trim()
  secrets[activeConnectionId.value] = apiKey.value
  return persist()
}
export function selectConnection(id: string): boolean {
  const profile = connectionProfiles.value.find(item => item.id === id)
  if (!profile) return false
  activeConnectionId.value = id
  Object.assign(modelPreferences,cleanPreferences(profile))
  apiKey.value = secrets[id] ?? ''
  return persist()
}
export function addConnection(name: string, preferences: ModelPreferences = DEFAULT_MODEL, key = ''): boolean {
  if (connectionProfiles.value.length >= 20) throw new Error('最多保存 20 组连接，请先移除不用的连接')
  const profile = {...cleanPreferences(preferences),id:crypto.randomUUID(),name:name.trim().slice(0,64) || '新的连接'}
  connectionProfiles.value.push(profile)
  secrets[profile.id] = key.trim()
  return selectConnection(profile.id)
}
export function removeConnection(id: string): boolean {
  if (connectionProfiles.value.length <= 1) throw new Error('请至少保留一组连接')
  connectionProfiles.value = connectionProfiles.value.filter(item => item.id !== id)
  delete secrets[id]
  return selectConnection(id === activeConnectionId.value ? connectionProfiles.value[0]!.id : activeConnectionId.value)
}
export function clearKey() {apiKey.value = ''; delete secrets[activeConnectionId.value]; persist()}
export function modelConnection() {return {...modelPreferences,api_key:apiKey.value}}
if (migratedLengths) persist()
