import { defineStore } from 'pinia'

export type ToastKind = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  kind: ToastKind
  text: string
}

let nextId = 1

export const useUiStore = defineStore('ui', {
  state: () => ({
    toasts: [] as Toast[],
  }),
  actions: {
    push(kind: ToastKind, text: string, timeoutMs = 6000): void {
      const toast: Toast = { id: nextId++, kind, text }
      this.toasts.push(toast)
      if (timeoutMs > 0) {
        window.setTimeout(() => this.dismiss(toast.id), timeoutMs)
      }
    },
    dismiss(id: number): void {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
  },
})
