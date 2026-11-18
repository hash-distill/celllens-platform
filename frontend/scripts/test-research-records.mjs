import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import ts from 'typescript'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
const compiled = ts.transpileModule(source('utils/researchRecords.ts'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText
const { measuredRecord, predictedRecord, selectRecords, collectRecordPages } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))
const measured = (id, status = 'completed', created_at = '2026-10-22T12:00:00') => measuredRecord({ id, status, created_at, cell_line: 'K562', perturbation: 'ALDOA', max_cells: 128, progress: 100 })
const predicted = (id, status = 'completed', created_at = '2026-10-22T11:00:00+00:00', synthetic = false) => predictedRecord({ id, status, created_at, title: 'RPE1 / TP53 扰动实验', subtitle: '请求 64 个预测细胞', run: { stage_progress: 100, result_kind: synthetic ? 'synthetic_demo' : null } })
const filters = { category: 'all', status: 'all', query: '', resultsOnly: false }

test('mixed history keeps source identity and correct detail routes, including synthetic evidence', () => {
  const observed = measured('same'), prediction = predicted('same')
  assert.notEqual(observed.key, prediction.key)
  assert.equal(observed.target, '/measured/same')
  assert.equal(prediction.target, '/runs/same')
  assert.equal(observed.sourceLabel, '公开实测')
  assert.equal(prediction.sourceLabel, '模型预测')
  assert.equal(predicted('demo', 'completed', undefined, true).sourceLabel, '合成示例')
})

test('merge order uses UTC database timestamps, with stable ties, before filtering and pagination', () => {
  const records = [predicted('older'), measured('newer'), predicted('newest', 'completed', '2026-10-22T21:00:00+08:00')]
  assert.deepEqual(selectRecords(records, filters).map(record => record.id), ['newest', 'newer', 'older'])
  assert.equal(records[0].id, 'older')
  const tied = [predicted('same'), measured('same', 'completed', '2026-10-22T11:00:00')]
  assert.deepEqual(selectRecords(tied, filters), selectRecords([...tied].reverse(), filters))
})

test('category, case-insensitive search and completed-result filters apply to both sources', () => {
  const records = [measured('done'), measured('waiting', 'queued'), measured('stopped', 'cancelled'), measured('lost', 'interrupted'), predicted('failed', 'failed'), predicted('prediction')]
  assert.equal(selectRecords(records, { ...filters, category: 'measured' }).length, 4)
  assert.deepEqual(selectRecords(records, { ...filters, query: ' aldoa ', status: 'completed' }).map(record => record.id), ['done'])
  assert.deepEqual(selectRecords(records, { ...filters, status: 'active' }).map(record => record.id), ['waiting'])
  assert.equal(selectRecords(records, { ...filters, status: 'cancelled' })[0].id, 'stopped')
  assert.equal(selectRecords(records, { ...filters, status: 'interrupted' })[0].id, 'lost')
  assert.equal(selectRecords(records, { ...filters, resultsOnly: true }).length, 2)
})

test('all source pages are loaded, not just the first page of each category', async () => {
  const rows = Array.from({ length: 205 }, (_, index) => ({ id: String(index) }))
  const offsets = []
  const result = await collectRecordPages(async (limit, offset) => {
    offsets.push(offset)
    return { items: rows.slice(offset, offset + limit), total: rows.length }
  })
  assert.equal(result.length, 205)
  assert.deepEqual(offsets, [0, 100, 200])
})

test('partial, shifting and cancelled responses never masquerade as complete history', async () => {
  await assert.rejects(collectRecordPages(async () => ({ items: [], total: 1 })), /刷新/)
  await assert.rejects(collectRecordPages(async (_limit, offset) => ({ items: [{ id: String(offset) }], total: offset ? 3 : 2 })), /刷新/)
  await assert.rejects(collectRecordPages(async () => ({ items: [{ id: 'duplicate' }], total: 2 })), /刷新/)
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(collectRecordPages(async () => { throw new Error('must not fetch') }, controller.signal), { name: 'AbortError' })
})

test('approved navigation keeps research, coverage and one source-filterable record table', () => {
  const header = source('components/AppHeader.vue'), records = source('views/RecordsView.vue')
  for (const label of ['研究概览', '研究工作台', '数据图谱', '实验记录']) assert.ok(header.includes(label), `Missing approved navigation: ${label}`)
  assert.match(source('components/SectionNavigation.vue'), /records\?status=completed/)
  assert.doesNotMatch(source('components/SectionNavigation.vue'), /已完成结果/)
  assert.match(records, /id="record-status"/)
  assert.doesNotMatch(records, /RESULT INTERPRETATION|只看完成结果|已完成研究/)
  assert.match(records, /id="record-category"/)
  assert.doesNotMatch(records, /<MeasuredHistory|实验分析<|加入比较</)
  assert.doesNotMatch(source('components/SectionNavigation.vue'), /label:'实测记录'|label:'预测记录'/)
  assert.doesNotMatch(source('components/MeasuredHistory.vue'), /打开分析/)
})

test('private measured records preserve input provenance instead of claiming public data', () => {
  const base = { id: 'private', status: 'completed', cell_line: 'K562', perturbation: 'ALDOA', max_cells: 128, progress: 100, created_at: '2026-11-07T12:00:00' }
  assert.equal(measuredRecord({ ...base, import_id: 'frozen-import' }).sourceLabel, '自有实测')
  assert.equal(measuredRecord({ ...base, source: { type: 'controlled_private_h5ad' } }).sourceLabel, '自有实测')
  assert.equal(measuredRecord({ ...base, summary: { provenance: { source: { kind: 'controlled_private_h5ad' } } } }).sourceLabel, '自有实测')
  assert.equal(measuredRecord({ ...base, source: { type: 'measured_rna' } }).sourceLabel, '公开实测')
})


test('cancelled predictions are listed and filtered as cancelled while real failures stay failed', () => {
  const base={id:'cancelled-run',status:'failed',created_at:'2026-11-07T12:00:00',title:'K562 / GENE',subtitle:'run',run:{stage_progress:28,error_code:'RUN_CANCELLED'}}
  const cancelled=predictedRecord(base)
  const failed=predictedRecord({...base,id:'failed-run',run:{...base.run,error_code:'EXECUTION_FAILED'}})
  assert.equal(cancelled.status,'cancelled')
  assert.equal(failed.status,'failed')
  assert.deepEqual(selectRecords([cancelled,failed],{...filters,status:'failed'}).map(row=>row.id),['failed-run'])
  assert.deepEqual(selectRecords([cancelled,failed],{...filters,status:'cancelled'}).map(row=>row.id),['cancelled-run'])
  assert.equal(selectRecords([cancelled],{...filters,status:'active'}).length,0)
})
