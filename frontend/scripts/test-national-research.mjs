import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'

// Executes real setup/watch/lifecycle code with Vue's renderer. No browser, network,
// WebGL, datasets or scientific fixtures are substituted into the application.
const require = createRequire(import.meta.url)
const noop = () => {}
const never = () => new Promise(noop)
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const flush = async () => { await vue.nextTick(); await new Promise(setImmediate); await vue.nextTick() }
const source = name => readFileSync(new URL(`../src/${name}`, import.meta.url), 'utf8')
class RequestError extends Error { constructor(kind, text) { super(text); this.kind = kind } }
const renderer = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert: noop, remove: noop, setText: noop, setElementText: noop, patchProp: noop, parentNode: () => null, nextSibling: () => null })
function evaluate(text, modules) {
  const code = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(name => modules[name] ?? (name.endsWith('.vue') ? {} : require(name)), module, module.exports)
  return module.exports
}
function mount(name, properties = {}, overrides = {}, events = []) {
  const route = vue.reactive({ path: '/research', query: {}, params: {} })
  const router = { push: async location => { route.path = typeof location === 'string' ? location : location.path }, replace: async location => { route.path = location.path; route.query = location.query ?? {} } }
  const draft = vue.reactive({ cellLine: 'K562', perturbation: '', measuredMaxCells: '256', measuredSeed: '42', seed: '42', measuredSubmitting: false, setCellLine(value) { this.cellLine = value } })
  const modules = {
    'vue': vue, 'vue-router': { useRoute: () => route, useRouter: () => router },
    '../api/uploads': { uploadH5ad: never },
    '../api/http': { apiFetch: never, ApiError: RequestError }, '../api/measured': { measuredApi: { get: never, table: never, projection: never } },
    '../stores/access': { accessSession: vue.ref({ mode: 'local', authenticated: true, read_only: false }) },
    '../stores/run': { useRunStore: () => ({ submitting: false, entry: () => null, leaveRun: noop, openRun: noop, ensureTabData: noop }) },
    '../stores/recent': { useRecentStore: () => ({ add: noop }) }, '../stores/candidates': { useCandidatesStore: () => ({ items: [], has: () => false }) },
    '../stores/draft': { useDraftStore: () => draft }, '../stores/ui': { useUiStore: () => ({ push: noop }) },
    '../stores/assistantSource': { useAssistantSource: noop, openAssistant: noop },
    '../utils/format': { fmtServerTime: value => value, STATUS_LABEL: {} }, '../utils/biologyLocale': { taskName: value => value, metabolicGroupName: value => value || '未提供功能分类' },
    '../utils/csv': { downloadBlob: noop }, '../utils/source': { isSyntheticResult: () => false, runSourceLabel: () => '模型预测' },
    '../utils/number': { isIntegerInRange: (value, min, max) => Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max },
    '../api/client': { api: {} }, ...overrides,
  }
  const descriptor = parse(source(name)).descriptor
  const component = evaluate(compileScript(descriptor, { id: name }).content, modules).default
  component.render = () => null
  const listeners = Object.fromEntries(['ready', 'review-change', 'busy-change'].map(name => [`on${name.split('-').map(x => x[0].toUpperCase() + x.slice(1)).join('')}`, value => events.push([name, value])]))
  const app = renderer.createApp(component, { ...properties, ...listeners })
  const instance = app.mount({}).$
  return { app, state: instance.setupState, props: instance.props, route, router, draft, modules }
}
const session = authenticated => ({ mode: 'private', authenticated, configured: true, read_only: false, public_result_ids: [] })
const record = overrides => ({ id: 'measured-old', cell_line: 'K562', perturbation: 'GENE', max_cells: 64, seed: 3, status: 'failed', progress: 0, summary: null, source_kind: 'measured', ...overrides })

test('both result views map visible tabs to backend selection enums and preserve exact selected IDs', async () => {
  const a = mount('views/WorkbenchView.vue')
  const b = mount('views/MeasuredAnalysisView.vue')
  try {
    for (const [tab, layer] of [['overview', 'expression'], ['genes', 'expression'], ['metabolism', 'function'], ['comparison', 'expression'], ['cell', 'expression'], ['validation', 'expression']]) {
      a.route.query = { tab, gene: 'GENE_exact', task: 'TASK_exact' }
      assert.equal(a.state.researchSelection.layer, layer)
      assert.equal(a.state.researchSelection.gene_id, 'GENE_exact')
      assert.equal(a.state.researchSelection.task_id, 'TASK_exact')
    }
    for (const [tab, layer] of [['overview', 'expression'], ['genes', 'expression'], ['metabolism', 'function'], ['comparison', 'expression']]) {
      b.route.query = { tab }
      await flush()
      b.state.selectedFeature = { view: tab, feature_kind: 'task', feature_id: 'TASK_exact' }
      assert.deepEqual(b.state.researchSelection, { gene_id: undefined, task_id: 'TASK_exact', layer, ...(tab === 'genes' ? {projection_id:'pca'} : {}) })
    }
    b.state.overviewTasks = [{ task: 'TASK_exact', category: 'Energy metabolism', control: 0, observed: 2, observed_delta: 2, gene_fraction: 0.7 }]
    assert.equal(b.state.overviewTaskRows[0].category, 'Energy metabolism', 'Frozen task metadata must reach the overview category display')
    assert.equal(b.state.overviewTaskRows[0].control, 0, 'A category display must preserve true zero scores')
    assert.equal(b.state.overviewTaskRows[0].rawCategory, 'Energy metabolism', 'Structure association must retain untranslated frozen metadata')
    for (const h of [a,b]) {
      h.route.query = {tab:'overview'}
      h.state.canvasSelection = {layer:'expression',projection_id:'umap',group_id:'observed'}
      assert.equal(h.state.researchSelection.projection_id,'umap')
      assert.equal(h.state.researchSelection.group_id,'observed')
      h.route.query = {tab:'metabolism'}
      assert.equal(h.state.researchSelection.projection_id,undefined,'Function evidence must not inherit the last visible projection')
      assert.equal(h.state.researchSelection.group_id,undefined,'Function evidence must not inherit the last visible population filter')
    }
  } finally { a.app.unmount(); b.app.unmount() }
})

test('imported K562 retry retains its frozen import identity and never queries the public catalog', async () => {
  const calls = [], navigation = []
  const h = mount('views/MeasuredAnalysisView.vue', {}, {
    '../api/http': { ApiError: RequestError, apiFetch: async (path, options) => { calls.push([path, options]); return { id: 'measured-new' } } },
    '../api/measured': { measuredApi: { coverage: () => { throw new Error('Imported input must not query public coverage') }, create: () => { throw new Error('Imported input must not create a public request') } } },
    'vue-router': { useRoute: () => vue.reactive({ path: '/measured/old', params: {}, query: {} }), useRouter: () => ({ push: async to => navigation.push(to) }) },
  })
  try {
    h.state.selected = record({ import_id: 'import/frozen', source: { type: 'controlled_private_h5ad' } })
    await h.state.retry()
    assert.equal(calls[0][0], '/research/imports/import%2Ffrozen/analyses')
    assert.equal(calls[0][1].method, 'POST')
    assert.equal(navigation[0], '/measured/measured-new')
    h.state.selected = record({ source: { type: 'controlled_private_h5ad' } })
    await h.state.retry()
    assert.equal(calls.length, 1, 'Missing import version cannot silently turn into a public K562 analysis')
    assert.equal(h.state.missingImport, true)
    assert.match(h.state.actionError, /自有数据版本/)
    h.state.selected = record({ cell_line: 'MyPrimaryCells' })
    await h.state.retry()
    assert.equal(calls.length, 1, 'Unregistered private backgrounds must never be forced into a public request')
  } finally { h.app.unmount() }
})

test('public measured retry still revalidates coverage and preserves sampling parameters', async () => {
  const calls = []
  const h = mount('views/MeasuredAnalysisView.vue', {}, { '../api/measured': { measuredApi: {
    coverage: async (...args) => { calls.push(['coverage', ...args]); return { source_status: 'measured' } },
    create: async payload => { calls.push(['create', payload]); return { id: 'new-public' } },
  } } })
  try {
    h.state.selected = record({ source: { type: 'measured_rna' } })
    await h.state.retry()
    assert.deepEqual(calls[0].slice(0, 3), ['coverage', 'K562', 'GENE'])
    assert.deepEqual(calls[1], ['create', { cell_line: 'K562', perturbation: 'GENE', max_cells: 64, seed: 3 }])
  } finally { h.app.unmount() }
})

function evidenceHarness() {
  const reads = [], saves = [], exports = [], downloads = []
  const accessSession = vue.ref({ mode: 'local', read_only: false })
  const api = {
    result: (kind, id, signal) => { const pending = deferred(); reads.push({ kind, id, signal, ...pending }); return pending.promise },
    findings: async () => ({ items: [] }),
    save: (kind, id, selection, note, signal) => { const pending = deferred(); saves.push({ kind, id, selection, note, signal, ...pending }); return pending.promise },
    export: (kind, id, signal) => { const pending = deferred(); exports.push({ kind, id, signal, ...pending }); return pending.promise },
  }
  const h = mount('components/ResearchEvidence.vue', { kind: 'measured', recordId: 'first', completed: true, selection: { gene_id: 'EXACT', layer: 'expression' } }, {
    '../api/research': { researchApi: api }, '../stores/access': { accessSession }, '../utils/csv': { downloadBlob: (...values) => downloads.push(values) },
  })
  return { ...h, reads, saves, exports, downloads, accessSession }
}

test('findings snapshot the selected evidence, abort old saves on record change and ignore late responses', async () => {
  const h = evidenceHarness()
  try {
    h.state.note = 'A research observation'
    const saving = h.state.save()
    assert.deepEqual(h.saves[0].selection, { gene_id: 'EXACT', layer: 'expression' })
    h.props.selection = { task_id: 'OTHER', layer: 'function' }
    assert.equal(h.saves[0].selection.gene_id, 'EXACT', 'An in-flight finding must retain its original evidence selection')
    h.props.recordId = 'second'
    await flush()
    assert.equal(h.saves[0].signal.aborted, true)
    assert.equal(h.reads[0].signal.aborted, true)
    assert.equal(h.state.saving, false)
    h.saves[0].resolve({ id: 'old-finding', note: 'old' })
    h.reads[0].resolve({ record_id: 'first' })
    await saving; await flush()
    assert.deepEqual(h.state.findings, [])
    assert.equal(h.state.result, null)
    h.reads[1].resolve({ record_id: 'second' })
    await flush()
    assert.equal(h.state.result.record_id, 'second')
  } finally { h.app.unmount() }
})

test('record exports are cancelled on source-kind changes even when IDs are identical', async () => {
  const h = evidenceHarness()
  try {
    const exporting = h.state.exportRecord()
    h.props.kind = 'prediction'
    await flush()
    assert.equal(h.exports[0].signal.aborted, true)
    assert.equal(h.state.busy, false)
    h.exports[0].resolve({ record_id: 'first', source_kind: 'measured' })
    await exporting
    assert.equal(h.downloads.length, 0, 'A stale source export must never download as the current research')
  } finally { h.app.unmount() }
})

test('evidence labels distinguish measured groups from model diagnostics without rewriting source values', () => {
  const h = evidenceHarness()
  try {
    assert.equal(h.state.sourceLabel('measured'), '实测数据')
    assert.equal(h.state.sourceLabel('prediction'), '模型预测')
    assert.equal(h.state.sourceLabel('synthetic_demo'), '合成演示')
    assert.equal(h.state.availabilityLabels.comparison, '模型与实测诊断')
    assert.match(source('components/ResearchEvidence.vue'), /本页「实验对照」展示实测对照组与扰动组的描述性比较/)
    assert.equal(h.state.unitLabels.function, '功能支持评分尺度')
  } finally { h.app.unmount() }
})

test('latest access inspection wins over an older authenticated response and unmount aborts inspection', async () => {
  const calls = [], accessSession = vue.ref(null), events = []
  const h = mount('components/AccessGate.vue', {}, {
    '../stores/access': { accessSession }, '../api/http': { apiFetch: (_path, options) => { const task = deferred(); calls.push({ ...task, signal: options.signal }); return task.promise } },
  }, events)
  try {
    const current = h.state.inspect()
    calls[1].resolve(session(false)); await current
    calls[0].resolve(session(true)); await flush()
    assert.equal(accessSession.value.authenticated, false, 'The first request must not reopen a newer locked workspace')
    assert.equal(events.some(([name]) => name === 'ready'), false)
    const pending = h.state.inspect()
    h.app.unmount()
    assert.equal(calls[2].signal.aborted, true)
    calls[2].resolve(session(true)); await pending
    assert.equal(accessSession.value.authenticated, false, 'Unmounted checks must not update the shared session')
  } finally { h.app.unmount() }
})

test('logout failures stay visible and keep the current workspace instead of rejecting silently', async () => {
  const accessSession = vue.ref(session(true))
  const h = mount('components/AccessGate.vue', {}, {
    '../stores/access': { accessSession }, '../api/http': { apiFetch: async (_path, options) => { if (options.method === 'DELETE') throw new Error('logout unavailable'); return session(true) } },
  })
  try {
    await flush()
    await assert.doesNotReject(h.state.logout())
    assert.match(h.state.error, /logout unavailable/)
    assert.equal(accessSession.value.authenticated, true)
  } finally { h.app.unmount() }
})

test('browser navigation between research paths resets review step and in-flight import locks path buttons', async () => {
  const h = mount('views/ResearchView.vue')
  try {
    h.route.query = { type: 'measured' }; await flush()
    h.state.reviewing = true
    assert.equal(h.state.step, 3)
    h.route.query = { type: 'import' }; await flush()
    assert.equal(h.state.step, 2, 'A review from the previous path is not a review of imported data')
    h.state.importBusy = true
    assert.equal(h.state.locked, true)
  } finally { h.app.unmount() }
})

test('controlled import exposes pending validation and aborts it after unmount', async () => {
  const events = [], pending = deferred(), calls = [], navigation = []
  const h = mount('components/ControlledImport.vue', {}, {
    '../api/http': { ApiError: RequestError, apiFetch: (path, options) => {
      if (path.endsWith('capabilities')) return Promise.resolve({ available: true })
      calls.push({ path, options }); return pending.promise
    } },
    'vue-router': { useRouter: () => ({ push: async to => navigation.push(to) }) },
  }, events)
  try {
    await flush()
    h.state.upload = { upload_id: 'sample-upload', obs_columns: [{ name:'condition', truncated:false, values:[{label:'control',count:30},{label:'GENE',count:30}] }] }
    Object.assign(h.state.form, { group_key:'condition', control_label:'control', target_label:'GENE', perturbation:'GENE', cell_line:'K562', expression_scale:'cp10k' })
    const checking = h.state.inspect(); await flush()
    assert.ok(events.some(([name, busy]) => name === 'busy-change' && busy === true), 'Parent must know validation is in flight')
    h.app.unmount()
    assert.equal(calls[0].options.signal.aborted, true)
    pending.resolve({ import_id: 'frozen-version' }); await checking
    assert.equal(navigation.length, 0)
    assert.equal(events.at(-1)[1], false, 'Parent lock must release when import component leaves')
  } finally { h.app.unmount() }
})

test('uncertain imported analysis submission prevents duplicate creation and keeps parent informed', async () => {
  const events = [], pending = deferred(), calls = []
  const h = mount('components/ControlledImport.vue', {}, {
    '../api/http': { ApiError: RequestError, apiFetch: (path, options) => {
      if (path.endsWith('capabilities')) return Promise.resolve({ available: true })
      calls.push({ path, options }); return pending.promise
    } },
  }, events)
  try {
    await flush()
    h.state.result = { import_id: 'immutable-input' }
    h.state.review(true)
    const submission = h.state.create()
    assert.ok(events.some(([name, busy]) => name === 'busy-change' && busy === true))
    assert.equal(calls[0].path, '/research/imports/immutable-input/analyses')
    pending.reject(new RequestError('timeout', 'Submission response timed out'))
    await submission
    assert.equal(h.state.uncertain, true)
    assert.equal(h.state.creating, false)
    await h.state.create()
    assert.equal(calls.length, 1, 'A timeout must not automatically resubmit an analysis that may already exist')
    assert.equal(events.at(-1)[1], false)
  } finally { h.app.unmount() }
})

test('readiness consumes worker capabilities separately from browsing readiness and drops stale probes', async () => {
  const { createPinia, setActivePinia } = require('pinia')
  setActivePinia(createPinia())
  let response = { httpStatus: 200, body: { ready: true, checks: { database: true }, capabilities: { result_browsing: true, cpu_analysis: true, prediction: false }, workers: { mode: 'external', live: [], cpu_available: true, prediction_available: false } } }
  const api = { health: async () => ({ status: 'ok', database: 'connected' }), ready: async () => { if (response instanceof Error) throw response; return response } }
  const { useServiceStore } = evaluate(source('stores/service.ts'), { '../api/client': { api }, '../api/http': { ApiError: RequestError } })
  const store = useServiceStore()
  await store.refresh()
  assert.equal(store.level, 'ok', 'A database-ready service can still browse frozen results without prediction workers')
  assert.equal(store.capabilities?.cpu_analysis, true)
  assert.equal(store.capabilities?.prediction, false, 'Hardware availability must not synthesize prediction readiness')
  response = { httpStatus: 200, body: { ready: true, checks: { database: true, worker: true, gpu: true } } }
  await store.refresh()
  assert.equal(store.capabilities, null, 'Legacy config flags are not live worker capability evidence')
  response = { httpStatus: 200, body: { ready: true, checks: { database: true }, capabilities: { cpu_analysis: true, prediction: true, result_browsing: true } } }
  await store.refresh()
  response = new RequestError('network', 'connection lost')
  await store.refresh()
  assert.equal(store.capabilities, null, 'A failed probe must not keep showing the previous worker as live')
})


test('public workspace startup skips private catalog preloading while preserving service readiness', () => {
  const previousDocument = globalThis.document
  globalThis.document = { addEventListener: noop, removeEventListener: noop }
  const accessSession = vue.ref({mode:'public',read_only:true})
  let readiness = 0, catalog = 0
  const h = mount('App.vue', {}, {
    './stores/access': { accessSession }, './stores/service': { useServiceStore: () => ({refresh: () => readiness++}) },
    './stores/catalog': { useCatalogStore: () => ({load: () => catalog++}) }, './stores/run': {useRunStore: () => ({wakePolling:noop})},
    './stores/ui': {useUiStore: () => ({})}, './api/mockFlag': {isMockEnabled: () => false},
    './stores/assistantSource': {assistantOpen:vue.ref(false),assistantSource:vue.ref(null)},
  })
  try {
    h.state.workspaceReady()
    assert.equal(readiness,1)
    assert.equal(catalog,0,'Public startup must not call /catalog/contexts')
    accessSession.value = {mode:'private',read_only:false}
    h.state.workspaceReady()
    assert.equal(catalog,1,'Private research still loads supported contexts')
  } finally { h.app.unmount(); if(previousDocument===undefined)delete globalThis.document;else globalThis.document=previousDocument }
})

test('public data catalog exposes only published backgrounds and blocks private CSV requests', async () => {
  let downloads=0
  const h=mount('views/DataCatalogView.vue',{}, {
    '../stores/access':{accessSession:vue.ref({mode:'public',read_only:true})},
    '../api/dataCatalog':{dataCatalogApi:{query:async()=>({items:[],total:0,summary:{contexts:[{cell_line:'K562'}]}}),download:async()=>{downloads++}}},
  })
  try {
    await flush()
    assert.deepEqual(h.state.contexts,['K562'],'Unpublished backgrounds cannot be presented as full atlas coverage')
    await h.state.download()
    assert.equal(downloads,0)
  } finally {h.app.unmount()}
})

test('prediction cancellation prevents duplicate POSTs, refreshes actual state and remains blocked publicly', async () => {
  const entry=vue.reactive({record:{run_id:'running',status:'state_running',warnings:[],error_code:null,request:{cell_line:'K562',perturbation:'GENE',mode:'online'}}})
  const calls=[],refreshes=[],accessSession=vue.ref({mode:'local',read_only:false})
  const h=mount('views/WorkbenchView.vue',{}, {
    '../stores/access':{accessSession},
    '../stores/run':{useRunStore:()=>({entry:()=>entry,openRun:noop,leaveRun:noop,ensureTabData:noop,refreshRecord:async id=>{refreshes.push(id);entry.record.status='failed';entry.record.error_code='RUN_CANCELLED'}})},
    '../api/http':{apiFetch:(path,options)=>{const pending=deferred();calls.push({path,options,...pending});return pending.promise}},
  })
  try {
    h.route.params={runId:'running'}
    const cancelling=h.state.cancelRun()
    await h.state.cancelRun()
    assert.equal(calls.length,1)
    assert.equal(calls[0].path,'/runs/running/cancel')
    assert.equal(calls[0].options.method,'POST')
    calls[0].resolve({...entry.record,status:'failed',error_code:'RUN_CANCELLED'})
    await cancelling
    assert.deepEqual(refreshes,['running'])
    assert.equal(h.state.cancelled,true)
    assert.equal(h.state.cancelling,false)
    assert.match(h.state.cancelNote,/已取消/)
    entry.record.status='state_running';entry.record.error_code=null
    const failing=h.state.cancelRun()
    calls[1].reject(new Error('Connection lost'));await failing
    assert.match(h.state.cancelError,/Connection lost.*刷新/)
    accessSession.value={mode:'public',read_only:true}
    await h.state.cancelRun()
    assert.equal(calls.length,2,'Public mode must never send a cancellation')
  } finally {h.app.unmount()}
})

test('cancelled prediction progress is neutral and does not claim an execution failure', () => {
  const failed={run_id:'cancelled',status:'failed',stage_progress:28,error_code:'RUN_CANCELLED',warnings:[]}
  const h=mount('components/StageProgress.vue',{record:failed},{'../utils/format':{STATUS_LABEL:{failed:'分析失败'}}})
  try {
    assert.equal(h.state.statusText,'已取消')
    assert.equal(h.state.fillClass,'cancelled')
    assert.equal(h.state.currentIndex,-1)
    h.props.record={...failed,error_code:'EXECUTION_FAILED'}
    assert.equal(h.state.statusText,'分析失败')
    assert.equal(h.state.fillClass,'failed','Genuine failures must retain their failure state')
  } finally {h.app.unmount()}
})
