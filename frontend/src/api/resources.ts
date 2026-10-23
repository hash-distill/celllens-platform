import { apiFetch } from './http'
export type ResourceCell = 'K562'|'RPE1'|'Jurkat'|'HepG2'
export interface ResourceJob {status: 'idle'|'queued'|'downloading'|'verifying'|'preparing_control'|'completed'|'cancelled'|'interrupted'|'failed'; downloaded_bytes?: number; total_bytes?: number; current_file?: string; message?: string; updated_at?: string}
export interface ResourcePack {cell_line: ResourceCell; size_bytes: number; remaining_bytes: number; weights_ready: boolean; control_ready: boolean; ready: boolean; license: string; source_url: string; files: {name: string; size_bytes: number; status: 'verified'|'missing'|'invalid'}[]; job: ResourceJob}
export interface ResourceCatalog {items: ResourcePack[]; active_cell: ResourceCell|null; can_cancel: boolean; download_location: string}
export const resourcesApi = {
  list: (signal?: AbortSignal) => apiFetch<ResourceCatalog>('/resources', {signal,timeoutMs:60000}),
  start: (cell: ResourceCell) => apiFetch<ResourceJob>(`/resources/${cell}/download`, {method:'POST',body:{accepted_license:true}}),
  cancel: (cell: ResourceCell) => apiFetch<{status:string}>(`/resources/${cell}/cancel`, {method:'POST'}),
}
