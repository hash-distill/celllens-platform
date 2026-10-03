/**
 * Mock 演示模式开关（需求 8.4：只能通过显式开发开关启用）。
 *
 * 两条显式启用途径（默认均关闭）：
 * 1. 环境变量 VITE_ENABLE_MOCK=true（构建 / 启动时注入，见 .env.example）；
 * 2. 「使用说明 / 服务状态」页面的本机开关（localStorage，切换后刷新页面生效）。
 *
 * 请求失败绝不会自动开启本开关。
 */

const ENV_ENABLED =
  String(import.meta.env.VITE_ENABLE_MOCK ?? '')
    .trim()
    .toLowerCase() === 'true'

const LS_KEY = 'celllens.mockMode.v1'

/** 环境变量是否已启用 mock */
export const mockEnvEnabled = ENV_ENABLED

export function isMockEnabled(): boolean {
  if (ENV_ENABLED) return true
  try {
    return localStorage.getItem(LS_KEY) === 'on'
  } catch {
    return false
  }
}

/** 本机开关状态（不含环境变量） */
export function isMockOverrideOn(): boolean {
  try {
    return localStorage.getItem(LS_KEY) === 'on'
  } catch {
    return false
  }
}

export function setMockOverride(on: boolean): void {
  try {
    localStorage.setItem(LS_KEY, on ? 'on' : 'off')
  } catch {
    // 本地存储不可用时静默忽略
  }
}
