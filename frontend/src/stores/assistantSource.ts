import { computed, onBeforeUnmount, ref, shallowRef, watch, type WatchSource } from 'vue'
import type { AssistantSelection, AssistantSourceKind } from '../api/assistant'

export interface AssistantSource {
  kind: AssistantSourceKind
  id: string
  title: string
  completed: boolean
  view: AssistantSelection['view']
  selection?: AssistantSelection
}

export const assistantSource = shallowRef<AssistantSource | null>(null)
export const assistantOpen = ref(false)
export const assistantFigure = shallowRef<AssistantSelection | null>(null)
const preferFigure = ref(true)
export const assistantSelection = computed<AssistantSelection>(() => {
  const source = assistantSource.value
  if (source?.kind === 'measured') return source.selection ?? {view:source.view}
  return preferFigure.value && assistantFigure.value ? assistantFigure.value : {view:source?.view ?? 'overview'}
})
export function openAssistant(figure?: boolean) { if (figure !== undefined) preferFigure.value = figure; assistantOpen.value = true }

export function useAssistantFigure(source: WatchSource<AssistantSelection | null>) {
  let published: AssistantSelection | null = null
  watch(source, value => {
    if (value || assistantFigure.value === published) assistantFigure.value = value
    published = value
  }, {immediate:true, flush:'sync'})
  onBeforeUnmount(() => {if (assistantFigure.value === published) assistantFigure.value = null})
}

/** Result and figure views publish only the currently visible, verified source. */
export function useAssistantSource(source: WatchSource<AssistantSource | null>) {
  let published: AssistantSource | null = null
  watch(source, value => {
    if (value?.id !== assistantSource.value?.id || value?.kind !== assistantSource.value?.kind) assistantFigure.value = null
    if (value?.id !== published?.id || value?.kind !== published?.kind || value?.view !== published?.view) preferFigure.value = true
    published = value; assistantSource.value = value
  }, {immediate: true, flush:'sync'})
  onBeforeUnmount(() => {
    if (assistantSource.value === published) {assistantSource.value = null; assistantFigure.value = null}
  })
}
