import { onBeforeUnmount, shallowRef, watch, type WatchSource } from 'vue'

export interface AssistantSource {
  kind: 'run'
  id: string
  title: string
  completed: boolean
}

export const assistantSource = shallowRef<AssistantSource | null>(null)

/** The result view publishes its current source; the global floating assistant reads it. */
export function useAssistantSource(source: WatchSource<AssistantSource | null>) {
  let published: AssistantSource | null = null
  watch(source, value => {published = value; assistantSource.value = value}, {immediate: true})
  onBeforeUnmount(() => {
    if (assistantSource.value === published) assistantSource.value = null
  })
}
