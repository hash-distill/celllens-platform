import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'

const require = createRequire(import.meta.url), noop = () => {}
const source = readFileSync(new URL('../src/views/FigureWorkspaceView.vue', import.meta.url), 'utf8')
const flush = async () => { for (let i = 0; i < 4; i++) { await vue.nextTick(); await new Promise(setImmediate) } }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const svg = () => new Blob(['<svg xmlns="http://www.w3.org/2000/svg"><text>figure</text></svg>'], { type: 'image/svg+xml' })
const spec = (title = '') => ({ chart: 'projection', embedding: 'pca', gene: '', group: 'all', title, note: '', direction: 'both', limit: 10 })
const item = (title = '', fingerprint = 'hash') => ({ id: `saved-${title || 'default'}`, spec: spec(title), manifest_sha256: fingerprint, created_at: '2026-11-16T00:00:00Z' })
const fixture = () => ({ result: { background: { cell_line: 'K562' }, target: { perturbation: 'ALDOA' }, provenance: { manifest_sha256: 'hash' } }, genes: ['ALDOA', 'GAPDH'], availability: { projection: true, distribution: true, pathways: false }, reasons: { pathways: '没有冻结通路结果' } })
const renderer = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert: noop, remove: noop, setText: noop, setElementText: noop, patchProp: noop, parentNode: () => null, nextSibling: () => null })
function mount(options = {}) {
  const route = vue.reactive({ params: { recordKind: 'measured', recordId: 'first', ...options.params } })
  const accessSession = vue.ref({ mode: options.public ? 'public' : 'local', read_only: Boolean(options.public) }), calls = [], downloads = []
  const modules = { vue, 'vue-router': { useRoute: () => route }, '../stores/access': { accessSession }, '../utils/csv': { downloadBlob: (...args) => downloads.push(args) }, '../api/http': { apiFetch: (path, request = {}) => {
    calls.push({ path, ...request })
    if (options.request) { const response = options.request(path, request); if (response !== undefined) return response }
    if (path.endsWith('/context')) return Promise.resolve(options.context ?? fixture())
    if (path.endsWith('/saved') && request.method === 'POST') return Promise.resolve({ ...item(request.body.title), spec: request.body })
    if (path.endsWith('/saved')) return Promise.resolve({ items: options.items ?? [], total: options.items?.length ?? 0 })
    return Promise.resolve(svg())
  } } }
  const code = ts.transpileModule(compileScript(parse(source).descriptor, { id: 'figures-test' }).content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(name => modules[name] ?? require(name), module, module.exports)
  const component = module.exports.default; component.render = () => null
  const app = renderer.createApp(component), instance = app.mount({}).$
  return { app, state: instance.setupState, route, accessSession, calls, downloads }
}

test('initial preview uses available frozen chart; exports and saves use rendered settings despite unapplied draft', async () => {
  const h = mount()
  try {
    await flush(); assert.ok(h.state.previewUrl.startsWith('blob:')); assert.deepEqual({ ...h.state.renderedSpec }, spec())
    h.state.draft.title = 'unapplied'; h.state.draft.group = 'observed'; assert.equal(h.state.dirty, true)
    await h.state.exportFigure(); assert.deepEqual(h.calls.at(-1).body, spec()); assert.equal(h.downloads.length, 1)
    await h.state.saveFigure(); assert.deepEqual(h.calls.at(-1).body, spec()); assert.equal(h.state.saved[0].spec.title, '')
    await h.state.renderFigure(); assert.equal(h.state.renderedSpec.title, 'unapplied'); assert.equal(h.state.renderedSpec.group, 'observed'); assert.equal(h.state.dirty, false)
  } finally { h.app.unmount() }
})

test('saved recipes restore exactly and selected exports use immutable saved endpoint', async () => {
  const saved = item('saved title'), h = mount({ items: [saved, item('wrong', 'different')] })
  try {
    await flush(); await h.state.restore(saved)
    assert.deepEqual(h.state.draft, saved.spec); assert.deepEqual(h.state.renderedSpec, saved.spec); assert.equal(h.state.selectedId, saved.id)
    assert.equal(h.calls.at(-1).path, '/figures/measured/first/saved/saved-saved%20title/export')
    assert.equal(h.calls.at(-1).method, 'GET'); assert.equal(h.calls.at(-1).query.format, 'svg'); assert.equal(h.calls.at(-1).body, undefined)
    h.state.draft.title = 'different draft'; await h.state.exportFigure(true)
    assert.equal(h.calls.at(-1).path, '/figures/measured/first/saved/saved-saved%20title/export'); assert.equal(h.calls.at(-1).body, undefined)
    await h.state.exportFigure(); assert.equal(h.calls.at(-1).path, '/figures/measured/first/saved/saved-saved%20title/export')
    const beforeSave = h.calls.length; await h.state.saveFigure(); assert.equal(h.calls.length, beforeSave)
    const count = h.calls.length; await h.state.restore(h.state.saved[1]); assert.equal(h.calls.length, count)
    h.state.selectedId = 'saved-wrong'; await h.state.exportFigure(true); assert.equal(h.calls.length, count)
  } finally { h.app.unmount() }
})

test('saved source mismatch clears preview and retry never falls back to rendering current data', async () => {
  const saved = item('preserved'), h = mount({ items: [saved], request: path => path.endsWith('/export') ? Promise.reject(Error('图表来源指纹已变化')) : undefined })
  try {
    await flush(); assert.ok(h.state.previewUrl)
    const initialRenders = h.calls.filter(call => call.path.endsWith('/render')).length
    await h.state.restore(saved)
    assert.equal(h.state.previewUrl, ''); assert.equal(h.state.renderedSpec, null); assert.match(h.state.renderError, /指纹已变化/)
    await h.state.retryPreview(); assert.equal(h.calls.at(-1).method, 'GET'); assert.match(h.calls.at(-1).path, /\/saved\/saved-preserved\/export$/)
    assert.equal(h.calls.filter(call => call.path.endsWith('/render')).length, initialRenders)
    await h.state.exportFigure(); await h.state.saveFigure(); assert.equal(h.downloads.length, 0)
    h.state.draft.title = 'explicit fresh recipe'; await h.state.renderFigure()
    assert.equal(h.calls.at(-1).method, 'POST'); assert.equal(h.state.renderedSavedId, ''); assert.equal(h.state.failedRestore, null)
  } finally { h.app.unmount() }
})

test('late saved preview is discarded after a different record is selected', async () => {
  const d = deferred(), saved = item('waiting'), h = mount({ items: [saved], request: path => path.endsWith('/export') ? d.promise : undefined })
  try {
    await flush(); const restoring = h.state.restore(saved), request = h.calls.at(-1)
    h.route.params = { recordKind: 'prediction', recordId: 'second' }; await flush()
    assert.equal(request.signal.aborted, true); const currentUrl = h.state.previewUrl
    d.resolve(svg()); await restoring
    assert.equal(h.state.previewUrl, currentUrl); assert.equal(h.state.renderedSavedId, ''); assert.equal(h.state.recordId, 'second')
  } finally { h.app.unmount() }
})

test('metadata controls availability and gene validation without fabricating historical expression', async () => {
  const context = fixture(); context.availability.distribution = false; context.reasons.distribution = '历史结果没有逐细胞表达'
  const h = mount({ context })
  try {
    await flush(); h.state.chooseChart('distribution'); assert.equal(h.state.validDraft, false); assert.equal(h.state.reason, '历史结果没有逐细胞表达')
    const count = h.calls.length; await h.state.renderFigure(); assert.equal(h.calls.length, count)
    h.state.context.availability.distribution = true; h.state.draft.gene = 'NOT_IN_PANEL'; assert.equal(h.state.validDraft, false)
    h.state.draft.gene = 'GAPDH'; assert.equal(h.state.validDraft, true)
    h.state.chooseChart('pathways'); assert.equal(h.state.draft.gene, ''); assert.equal(h.state.draft.group, 'all'); assert.equal(h.state.validDraft, false)
    h.state.context.availability.pathways = true; h.state.draft.limit = 31; assert.equal(h.state.validDraft, false)
    h.state.draft.limit = 30; assert.equal(h.state.validDraft, true)
  } finally { h.app.unmount() }
})

test('a new render clears old preview and changing draft aborts pending renders', async () => {
  let pending, blocked = false
  const h = mount({ request: (path) => { if (blocked && path.endsWith('/render')) { pending = deferred(); return pending.promise } } })
  try {
    await flush(); blocked = true; const job = h.state.renderFigure(); assert.equal(h.state.previewUrl, ''); assert.equal(h.state.renderedSpec, null)
    const request = h.calls.at(-1); h.state.draft.embedding = 'umap'; assert.equal(request.signal.aborted, true); assert.equal(h.state.rendering, false)
    pending.resolve(svg()); await job; assert.equal(h.state.previewUrl, ''); assert.equal(h.state.renderedSpec, null)
  } finally { h.app.unmount() }
})

test('record switching clears snapshots and prevents stale render, export, and saved responses from being published', async () => {
  const pending = [], h = mount({ request: (path, opts) => { if (path.includes('/first/') && (path.endsWith('/render') || opts.method === 'POST')) { const d = deferred(); pending.push({ ...d, signal: opts.signal }); return d.promise } } })
  try {
    await flush(); assert.equal(pending.length, 1)
    h.route.params = { recordKind: 'prediction', recordId: 'second' }; assert.equal(h.state.previewUrl, ''); assert.equal(h.state.context, null)
    await flush(); assert.equal(pending[0].signal.aborted, true); pending[0].resolve(svg()); await flush()
    assert.ok(h.state.previewUrl); assert.equal(h.state.recordId, 'second'); assert.equal(h.state.resultLink, '/runs/second')
    assert.equal(h.downloads.length, 0)
  } finally { h.app.unmount() }
})

test('public mode makes zero private requests and transitioning to public aborts pending exports', async () => {
  const h = mount({ public: true })
  try { await flush(); await h.state.loadSaved(); await h.state.renderFigure(); await h.state.saveFigure(); await h.state.exportFigure(); assert.equal(h.calls.length, 0) } finally { h.app.unmount() }
  let pending, exporting = false
  const active = mount({ request: (path) => { if (exporting && path.endsWith('/render')) { pending = deferred(); return pending.promise } } })
  try {
    await flush(); exporting = true; const job = active.state.exportFigure(); const request = active.calls.at(-1)
    active.accessSession.value = { mode: 'public', read_only: true }; assert.equal(request.signal.aborted, true); assert.equal(active.state.context, null); assert.equal(active.state.previewUrl, '')
    pending.resolve(svg()); await job; assert.equal(active.downloads.length, 0)
  } finally { active.app.unmount() }
})

test('save errors require refreshing saved state before retry; render MIME errors remain visible and retryable', async () => {
  let failSave = true, badMime = false
  const h = mount({ request: (path, options) => {
    if (path.endsWith('/saved') && options.method === 'POST' && failSave) return Promise.reject(Error('network failure'))
    if (path.endsWith('/render') && badMime) return Promise.resolve(new Blob(['login'], { type: 'text/html' }))
  } })
  try {
    await flush(); await h.state.saveFigure(); assert.equal(h.state.saveUncertain, true); assert.match(h.state.actionError, /刷新图表清单/)
    const count = h.calls.length; await h.state.saveFigure(); assert.equal(h.calls.length, count)
    await h.state.loadSaved(); assert.equal(h.state.saveUncertain, false); failSave = false; await h.state.saveFigure(); assert.equal(h.state.saved.length, 1)
    badMime = true; await h.state.renderFigure(); assert.match(h.state.renderError, /文件类型/); assert.equal(h.state.renderedSpec, null)
    badMime = false; await h.state.renderFigure(); assert.equal(h.state.renderError, ''); assert.ok(h.state.previewUrl)
  } finally { h.app.unmount() }
})

test('invalid identities do not call APIs and unmount aborts in-flight context', async () => {
  const invalid = mount({ params: { recordKind: 'unknown' } })
  try { await flush(); assert.equal(invalid.calls.length, 0); assert.match(invalid.state.loadError, /研究标识无效/) } finally { invalid.app.unmount() }
  const d = deferred(), h = mount({ request: () => d.promise }); const request = h.calls[0]
  h.app.unmount(); assert.equal(request.signal.aborted, true); d.resolve(fixture()); await flush(); assert.equal(h.state.context, null)
})

test('whole report exports all saved figures via GET and ignores stale responses after record changes', async () => {
  let pending = null
  const h = mount({ items: [item('first'), item('second')], request: path => path.endsWith('/report')
    ? pending?.promise ?? Promise.resolve(new Blob(['<!doctype html><html>saved report</html>'], { type: 'text/html' })) : undefined })
  try {
    await flush(); h.state.draft.title = 'unapplied draft'; await h.state.exportReport()
    assert.equal(h.calls.at(-1).path, '/figures/measured/first/report')
    assert.equal(h.calls.at(-1).method, 'GET'); assert.equal(h.calls.at(-1).query.format, 'html'); assert.equal(h.calls.at(-1).body, undefined)
    assert.equal(h.downloads[0][1], 'CellLens-report-first.html')
    h.state.saved = Array.from({ length: 21 }, (_, i) => item(String(i)))
    const count = h.calls.length; await h.state.exportReport(); assert.equal(h.calls.length, count)
    h.state.saved = []; await h.state.exportReport(); assert.equal(h.calls.length, count)
    h.state.saved = [item('first')]; h.state.reportFormat = 'zip'; pending = deferred()
    const exporting = h.state.exportReport(), request = h.calls.at(-1)
    assert.equal(request.query.format, 'zip')
    h.route.params = { recordKind: 'prediction', recordId: 'second' }; await flush()
    assert.equal(request.signal.aborted, true)
    pending.resolve(new Blob(['PK'], { type: 'application/zip' })); await exporting
    assert.equal(h.downloads.length, 1); assert.equal(h.state.exporting, false)
    h.accessSession.value = { read_only: true }; const publicCount = h.calls.length
    await h.state.exportReport(); assert.equal(h.calls.length, publicCount)
  } finally { h.app.unmount() }
})

test('confirmed removal deletes only a saved recipe, reloads list, clears its preview and ignores stale completion', async () => {
  const first = item('remove me'), second = item('keep me'); let rows = [first, second]
  const h = mount({ request: (path, request) => {
    if (request.method === 'DELETE') { rows = rows.filter(row => row.id !== first.id); return Promise.resolve(null) }
    if (path.endsWith('/saved') && request.method !== 'POST') return Promise.resolve({ items: rows, total: rows.length })
  } })
  try {
    await flush(); await h.state.restore(first); const count = h.calls.length
    await h.state.removeFigure(first); assert.equal(h.calls.length, count, 'A first click must not delete')
    h.state.exporting = true; h.state.requestRemoval(first); assert.equal(h.state.confirmingRemoval, '')
    h.state.exporting = false; h.state.requestRemoval(first); assert.equal(h.state.confirmingRemoval, first.id)
    await h.state.removeFigure(first)
    const writes = h.calls.filter(call => call.method === 'DELETE')
    assert.equal(writes.length, 1); assert.equal(writes[0].path, '/figures/measured/first/saved/saved-remove%20me'); assert.equal(writes[0].body, undefined)
    assert.equal(h.calls.at(-1).path, '/figures/measured/first/saved')
    assert.deepEqual(h.state.saved.map(row => row.id), [second.id]); assert.equal(h.state.selectedId, '')
    assert.equal(h.state.previewUrl, ''); assert.equal(h.state.renderedSavedId, ''); assert.equal(h.state.renderedSpec, null)
    assert.match(h.state.notice, /原始分析结果保持不变/)
    assert.equal(h.calls.some(call => call.method === 'DELETE' && !call.path.includes('/saved/')), false)
  } finally { h.app.unmount() }
  const pending = deferred(), stale = mount({ items: [first], request: (_path, request) => request.method === 'DELETE' ? pending.promise : undefined })
  try {
    await flush(); stale.state.requestRemoval(first); const deleting = stale.state.removeFigure(first), request = stale.calls.at(-1)
    stale.accessSession.value = { read_only: true }; assert.equal(request.signal.aborted, true)
    pending.resolve(null); await deleting; assert.equal(stale.state.context, null); assert.equal(stale.state.saved.length, 0); assert.equal(stale.state.notice, '')
  } finally { stale.app.unmount() }
})
