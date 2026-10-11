import { defineStore } from 'pinia'
import type { CellLine, RunMode } from '../types/run'

/**
 * 参数表单草稿：运行开始后，表单作为「下一次实验草稿」独立编辑，
 * 不回写当前运行标题；状态保存在 store 中，切换视图不丢失。
 */
export const useDraftStore = defineStore('draft', {
  state: () => ({
    cellLine: 'K562' as CellLine,
    perturbation: '' as string,
    mode: 'online' as RunMode,
    nCells: '64' as string | number,
    seed: '42' as string | number,
    advancedOpen: false,
  }),
  actions: {
    setCellLine(cellLine: CellLine): void {
      if (this.cellLine !== cellLine) {
        this.cellLine = cellLine
        // 切换细胞背景后，原扰动选择可能失效，重新拉取列表并清空选择
        this.perturbation = ''
      }
    },
    applyFromRequest(req: {
      cell_line: CellLine
      perturbation: string
      mode: RunMode
      n_cells: number
      seed: number
    }): void {
      this.cellLine = req.cell_line
      this.perturbation = req.perturbation
      this.mode = 'online'
      this.nCells = String(req.n_cells)
      this.seed = String(req.seed)
    },
  },
})
