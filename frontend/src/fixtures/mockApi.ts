/**
 * Mock 样例数据（仅供显式开启的开发演示与样式调试）。
 *
 * 本模块只在 mock 开关开启时被 client.ts 动态引入；
 * 所有数据为固定种子的伪随机假数据，不代表任何真实计算结果。
 */

import { ApiError } from '../api/http'
import type {
  ContextItem,
  CreateRunRequest,
  CreateRunResponse,
  EvidenceItem,
  GenesResponse,
  GeneRow,
  HealthResponse,
  MetabolicTasksResponse,
  PerturbationList,
  ProjectionPoint,
  ProjectionResponse,
  ReactionsResponse,
  ReactionRow,
  ReadyResponse,
  RunRecord,
  RunListQuery,
  RunListResponse,
  RunStatus,
  RunSummary,
} from '../types/run'

// ---------- 工具 ----------

function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function round(value: number, digits = 5): number {
  return Number(value.toFixed(digits))
}

function delay(ms = 120): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function notFound(runId: string, suffix = ''): ApiError {
  return new ApiError({
    kind: 'http',
    status: 404,
    code: 'RUN_NOT_FOUND',
    message: `Mock: run ${runId} not found`,
    endpoint: `/runs/${runId}${suffix}`,
  })
}

// ---------- Mock 运行登记表（仅本浏览器的独立演示存储） ----------

interface MockRun {
  request: CreateRunRequest
  polls: number
  createdAt: string
}

const MOCK_STORAGE = 'celllens.mockRuns.v2'
function loadRuns(): Map<string, MockRun> {
  try {
    const entries = JSON.parse(localStorage.getItem(MOCK_STORAGE) ?? '[]')
    return new Map(Array.isArray(entries) ? entries.filter((item) =>
      Array.isArray(item) && typeof item[0] === 'string' && item[0].startsWith('mock_run_') &&
      item[1]?.request && Number.isInteger(item[1]?.polls),
    ) : [])
  } catch { return new Map() }
}
const mockRuns = loadRuns()
function persistRuns(): void {
  try { localStorage.setItem(MOCK_STORAGE, JSON.stringify([...mockRuns])) } catch { /* session only */ }
}

const STAGE_PLAN: Array<{ status: RunStatus; progress: number }> = [
  { status: 'queued', progress: 5 },
  { status: 'state_running', progress: 22 },
  { status: 'state_running', progress: 41 },
  { status: 'adapting', progress: 55 },
  { status: 'metabolic_running', progress: 70 },
  { status: 'metabolic_running', progress: 84 },
  { status: 'validating', progress: 93 },
  { status: 'completed', progress: 100 },
]

const MOCK_WARNINGS = ['代谢库基因覆盖有限，部分任务只能作探索性解释（mock 样例警告）']

function requireRun(runId: string, suffix = ''): MockRun {
  const run = mockRuns.get(runId)
  if (!run) throw notFound(runId, suffix)
  return run
}

// ---------- 健康与就绪 ----------

export async function health(): Promise<HealthResponse> {
  await delay(60)
  return { service: 'celllens-mock', status: 'ok', database: 'ok' }
}

export async function ready(): Promise<{ httpStatus: number; body: ReadyResponse | null }> {
  await delay(60)
  return {
    httpStatus: 200,
    body: { ready: true, checks: { database: true, worker: true, gpu: true } },
  }
}

// ---------- catalog ----------

export async function contexts(): Promise<ContextItem[]> {
  await delay()
  return [
    {
      cell_line: 'K562',
      online_ready: true,
      validation_ready: true,
      precomputed_ready: true,
      model_id: 'state-k562-mock',
      disabled_reason: null,
      readiness_reasons: [],
    },
    {
      cell_line: 'RPE1',
      online_ready: false,
      validation_ready: false,
      precomputed_ready: false,
      model_id: 'state-rpe1-mock',
      disabled_reason: 'model assets are disabled, missing, or have invalid hashes（mock 样例原因）',
      readiness_reasons: [
        'model assets are disabled, missing, or have invalid hashes',
        'control dataset is disabled, missing, or has an invalid hash',
      ],
    },
  ]
}

const PERTURBATIONS: Record<string, string[]> = {
  K562: ['MYC', 'TP53', 'GATA1', 'JUN', 'FOS', 'STAT3', 'KRAS', 'BCL2', 'EGFR', 'RUNX1'],
  RPE1: [],
}

export async function perturbations(cellLine: string, mode = 'online'): Promise<PerturbationList> {
  await delay()
  return { cell_line: cellLine, items: mode === 'validation' ? [] :
    mode === 'precomputed' ? (cellLine === 'K562' ? ['MYC'] : []) : PERTURBATIONS[cellLine] ?? [] }
}

// ---------- 创建与轮询 ----------

export async function createRun(payload: CreateRunRequest): Promise<CreateRunResponse> {
  await delay(150)
  const runId = `mock_run_${crypto.randomUUID()}`
  mockRuns.set(runId, {
    request: { ...payload },
    polls: 0,
    createdAt: new Date().toISOString(),
  })
  persistRuns()
  // 预计算模式直接完成（与真实后端行为一致）
  return {
    run_id: runId,
    status: payload.mode === 'precomputed' ? 'completed' : 'queued',
    cache_hit: false,
  }
}

export async function listRuns(query: RunListQuery = {}): Promise<RunListResponse> {
  await delay()
  const term = (query.q ?? '').trim().toUpperCase()
  const records = [...mockRuns].map(([id, run]) => snapshotRecord(id, run)).filter(record =>
    (!term || [record.run_id, record.request.cell_line, record.request.perturbation].some(text => text.toUpperCase().includes(term))) &&
    (!query.mode || record.request.mode === query.mode) &&
    (!query.status || query.status === 'all' || (query.status === 'active'
      ? record.status !== 'completed' && record.status !== 'failed' : record.status === query.status)),
  ).sort((a, b) => b.created_at.localeCompare(a.created_at) || b.run_id.localeCompare(a.run_id))
  const limit = query.limit ?? 20, offset = query.offset ?? 0
  return {items: records.slice(offset, offset + limit), total: records.length, limit, offset}
}

export async function getRun(runId: string): Promise<RunRecord> {
  await delay(80)
  const run = requireRun(runId)
  run.polls += 1
  persistRuns()
  return snapshotRecord(runId, run)
}

function snapshotRecord(runId: string, run: MockRun): RunRecord {
  const stage =
    run.request.mode === 'precomputed'
      ? STAGE_PLAN[STAGE_PLAN.length - 1]
      : STAGE_PLAN[Math.max(0, Math.min(run.polls - 1, STAGE_PLAN.length - 1))]
  const now = new Date().toISOString()
  return {
    run_id: runId,
    status: stage.status,
    stage_progress: stage.progress,
    request: { ...run.request },
    created_at: run.createdAt,
    updated_at: now,
    warnings: stage.status === 'completed' ? [...MOCK_WARNINGS] : [],
    error_code: null,
    error_message: null,
  }
}

// ---------- 结果产物 ----------

function isObservedMode(run: MockRun): boolean {
  // online 没有匹配观测；precomputed 演示包含 observed（页面标「合成参考值」）
  return run.request.mode === 'precomputed'
}

const KNOWN_GENES = [
  'MYC', 'GATA1', 'TP53', 'BCL2', 'JUN', 'FOS', 'EGFR', 'KRAS', 'NRAS', 'AKT1',
  'MTOR', 'STAT3', 'JAK2', 'ABL1', 'CDK4', 'CDK6', 'RB1', 'PTEN', 'PIK3CA', 'MAPK1',
  'MAPK3', 'FOSB', 'JUNB', 'IRF1', 'NFKB1', 'RELA', 'SPI1', 'RUNX1', 'TAL1', 'GATA2',
  'KLF1', 'ETV6', 'FLT3', 'KIT', 'MPL', 'JAK3', 'SRC', 'LYN', 'SYK', 'BTK', 'VEGFA',
]

const GENE_COUNT = 320

function buildGenes(run: MockRun): GeneRow[] {
  const rng = mulberry32(run.request.seed * 7919 + 13)
  const observedMode = isObservedMode(run)
  const rows: GeneRow[] = []
  for (let i = 0; i < GENE_COUNT; i += 1) {
    const gene = i < KNOWN_GENES.length ? KNOWN_GENES[i] : `LOC${100000 + i}`
    const control = round(0.2 + rng() * 2.8)
    // 大部分变化较小，约 12% 显著
    let delta = (rng() + rng() + rng() - 1.5) * 0.6
    if (rng() < 0.12) delta *= 4
    const predicted = round(Math.max(0, control + delta))
    const predictedDelta = round(predicted - control)
    let observed: number | null = null
    let observedDelta: number | null = null
    if (observedMode) {
      const obsDelta = delta * 0.8 + (rng() - 0.5) * 0.15
      observed = round(Math.max(0, control + obsDelta))
      observedDelta = round(observed - control)
    }
    // 少量空值，演示「未提供」
    rows.push({
      gene,
      control,
      predicted: rng() < 0.04 ? null : predicted,
      predicted_delta: predictedDelta,
      observed: observedMode && rng() < 0.05 ? null : observed,
      observed_delta: observedMode && rng() < 0.05 ? null : observedDelta,
    })
  }
  return rows
}

export async function getGenes(runId: string, limit = 2000): Promise<GenesResponse> {
  await delay()
  const run = requireRun(runId, '/genes')
  const all = buildGenes(run)
  return {
    items: all.slice(0, limit),
    limit,
    truncated: all.length > limit,
  }
}

const TASK_SPECS: Array<{ label: string; level: EvidenceItem['evidence_level'] }> = [
  { label: 'Purine synthesis', level: 'supported' },
  { label: 'Glycolysis', level: 'supported' },
  { label: 'Pentose phosphate pathway', level: 'exploratory' },
  { label: 'Glutaminolysis', level: 'exploratory' },
  { label: 'One-carbon metabolism', level: 'exploratory' },
  { label: 'Serine synthesis', level: 'exploratory' },
  { label: 'Pyrimidine synthesis', level: 'exploratory' },
  { label: 'Fatty acid synthesis', level: 'exploratory' },
  { label: 'TCA cycle', level: 'insufficient' },
  { label: 'Oxidative phosphorylation', level: 'insufficient' },
  { label: 'Fatty acid oxidation', level: 'insufficient' },
  { label: 'Urea cycle', level: 'insufficient' },
  { label: 'Methionine cycle', level: 'insufficient' },
  { label: 'Cholesterol synthesis', level: 'insufficient' },
  { label: 'Heme synthesis', level: 'insufficient' },
  { label: 'NAD synthesis', level: 'insufficient' },
  { label: 'Glutathione synthesis', level: 'insufficient' },
  { label: 'Arginine metabolism', level: 'insufficient' },
  { label: 'Lysine degradation', level: 'insufficient' },
  { label: 'BCAA degradation', level: 'insufficient' },
]

function buildTasks(run: MockRun): EvidenceItem[] {
  const rng = mulberry32(run.request.seed * 104729 + 7)
  const observedMode = isObservedMode(run)
  return TASK_SPECS.map((spec, index) => {
    const delta = round((rng() - 0.5) * (spec.level === 'supported' ? 1.4 : 0.8))
    const coverage =
      spec.level === 'supported'
        ? round(0.82 + rng() * 0.15, 3)
        : spec.level === 'exploratory'
          ? round(0.4 + rng() * 0.25, 3)
          : round(0.05 + rng() * 0.2, 3)
    const geneCount = spec.level === 'insufficient' && index % 3 === 0 ? 0 : 2 + Math.floor(rng() * 3)
    const determinant = Array.from(
      { length: geneCount },
      () => KNOWN_GENES[Math.floor(rng() * KNOWN_GENES.length)],
    )
    return {
      id: `task_${String(index + 1).padStart(3, '0')}`,
      label: spec.label,
      predicted_delta: delta,
      observed_delta: observedMode ? round(delta * 0.85 + (rng() - 0.5) * 0.1) : null,
      coverage,
      evidence_level: spec.level,
      determinant_genes: [...new Set(determinant)],
    }
  })
}

export async function getMetabolicTasks(
  runId: string,
  limit = 1000,
): Promise<MetabolicTasksResponse> {
  await delay()
  const run = requireRun(runId, '/metabolic-tasks')
  const tasks = buildTasks(run)
  return { items: tasks.slice(0, limit), limit, truncated: tasks.length > limit }
}

const REACTION_NAMES = [
  'HEX1', 'GPI', 'PFK', 'FBA', 'TPI', 'GAPD', 'PGK', 'PGM', 'ENO', 'PYK',
  'LDH_L', 'PDH', 'CS', 'ACONT', 'ICDH', 'OGDH', 'SUCOAS', 'SUCD', 'FUM', 'MDH',
  'G6PD', 'PGL', 'GND', 'RPI', 'RPE', 'TKT1', 'TKT2', 'TALA', 'GLUD', 'GLNS',
  'ASNS', 'CAD', 'UMPS', 'ADSS', 'ADSL', 'IMPDH', 'PPAT', 'GART', 'ATIC', 'DHFR',
]

function buildReactions(run: MockRun): ReactionRow[] {
  const rng = mulberry32(run.request.seed * 31 + 3)
  const rows: ReactionRow[] = []
  const count = 60
  for (let i = 0; i < count; i += 1) {
    const reaction = i < REACTION_NAMES.length ? REACTION_NAMES[i] : `RXN${String(i).padStart(3, '0')}`
    const control = round(0.1 + rng() * 3)
    const delta = round((rng() + rng() - 1) * 0.9)
    rows.push({
      reaction,
      control,
      predicted: round(Math.max(0, control + delta)),
      predicted_delta: delta,
    })
  }
  return rows.sort((a, b) => Math.abs(b.predicted_delta ?? 0) - Math.abs(a.predicted_delta ?? 0))
}

export async function getReactions(runId: string, limit = 1000): Promise<ReactionsResponse> {
  await delay()
  const run = requireRun(runId, '/reactions')
  const all = buildReactions(run)
  return { items: all.slice(0, limit), limit, truncated: all.length > limit }
}

export async function getSummary(runId: string): Promise<RunSummary> {
  await delay()
  const run = requireRun(runId, '/summary')
  const genes = buildGenes(run)
  const topGenes: EvidenceItem[] = [...genes]
    .filter((g) => g.predicted_delta !== null)
    .sort((a, b) => Math.abs(b.predicted_delta ?? 0) - Math.abs(a.predicted_delta ?? 0))
    .slice(0, 8)
    .map((g, index) => ({
      id: g.gene,
      label: g.gene,
      predicted_delta: g.predicted_delta ?? 0,
      observed_delta: g.observed_delta,
      coverage: round(0.88 + (index % 5) * 0.02, 3),
      evidence_level: index < 5 ? 'supported' : 'exploratory',
      determinant_genes: [g.gene],
    }))
  return {
    run_id: runId,
    status: 'completed',
    stage_progress: 100,
    cell_line: run.request.cell_line,
    perturbation: run.request.perturbation,
    coverage: {
      state_gene_fraction: 1.0,
      metabolic_gene_fraction: 0.1407,
      reaction_fraction: 0.2016,
      supported_tasks: 7,
      exploratory_tasks: 2,
      insufficient_tasks: 209,
    },
    top_genes: topGenes,
    metabolic_tasks: buildTasks(run),
    warnings: [...MOCK_WARNINGS],
    error_code: null,
  }
}

function clusterPoints(
  rng: () => number,
  count: number,
  centerX: number,
  centerY: number,
  spread: number,
  source: ProjectionPoint['source'],
): ProjectionPoint[] {
  const points: ProjectionPoint[] = []
  for (let i = 0; i < count; i += 1) {
    // 近似正态：均匀分布求和
    const nx = rng() + rng() + rng() - 1.5
    const ny = rng() + rng() + rng() - 1.5
    points.push({
      x: round(centerX + nx * spread),
      y: round(centerY + ny * spread),
      source,
      cell_index: i,
    })
  }
  return points
}

export async function getProjection(runId: string): Promise<ProjectionResponse> {
  await delay()
  const run = requireRun(runId, '/projection')
  const rng = mulberry32(run.request.seed * 977 + 5)
  const points: ProjectionPoint[] = [
    ...clusterPoints(rng, 420, 0, 0, 1.6, 'control'),
    ...clusterPoints(rng, 380, 2.2, -1.1, 1.4, 'predicted'),
  ]
  if (isObservedMode(run)) {
    points.push(...clusterPoints(rng, 260, 1.9, -0.8, 1.5, 'observed'))
  }
  return { method: 'seeded-random-projection', seed: run.request.seed, points }
}

export async function downloadReport(runId: string): Promise<{ blob: Blob; filename: string }> {
  await delay()
  const run = requireRun(runId, '/report')
  const html = `<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>CellLens Mock 报告 ${runId}</title></head>
<body style="font-family: sans-serif; max-width: 720px; margin: 40px auto; line-height: 1.7">
  <h1>细胞知镜 · 运行报告（Mock 样例）</h1>
  <p><strong>运行编号：</strong>${runId}</p>
  <p><strong>细胞背景：</strong>${run.request.cell_line}　<strong>扰动：</strong>${run.request.perturbation}　<strong>模式：</strong>${run.request.mode}</p>
  <p><strong>n_cells：</strong>${run.request.n_cells}　<strong>seed：</strong>${run.request.seed}</p>
  <p style="color:#b45309">本报告由 Mock 演示模式生成，全部为样例数据，不能用于任何科学结论。</p>
  <h2>说明</h2>
  <p>真实报告由后端 GET /api/v1/runs/{run_id}/report 生成，包含运行信息、主要基因、任务与警告；
  尚未包含完整哈希与验证指标（见需求文档 B7）。</p>
</body>
</html>`
  return {
    blob: new Blob([html], { type: 'text/html;charset=utf-8' }),
    filename: `celllens-${runId}.html`,
  }
}
