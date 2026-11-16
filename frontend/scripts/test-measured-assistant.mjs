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
      apiKey: vue.ref(''), modelReady: vue.ref(Boolean(options.ready)), modelPreferences: options.preferences ?? {}, modelConnection: () => (options.connection ?? {}),
    },
    '../utils/csv': { downloadBlob: options.download ?? (() => {}) },
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

const chatContext = (hash = 'verified-context') => ({
  source_kind:'measured', source_id:'measured_fixture', selection:{view:'overview'},
  context_sha256:hash, data:{cell_line:'test',perturbation:'test'},
  request_budget:{system_bytes:300,user_bytes:{interpret:600}},
})
const chatReply = text => ({text,model:'test-model',generated_at:'2026-11-16T00:00:00Z',finish_reason:'stop'})

test('follow-ups carry only completed same-context turns and retry does not resend its own answer', async () => {
  const requests = []
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}}, {
    ready:true, preferences:{max_tokens:2000,context_window:32000},
    fetch:async (path,options) => {requests.push({path,options});return chatReply(`answer ${requests.length}`)},
  })
  try {
    state.context = chatContext()
    state.question = 'first question'
    await state.generate()
    assert.equal(state.turns.length,1)
    assert.equal(state.turns[0].state,'complete')
    state.question = 'follow-up question'
    await state.generate()
    assert.deepEqual(requests[1].options.body.history,[{question:'first question',purpose:'interpret',answer:'answer 1'}])
    assert.equal(requests[1].options.body.history_context_sha256,'verified-context')
    await state.retryTurn(state.turns[1])
    assert.equal(state.turns.length,2)
    assert.deepEqual(requests[2].options.body.history,[{question:'first question',purpose:'interpret',answer:'answer 1'}])
    state.context = chatContext('changed-context')
    assert.equal(state.history.length,0)
    state.newConversation()
    assert.equal(state.turns.length,0)
  } finally {application.unmount()}
})

test('cancelled responses are discarded and never become conversation history', async () => {
  let resolveRequest
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}}, {
    ready:true, preferences:{max_tokens:2000,context_window:32000},
    fetch:() => new Promise(resolve => {resolveRequest = resolve}),
  })
  try {
    state.context = chatContext()
    const pending = state.generate()
    await Promise.resolve()
    state.cancel()
    resolveRequest(chatReply('late result'))
    await pending
    assert.equal(state.result,null)
    assert.equal(state.turns[0].state,'cancelled')
    assert.equal(state.history.length,0)
  } finally {application.unmount()}
})

test('history is bounded to six complete turns and rejects excessive answer/request bytes before sending', async () => {
  let calls = 0
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}}, {
    ready:true, preferences:{max_tokens:2000,context_window:32000}, fetch:async () => {calls++;return chatReply('ok')},
  })
  try {
    state.context = chatContext()
    for (let index=0;index<8;index++) state.turns.push({id:index,question:`q${index}`,purpose:'interpret',context:chatContext(),result:chatReply(`a${index}`),state:'complete',error:''})
    assert.equal(state.history.length,6)
    assert.equal(state.history[0].question,'q2')
    state.turns[7].result.text = 'x'.repeat(16001)
    assert.equal(state.historyOverBudget,true)
    await state.generate()
    assert.equal(calls,0)
    state.turns = [0,1,2].map(id => ({id,question:'q',purpose:'interpret',context:chatContext(),result:chatReply('中'.repeat(8000)),state:'complete',error:''}))
    assert.equal(state.historyOverBudget,true)
    await state.generate()
    assert.equal(calls,0)
    state.turns = [0,1,2].map(id => ({id,question:'q',purpose:'interpret',context:chatContext(),result:chatReply('中'.repeat(7000)),state:'complete',error:''}))
    state.question = '中'.repeat(1200)
    assert.ok(state.historyBytes < 64000)
    assert.equal(state.historyOverBudget,true, 'entire request must fit middleware cap, including current question')
    await state.generate()
    assert.equal(calls,0)
  } finally {application.unmount()}
})

test('assistant Markdown produces escaped Vue text blocks including tables, never executable HTML', () => {
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}})
  try {
    const blocks = state.markdownBlocks('# Finding\n\n| Gene | Delta |\n| --- | ---: |\n| <img src=x onerror=alert(1)> | 2 |\n\n```html\n<script>alert(1)</script>\n```')
    assert.equal(blocks[0].kind,'heading')
    const table = blocks.find(block => block.kind === 'table')
    assert.equal(table.rows[1][0],'<img src=x onerror=alert(1)>')
    assert.equal(blocks.find(block => block.kind === 'code').text,'<script>alert(1)</script>')
    assert.ok(!sourceText('components/AssistantPanel.vue').includes('v-html'))
    assert.deepEqual(state.inlineParts('**key** `value`'),[{kind:'strong',text:'key'},{kind:'text',text:' '},{kind:'code',text:'value'}])
  } finally {application.unmount()}
})

test('older failed or cancelled turns do not hide later standalone preview or copy errors', () => {
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}})
  try {
    state.turns = [{id:1,question:'q',purpose:'interpret',context:chatContext(),result:null,state:'error',error:'generation failure'}]
    state.error = 'generation failure'
    assert.equal(state.standaloneError,false, 'the generation error is already rendered on its turn')
    state.error = 'preview failed'
    assert.equal(state.standaloneError,true)
    state.error = 'copy failed'
    assert.equal(state.standaloneError,true)
    state.turns[0].state = 'cancelled'
    state.error = 'generation failure'
    assert.equal(state.standaloneError,true, 'cancelled turns never suppress standalone error messages')
    state.error = ''
    assert.equal(state.standaloneError,false)
  } finally {application.unmount()}
})

test('follow-up export retains the exact submitted history and hash without connection credentials', async () => {
  let calls = 0, exportedBlob
  const {application,state} = mountPanel({sourceKind:'measured',sourceId:'measured_fixture',selection:{view:'overview'}}, {
    ready:true, preferences:{max_tokens:2000,context_window:32000},
    connection:{api_key:'secret-key-never-export',model:'test-model',max_tokens:2000,context_window:32000},
    fetch:async () => chatReply(`answer ${++calls}`),
    download:blob => {exportedBlob = blob},
  })
  try {
    state.context = chatContext()
    state.question = 'initial question'
    await state.generate()
    state.question = 'follow-up question'
    await state.generate()
    state.turns[0].result.text = 'subsequently changed local answer'
    state.downloadTurn(state.turns[1])
    const raw = await exportedBlob.text(), exported = JSON.parse(raw)
    assert.deepEqual(exported.conversation_history,[{question:'initial question',purpose:'interpret',answer:'answer 1'}])
    assert.equal(exported.history_context_sha256,'verified-context')
    assert.equal(exported.context.context_sha256,exported.history_context_sha256)
    assert.equal(exported.interpretation.text,'answer 2')
    assert.ok(!raw.includes('secret-key-never-export'))
    assert.ok(!Object.hasOwn(exported,'connection'))
    state.downloadTurn(state.turns[0])
    const first = JSON.parse(await exportedBlob.text())
    assert.deepEqual(first.conversation_history,[])
    assert.equal(first.history_context_sha256,null)
  } finally {application.unmount()}
})
