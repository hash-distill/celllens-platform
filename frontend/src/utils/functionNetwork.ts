import type { TraceScore } from '../types/trace'

export type NodeKind = 'gene' | 'reaction' | 'task'
export type ValueSource = 'control' | 'predicted' | 'delta' | 'observed'
export interface FunctionNode { kind: NodeKind; score: TraceScore; x: number; y: number }
export const KIND_LABEL: Record<NodeKind, string> = { gene: '基因表达', reaction: '反应分数', task: '任务分数' }
export function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
export function nodeValue(score: TraceScore, source: ValueSource): number | null {
  if (source === 'delta') return finite(score.predicted_delta)
  // Saved observed deltas share the control reference. No observed value is invented when either part is missing.
  if (source === 'observed') {
    const control = finite(score.control), delta = finite(score.observed_delta)
    return control === null || delta === null ? null : finite(control + delta)
  }
  return finite(score[source])
}
export function layoutNodes(task: TraceScore, reaction?: TraceScore & { genes: TraceScore[] }): FunctionNode[] {
  const genes = [...(reaction?.genes ?? [])].sort((a, b) => a.id.localeCompare(b.id))
  const height = Math.max(260, genes.length * 52 + 90), y = height / 2
  return [...genes.map((score, index) => ({ kind: 'gene' as const, score, x: 92, y: 72 + index * 52 })),
    ...(reaction ? [{ kind: 'reaction' as const, score: reaction, x: 278, y }] : []),
    { kind: 'task' as const, score: task, x: 462, y }]
}
export function scaleFor(nodes: FunctionNode[], kind: NodeKind, delta: boolean): number {
  const values = nodes.filter(node => node.kind === kind).flatMap(node =>
    (delta ? ['delta'] as const : ['control', 'predicted', 'observed'] as const).map(source => nodeValue(node.score, source)))
  return Math.max(1e-9, ...values.map(value => value === null ? 0 : Math.abs(value)))
}
export function nodeColor(value: number | null, scale: number): string {
  if (value === null) return '#d5d9d5'
  const strength = Math.min(1, Math.abs(value) / scale)
  const base = [242, 243, 235], target = value < 0 ? [54, 127, 135] : [177, 84, 48]
  return `rgb(${base.map((channel, index) => Math.round(channel + (target[index]! - channel) * strength)).join(',')})`
}
export function nodeTextColor(value: number | null, scale: number): string {
  if (value===null) return '#000000'
  const channels = nodeColor(value,scale).match(/\d+/g)?.map(Number)
  if (!channels || channels.length!==3) return '#000000'
  const luminance = channels.map(channel => { const x=channel/255; return x<=0.04045 ? x/12.92 : ((x+0.055)/1.055)**2.4 })
  return 0.2126*luminance[0]!+0.7152*luminance[1]!+0.0722*luminance[2]! < 0.179 ? '#ffffff' : '#000000'
}
