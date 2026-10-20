export interface ResourceUsage {total_bytes: number | null; used_bytes: number | null}
export interface SystemStatus {
  service: string; checked_at: string
  database: {connected: boolean; engine: string; version: string | null; latency_ms: number | null; pool_size: number | null; checked_out: number | null}
  gpu: {configured: boolean; detected: boolean; message: string | null; devices: {
    index: string; name: string; driver_version: string
    memory_total_bytes: number | null; memory_used_bytes: number | null
    utilization_percent: number | null; temperature_c: number | null
  }[]}
  workers: {online_enabled: boolean; online_running: boolean; online_pending: number | null; sources?: Partial<Record<'worker_enabled' | 'gpu_available', 'environment' | 'env_file' | 'default'>>}
  system: {os: string; os_release: string; os_version: string; os_display_version: string | null; architecture: string; python: string; cpu_model: string | null; cpu_logical_cores: number | null; memory: ResourceUsage; storage: ResourceUsage & {free_bytes: number | null}}
  versions: Record<string, string | null>
}
