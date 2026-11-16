import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'

const require = createRequire(import.meta.url), noop = () => {}
const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
const flush = async () => { await vue.nextTick(); await new Promise(setImmediate); await vue.nextTick() }
const renderer = vue.createRenderer({ createElement: () => ({}), createText: () => ({}), createComment: () => ({}), insert: noop, remove: noop, setText: noop, setElementText: noop, patchProp: noop, parentNode: () => null, nextSibling: () => null })
function mount(name, initialQuery = {}, overrides = {}) {
  const route = vue.reactive({ path: '/research', query: initialQuery, params: {} })
  const router = { replace: async location => { route.path = location.path; route.query = location.query }, push: noop }
  const draft = vue.reactive({ cellLine: 'K562', perturbation: '', measuredMaxCells: '256', measuredSeed: '42', seed: '42', measuredSubmitting: false, setCellLine(value) { this.cellLine = value } })
  const runs = vue.reactive({ submitting: false })
  const modules = {
    vue, 'vue-router': { useRoute: () => route, useRouter: () => router },
    '../stores/access': { accessSession: vue.ref({ mode: 'local', read_only: false }) },
    '../stores/draft': { useDraftStore: () => draft }, '../stores/run': { useRunStore: () => runs },
    '../api/http': { apiFetch: async () => ({ available: true, import_directory: 'configured-directory' }), ApiError: Error },
    '../utils/number': { isIntegerInRange: (value, min, max) => Number.isInteger(Number(value)) && Number(value) >= min && Number(value) <= max },
    '../utils/csv': { downloadBlob: noop },
    '../api/dataCatalog': { dataCatalogApi: { query: async () => ({ items: [], total: 0, summary: { contexts: [] } }) } },
    ...overrides,
  }
  const compiled = compileScript(parse(source(name)).descriptor, { id: name }).content
  const code = ts.transpileModule(compiled, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', code)(name => modules[name] ?? (name.endsWith('.vue') ? {} : require(name)), module, module.exports)
  const component = module.exports.default
  component.render = () => null
  const app = renderer.createApp(component), instance = app.mount({}).$
  return { app, state: instance.setupState, route, draft, runs }
}

test('legacy measured/import/prediction links resolve to two tasks with the correct source and review step', async () => {
  const h = mount('views/ResearchView.vue')
  try {
    assert.deepEqual(h.state.options.map(option => option.id), ['measured', 'prediction'])
    for (const [type, task] of [['measured', 'measured'], ['import', 'measured'], ['prediction', 'prediction']]) {
      h.route.query = { type }; await flush()
      assert.equal(h.state.selected.id, task)
      assert.equal(h.state.selectedType, type)
      assert.equal(h.state.step, 2)
      h.state.reviewing = true
      assert.equal(h.state.step, 3)
    }
    h.route.query = { type: 'unknown' }; await flush()
    assert.equal(h.state.selected, null)
    assert.equal(h.state.step, 1)
  } finally { h.app.unmount() }
})

test('submission locks both task and measured-source switches and preserves the current input', async () => {
  const h = mount('views/ResearchView.vue', { type: 'import', cell_line: 'Jurkat', perturbation: 'ALDOA', max_cells: '64', seed: '7' })
  try {
    for (const lock of ['import', 'measured', 'prediction']) {
      h.state.importBusy = lock === 'import'
      h.draft.measuredSubmitting = lock === 'measured'
      h.runs.submitting = lock === 'prediction'
      assert.equal(h.state.locked, true)
      h.state.choose('prediction'); h.state.choose('measured')
      await flush()
      assert.equal(h.route.query.type, 'import')
    }
    h.state.importBusy = false; h.draft.measuredSubmitting = false; h.runs.submitting = false
    h.state.choose('measured'); await flush()
    assert.equal(h.route.query.type, 'measured')
    assert.equal(h.route.query.cell_line, 'Jurkat')
    assert.equal(h.route.query.perturbation, 'ALDOA')
    assert.equal(h.route.query.max_cells, '64')
    assert.equal(h.route.query.seed, h.draft.measuredSeed)
    h.state.choose('invented-type'); await flush()
    assert.equal(h.route.query.type, 'measured')
  } finally { h.app.unmount() }
})

test('source switches retain edited measured sampling and do not overwrite the prediction seed', async () => {
  const h = mount('views/ResearchView.vue', { type: 'measured', max_cells: '64', seed: '7' })
  try {
    h.draft.measuredMaxCells = '512'; h.draft.measuredSeed = '23'; h.draft.seed = '11'
    h.state.choose('import'); await flush()
    h.state.choose('measured'); await flush()
    assert.equal(h.draft.measuredMaxCells, '512'); assert.equal(h.draft.measuredSeed, '23')
    assert.equal(h.route.query.max_cells, '512'); assert.equal(h.route.query.seed, '23')
    h.state.choose('prediction'); await flush()
    assert.equal(h.draft.seed, '11'); assert.equal(h.route.query.seed, '11')
    h.state.choose('measured'); await flush()
    assert.equal(h.draft.measuredSeed, '23')
  } finally { h.app.unmount() }
})

test('measured deep links preserve valid sampling parameters and reject malformed replacements', async () => {
  const h = mount('views/ResearchView.vue', { type: 'measured', cell_line: 'RPE1', perturbation: 'aldoa', max_cells: '512', seed: '12' })
  try {
    assert.equal(h.draft.cellLine, 'RPE1')
    assert.equal(h.draft.perturbation, 'ALDOA')
    assert.equal(h.draft.measuredMaxCells, '512')
    assert.equal(h.draft.measuredSeed, '12')
    h.route.query = { type: 'measured', cell_line: 'invented', perturbation: '../bad', max_cells: '-3', seed: 'NaN' }
    await flush()
    assert.equal(h.draft.cellLine, 'RPE1')
    assert.equal(h.draft.perturbation, 'ALDOA')
    assert.equal(h.draft.measuredMaxCells, '512')
    assert.equal(h.draft.measuredSeed, '12')
  } finally { h.app.unmount() }
})

test('controlled H5AD readiness requires distinct groups and an explicit raw-count denominator', async () => {
  const h = mount('components/ControlledImport.vue')
  try {
    await flush()
    assert.equal(h.state.caps.import_directory, 'configured-directory')
    Object.assign(h.state.form, { relative_path: 'experiment.h5ad', target_label: 'ALDOA', perturbation: 'ALDOA' })
    assert.equal(Boolean(h.state.ready), true)
    h.state.form.target_label = 'non-targeting'
    assert.equal(Boolean(h.state.ready), false)
    h.state.form.target_label = 'ALDOA'
    h.state.form.expression_scale = 'raw_counts'
    assert.equal(Boolean(h.state.ready), false)
    h.state.form.total_counts_key = 'full_library_total_counts'
    assert.equal(Boolean(h.state.ready), true)
    h.state.busy = true
    assert.equal(Boolean(h.state.ready), false)
    assert.ok(h.state.preparationScript.includes('\ntry:\n'))
    assert.ok(h.state.preparationScript.includes('backed="r"'))
    assert.ok(h.state.preparationScript.includes('data.file.close()'))
  } finally { h.app.unmount() }
})

test('catalog route changes refresh the visible filters without remounting the page', async () => {
  const h = mount('views/DataCatalogView.vue', { cell_line: 'K562', perturbation: 'ALDOA' })
  try {
    await flush()
    assert.equal(h.state.cellLine, 'K562')
    assert.equal(h.state.term, 'ALDOA')
    h.route.query = { cell_line: 'HepG2', perturbation: 'GAPDH' }; await flush()
    assert.equal(h.state.cellLine, 'HepG2')
    assert.equal(h.state.term, 'GAPDH')
    assert.deepEqual(h.state.destination({ cell_line: 'HepG2', perturbation: 'GAPDH' }, '/measured'), { path: '/research', query: { type: 'measured', cell_line: 'HepG2', perturbation: 'GAPDH' } })
  } finally { h.app.unmount() }
})
