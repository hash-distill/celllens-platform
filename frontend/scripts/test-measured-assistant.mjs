import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'

const require = createRequire(import.meta.url)
const sourceText = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

function evaluate(code, imports = require) {
  const output = ts.transpileModule(code, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
  const exported = {}
  new Function('require', 'exports', output)(imports, exported)
  return exported
}

function createRenderer() {
  return vue.createRenderer({
    createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
    insert() {}, remove() {}, setText() {}, setElementText() {}, patchProp() {},
    parentNode: () => null, nextSibling: () => null,
  })
}

function loadApi(fetch) {
  return evaluate(sourceText('api/assistant.ts'), name => name === './http'
    ? { apiFetch: fetch }
    : require(name))
}

class TestApiError extends Error {
  constructor(code, message) { super(message); this.code = code }
}

function mountPanel(properties, options = {}) {
  const api = loadApi(options.fetch ?? (() => { throw new Error('This rendering test must not make a network request') }))
  const { descriptor } = parse(sourceText('components/AssistantPanel.vue'))
  const script = compileScript(descriptor, { id: 'measured-assistant-regression' }).content
  const modules = {
    '../api/assistant': api,
    '../api/http': { ApiError: TestApiError },
    '../stores/preferences': {
      apiKey: vue.ref(''), modelReady: vue.ref(Boolean(options.ready)), modelPreferences: options.preferences ?? {}, modelConnection: () => ({}),
    },
    '../utils/csv': { downloadBlob() {} },
    '../utils/format': {
      fmtNumber: value => String(value), fmtDelta: value => String(value),
    },
    '../utils/biologyLocale': { taskName: value => value },
  }
  const panel = evaluate(script, name => modules[name] ?? require(name)).default
  panel.render = () => null
  const application = createRenderer().createApp(panel, properties)
  const instance = application.mount({}).$
  return { application, state: instance.setupState }
}

test('legacy empty replies explain a possible reasoning budget issue without inventing a confirmed cause', async () => {
  let calls = 0
  const { application, state } = mountPanel({
    sourceKind: 'measured', sourceId: 'measured_fixture', selection: { view: 'overview' },
  }, {
    ready: true, preferences: { max_tokens: 2048 },
    fetch: async () => { calls++; throw new TestApiError('EMPTY_COMPLETION', 'old generic error') },
  })
  try {
    state.context = { source_kind: 'measured', source_id: 'measured_fixture', selection: { view: 'overview' } }
    await state.generate()
    assert.match(state.error, /空正文.*2,048.*可能.*模型设置/)
    assert.equal(state.result, null)
    assert.equal(state.generating, false)
    assert.equal(calls, 1)
  } finally {
    application.unmount()
  }
})

test('source changes clear stale figures and measured selections retain exact IDs', () => {
  const store = evaluate(sourceText('stores/assistantSource.ts'))
  const source = vue.ref({ kind: 'run', id: 'run_first', title: 'first', completed: true, view: 'overview' })
  const application = createRenderer().createApp({
    setup() {
      store.useAssistantSource(() => source.value)
      return () => null
    },
  })
  application.mount({})
  try {
    store.assistantFigure.value = { view: 'chart', feature_id: 'OLD' }
    assert.equal(store.assistantSelection.value.view, 'chart')
    source.value = {
      kind: 'measured', id: 'measured_fixture', title: 'fixture', completed: true, view: 'genes',
      selection: { view: 'genes', feature_kind: 'gene', feature_id: 'ALDOA' },
    }
    assert.equal(store.assistantFigure.value, null)
    assert.equal(store.assistantSelection.value.view, 'genes')
    assert.equal(store.assistantSelection.value.feature_id, 'ALDOA')
    store.assistantFigure.value = { view: 'chart', feature_id: 'STALE' }
    store.openAssistant(true)
    assert.equal(store.assistantSelection.value.view, 'genes')
    source.value = { kind: 'run', id: 'run_second', title: 'second', completed: true, view: 'overview' }
    assert.equal(store.assistantFigure.value, null)
    assert.equal(store.assistantSelection.value.view, 'overview')
  } finally {
    application.unmount()
  }
  assert.equal(store.assistantSource.value, null)
  assert.equal(store.assistantFigure.value, null)
})

test('measured previews display observation values, exact selected rows and no prediction figures', () => {
  const { application, state } = mountPanel({
    sourceKind: 'measured', sourceId: 'measured_fixture', selection: { view: 'genes' },
  })
  try {
    assert.ok(!('figure' in state.availablePurposes))
    assert.ok(!('comparison' in state.availablePurposes))
    assert.ok('genes' in state.availablePurposes && 'metabolism' in state.availablePurposes)
    assert.equal(state.purpose, 'genes')
    const rendered = state.previewRows([{ gene: 'ALDOA', control: 2, observed: 3, observed_delta: 1 }])
    assert.match(rendered, /ALDOA.*对照 2.*实测 3.*实测差值 1/)
    assert.ok(!rendered.includes('预测'))
    const missing = state.previewRows([{ task: 'fixture-task', control: 0, observed: null }])
    assert.match(missing, /fixture-task.*对照 0.*实测 未提供.*实测差值 未提供/)
    state.context = {
      data: {
        figure: { fake: true },
        selected_feature: {
          id: 'ALDOA', source: 'genes.csv', units: 'mean(log1p(CP10K))',
          row: { gene: 'ALDOA', control: 2, observed: 3, observed_delta: 1 },
        },
      },
    }
    assert.equal(state.figure, undefined)
    assert.equal(state.selectedFeature.id, 'ALDOA')
    assert.equal(state.selectedFeature.units, 'mean(log1p(CP10K))')
  } finally {
    application.unmount()
  }
})

test('run previews retain prediction and chart behavior', () => {
  const { application, state } = mountPanel({
    sourceKind: 'run', sourceId: 'run_fixture', selection: { view: 'chart' },
  })
  try {
    assert.equal(state.purpose, 'figure')
    assert.ok('figure' in state.availablePurposes && 'comparison' in state.availablePurposes)
    assert.match(state.previewRows([{ id: 'GENE', predicted_delta: -2 }]), /GENE：预测差值 -2/)
    state.context = { data: { figure: { method: 'pca' } } }
    assert.equal(state.figure.method, 'pca')
  } finally {
    application.unmount()
  }
})

test('matched comparison previews label all three matched means and both deltas', () => {
  const { application, state } = mountPanel({
    sourceKind: 'run', sourceId: 'run_fixture', selection: { view: 'comparison' },
  })
  try {
    const rendered = state.previewRows([
      { id: 'MATCHED_GENE', control: 2, predicted: 5, observed: 3, predicted_delta: 3, observed_delta: 1 },
    ])
    assert.match(rendered, /MATCHED_GENE.*匹配对照 2.*预测 5.*实测 3.*预测差值 3.*实测差值 1/)
  } finally {
    application.unmount()
  }
})

test('measured API calls retain the source, exact feature ID and reviewed context hash', async () => {
  const requests = []
  const identifier = `measured_${'a'.repeat(24)}`
  const selection = { view: 'metabolism', feature_kind: 'task', feature_id: 'long-task-'.repeat(15) }
  const context = { source_kind: 'measured', source_id: identifier, selection, context_sha256: 'b'.repeat(64) }
  const { assistantApi } = loadApi(async (path, options) => {
    requests.push({ path, options })
    return context
  })
  const controller = new AbortController()
  const preview = await assistantApi.context('measured', identifier, controller.signal, selection)
  assert.equal(requests[0].options.query.source_kind, 'measured')
  assert.equal(requests[0].options.query.feature_id, selection.feature_id)
  await assistantApi.interpret(preview, 'metabolism', { model: 'fixture' }, controller.signal, 'fixture question')
  assert.equal(requests[1].options.body.source_kind, 'measured')
  assert.equal(requests[1].options.body.source_id, identifier)
  assert.equal(requests[1].options.body.feature_id, selection.feature_id)
  assert.equal(requests[1].options.body.context_sha256, context.context_sha256)
  assert.equal(requests[1].options.signal, controller.signal)
})

test('comparison previews reject old backend envelopes or a mismatched returned view', async () => {
  for (const context of [
    { selection: { view: 'comparison' }, artifact_sha256: {} },
    { selection: { view: 'comparison' } },
    { selection: { view: 'overview' }, artifact_sha256: { 'comparison_manifest.json': 'a'.repeat(64) } },
  ]) {
    const { assistantApi } = loadApi(async () => context)
    await assert.rejects(
      assistantApi.context('run', 'run_fixture', undefined, { view: 'comparison' }),
      /后台仍是旧版本.*重启 CellLens 分析服务/,
    )
  }
})

test('comparison previews accept the verified matched branch without blocking ordinary overview', async () => {
  const context = {
    source_kind: 'run', source_id: 'run_fixture', selection: { view: 'comparison' },
    artifact_sha256: { 'comparison_manifest.json': 'a'.repeat(64) },
  }
  const { assistantApi } = loadApi(async () => context)
  assert.equal(await assistantApi.context('run', 'run_fixture', undefined, { view: 'comparison' }), context)
  const overview = { selection: { view: 'overview' }, artifact_sha256: {} }
  const legacyApi = loadApi(async () => overview).assistantApi
  assert.equal(await legacyApi.context('run', 'run_fixture'), overview)
})

test('model default requests check backend support before sending and retain null lengths', async () => {
  const context = {source_kind:'run',source_id:'run_fixture',selection:{view:'overview'}}
  const connection = {max_tokens:null,context_window:null}
  const requests = []
  const current = loadApi(async (path, options) => {
    requests.push({path,options})
    return path === '/assistant/capabilities' ? {model_default_lengths:true} : {text:'ok'}
  }).assistantApi
  await current.interpret(context,'interpret',connection)
  assert.deepEqual(requests.map(item => item.path),['/assistant/capabilities','/assistant/interpret'])
  assert.equal(requests[1].options.body.max_tokens,null)
  assert.equal(requests[1].options.body.context_window,null)
  requests.length = 0
  const stale = loadApi(async path => {requests.push(path); return {}}).assistantApi
  await assert.rejects(stale.interpret(context,'interpret',connection),/重启 CellLens/)
  await assert.rejects(stale.test(connection),/重启 CellLens/)
  assert.deepEqual(requests,['/assistant/capabilities','/assistant/capabilities'])
})
