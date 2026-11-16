export type CellRegionKey = 'nucleus' | 'mitochondria' | 'er' | 'golgi' | 'membrane' | 'cytoplasm'
export interface CellSceneController {
  select(key: CellRegionKey | '' | null): void
  reset(): void
  setZoom(value: number): number
  toggleMotion(): boolean
  setMotion(value: boolean): void
  dispose(): void
}
export function mountCellScene(container: HTMLElement, options?: {
  onSelect?: (key: CellRegionKey) => void
  onUnavailable?: () => void
  onZoomChange?: (value: number) => void
  compact?: boolean
  interactive?: boolean
}): CellSceneController | null
