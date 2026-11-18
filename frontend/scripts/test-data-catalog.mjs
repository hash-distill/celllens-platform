import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'

const require = createRequire(import.meta.url), noop = () => {}
const source = readFileSync(new URL('../src/views/DataCatalogView.vue', import.meta.url), 'utf8')
const flush = async () => { await vue.nextTick(); await new Promise(setImmediate); await vue.nextTick() }
const settle = async () => { await flush(); await new Promise(resolve => setTimeout(resolve, 200)); await flush() }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const fixture = (name = 'ALDOA', total = 31) => ({ items: [{ cell_line: 'K562', perturbation: name, source_status: 'measured', source_cell_count: 12, local_verified: false, local_measured_cells: 0, model_supported: true, recommended_action: 'measured' }], total, source_verified: true, source: { repo: 'fixed-source', revision: 'fixed-version', url: 'https://example.org', scope: 'filtered' }, summary: { pairs: 40, measured_pairs: 31, model_supported_pairs: 40, local_verified_pairs: 1, contexts: [{ cell_line: 'K562', measured_pairs: 31 }] } })
const renderer = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert: noop, remove: noop, setText: noop, setElementText: noop, patchProp: noop, parentNode: () => null, nextSibling: () => null })
function mount(options = {}) {
  const route = vue.reactive({ query: options.route ?? {} }), accessSession = vue.ref({ mode: options.public ? 'public' : 'local', read_only: Boolean(options.public) })
  const queries = [], downloads = [], saved = []
  const api = {
    query: (query, signal) => { queries.push({ query, signal }); return options.query ? options.query(query, signal) : Promise.resolve(fixture()) },
    download: (query, signal) => { downloads.push({ query, signal }); return options.download ? options.download(query, signal) : Promise.resolve({ blob: new Blob(['csv']), filename: 'filtered.csv' }) },
  }
  const modules = { vue, 'vue-router': { useRoute: () => route }, '../stores/access': { accessSession }, '../api/dataCatalog': { dataCatalogApi: api }, '../utils/csv': { downloadBlob: (...args) => saved.push(args) } }
  const code = ts.transpileModule(compileScript(parse(source).descriptor, { id: 'catalog-test' }).content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(name => modules[name] ?? (name.endsWith('.vue') ? {} : require(name)), module, module.exports)
  const component = module.exports.default; component.render = () => null
  const app = renderer.createApp(component), instance = app.mount({}).$
  return { app, state: instance.setupState, route, accessSession, queries, downloads, saved }
}

test('default entry requests measured conditions with ten rows; prediction and full modes remain separate', async () => {
  const h = mount()
  try {
    await flush(); assert.equal(h.queries[0].query.availability, 'measured'); assert.equal(h.queries[0].query.limit, 10)
    h.state.chooseMode('prediction'); await settle()
    assert.equal(h.queries.at(-1).query.model_supported, true); assert.equal(h.queries.at(-1).query.availability, 'all')
    h.state.chooseMode('all'); await settle()
    assert.equal(h.queries.at(-1).query.model_supported, undefined); assert.equal(h.queries.at(-1).query.availability, 'all')
  } finally { h.app.unmount() }
})

test('filtering resets pagination; reset retains mode; CSV covers all matching rows and missing filters', async () => {
  const h = mount()
  try {
    await flush(); h.state.page = 3; await settle(); assert.equal(h.queries.at(-1).query.offset, 20)
    h.state.cellLine = 'K562'; h.state.term = '  ALDOA  '; await settle()
    assert.equal(h.state.page, 1); assert.equal(h.queries.at(-1).query.query, 'ALDOA')
    await h.state.download(); assert.deepEqual(h.downloads.at(-1).query, h.state.filters()); assert.equal(h.downloads.at(-1).query.limit, undefined)
    h.state.showMissing(); await settle(); assert.equal(h.state.mode, 'all'); assert.equal(h.state.availability, 'missing'); assert.equal(h.state.cellLine, 'K562')
    await h.state.download(); assert.deepEqual(h.downloads.at(-1).query, { cell_line: 'K562', query: 'ALDOA', availability: 'missing', model_supported: true })
    h.state.resetFilters(); await settle(); assert.equal(h.state.mode, 'all'); assert.equal(h.state.cellLine, ''); assert.equal(h.state.term, ''); assert.equal(h.state.availability, 'all')
  } finally { h.app.unmount() }
})

test('late filter responses cannot replace current rows and failed queries offer clean retry', async () => {
  const calls = [], h = mount({ query: () => { const d = deferred(); calls.push(d); return d.promise } })
  try {
    h.state.term = 'new'; await settle(); assert.equal(h.queries[0].signal.aborted, true)
    calls[1].resolve(fixture('new')); await flush(); calls[0].resolve(fixture('old')); await flush(); assert.equal(h.state.data.items[0].perturbation, 'new')
    const failed = h.state.load(); calls[2].reject(Error('network failure')); await failed; assert.equal(h.state.error, 'network failure'); assert.equal(h.state.data, null)
    const retried = h.state.load(); calls[3].resolve(fixture('retry')); await retried; assert.equal(h.state.error, ''); assert.equal(h.state.data.items[0].perturbation, 'retry')
  } finally { h.app.unmount() }
})

test('filter changes abort CSV and prevent downloading a response for old conditions', async () => {
  const d = deferred(), h = mount({ download: () => d.promise })
  try {
    await flush(); const pending = h.state.download(); h.state.term = 'changed'; await flush()
    assert.equal(h.downloads[0].signal.aborted, true)
    d.resolve({ blob: new Blob(['old']), filename: 'old.csv' }); await pending
    assert.equal(h.saved.length, 0); assert.equal(h.state.downloading, false)
  } finally { h.app.unmount() }
})

test('public cases retain complete whitelist mode and suppress downloads; access transitions clear private data', async () => {
  const h = mount({ public: true })
  try {
    await flush(); assert.equal(h.queries[0].query.availability, 'all'); assert.deepEqual(h.state.contexts, ['K562'])
    await h.state.download(); assert.equal(h.downloads.length, 0)
  } finally { h.app.unmount() }
  const calls = [], second = mount({ query: () => { const d = deferred(); calls.push(d); return d.promise } })
  try {
    calls[0].resolve(fixture('private')); await flush(); second.accessSession.value = { mode: 'public', read_only: true }
    assert.equal(second.state.data, null); assert.deepEqual(second.state.contexts, [])
    calls[1].resolve(fixture('public')); await flush(); assert.equal(second.state.data.items[0].perturbation, 'public')
    await second.state.download(); assert.equal(second.downloads.length, 0)
  } finally { second.app.unmount() }
})

test('both cached and on-demand measured records route to the measured review workflow', async () => {
  const h = mount()
  try {
    for (const local_verified of [false, true]) assert.deepEqual(h.state.destination({ ...fixture().items[0], local_verified }, '/measured'), { path: '/research', query: { type: 'measured', cell_line: 'K562', perturbation: 'ALDOA' } })
    assert.match(source, /核对并分析/); assert.doesNotMatch(source, /直接分析实测|立即分析/)
  } finally { h.app.unmount() }
})
