/** Development fixtures are unavailable in production builds. */
const ENV_ENABLED = import.meta.env.DEV &&
  String(import.meta.env.VITE_ENABLE_MOCK ?? '').trim().toLowerCase() === 'true'

const LS_KEY = 'celllens.mockMode.v1'

export function isMockEnabled(): boolean {
  if (!import.meta.env.DEV) return false
  if (ENV_ENABLED) return true
  try {
    return localStorage.getItem(LS_KEY) === 'on'
  } catch {
    return false
  }
}
