import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as vue from 'vue'
import ts from 'typescript'
import { parse, compileScript } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'

function evaluate(source, requireModule) {
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', compiled)(requireModule, module, module.exports)
  return module.exports
}
const helpers = evaluate(readFileSync(new URL('../src/utils/resultOverview.ts', import.meta.url), 'utf8'), () => ({}))
const entry = vue.reactive({
  record: { run_id: 'run_test', status: 'completed', request: { cell_line: 'K562', perturbation: 'TARGET', mode: 'online' } },
  genes: { status: 'ok', data: { truncated: false, items: [{ gene: 'TARGET', control: 100, predicted: 150, predicted_delta: 50 }, { gene: 'OTHER', control: 20, predicted: 30, predicted_delta: 10 }] } },
  tasks: { status: 'ok', data: { items: [{ id: 'TASK1', control: 100, predicted: 200 }, { id: 'TASK2', control: 20, predicted: 30 }] } },
})
const route = vue.reactive({ path: '/runs/run_test', params: { runId: 'run_test' }, query: {} })
const noop = () => {}
const cleanup = []
const navigations = []
let assistantSource
const requireModule = name => {
  if (name === 'vue') return { ...vue, onBeforeUnmount: callback => cleanup.push(callback) }
  if (name === 'vue-router') return { useRoute: () => route, useRouter: () => ({ replace: location => navigations.push(location) }) }
  if (name.endsWith('stores/run')) return { useRunStore: () => ({ entry: () => entry, openRun: noop, leaveRun: noop, ensureTabData: noop }) }
  if (name.endsWith('stores/recent')) return { useRecentStore: () => ({ add: noop }) }
  if (name.endsWith('stores/candidates')) return { useCandidatesStore: () => ({}) }
  if (name.endsWith('stores/draft')) return { useDraftStore: () => ({}) }
  if (name.endsWith('stores/ui')) return { useUiStore: () => ({}) }
  if (name.endsWith('stores/assistantSource')) return { useAssistantSource: source => { assistantSource = source }, openAssistant: noop }
  if (name.endsWith('api/http')) return { apiFetch: () => new Promise(noop) }
  if (name.endsWith('utils/resultOverview')) return helpers
  if (name.endsWith('utils/biologyLocale')) return { taskName: (id, label) => label || id, metabolicGroupName: value => value || 'unknown' }
  if (name.endsWith('utils/source')) return { isSyntheticResult: () => false }
  return {}
}
function componentFrom(relative) {
  const filename = new URL(relative, import.meta.url).pathname
  const descriptor = parse(readFileSync(new URL(relative, import.meta.url), 'utf8'), { filename }).descriptor
  return evaluate(compileScript(descriptor, { id: filename }).content, requireModule).default
}
function setup(relative, props, emit = noop) {
  return componentFrom(relative).setup(props, { expose: noop, emit })
}

const overviewComponent = componentFrom('../src/components/ResultOverview.vue')
const requiredProps = { sourceKind: 'measured', cellLine: 'K562', perturbation: 'TARGET', genes: [], tasks: [] }
for (const [supplied, expected] of [[{}, null], [{ targetInPanel: false }, false], [{ targetInPanel: true }, true]]) {
  let resolvedTarget
  await renderToString(vue.createSSRApp({ ...overviewComponent, setup: props => { resolvedTarget = props.targetInPanel; return () => null } }, { ...requiredProps, ...supplied }))
  assert.equal(resolvedTarget, expected, 'An omitted optional target flag means unknown, not an absent target')
}

const scope = vue.effectScope()
scope.run(() => {
  const workbench = setup('../src/views/WorkbenchView.vue', {})
  assert.equal(assistantSource().view, 'overview')
  const events = []
  const wrapper = setup('../src/components/RunResultOverview.vue', { runId: 'run_test' }, (event, value) => {
    events.push([event, value])
    if (event === 'comparison-mode' && workbench.overviewMatched) workbench.overviewMatched.value = value
  })
  wrapper.coverage.value = { tasks: [{ id: 'TASK1', fraction_present_all: 1 }, { id: 'TASK2', fraction_present_all: 0.5 }] }
  assert.equal(wrapper.targetInPanel.value, true)
  assert.equal(wrapper.tasks.value[0].control, 100)
  assert.equal(wrapper.genes.value[0].observed, null)
  wrapper.comparison.value = {
    status: 'available', genes: [{ id: 'TARGET', control: 2, predicted: 3, observed: 4, predicted_delta: 1 }, { id: 'OTHER', control: 5, predicted: 6, observed: 7, predicted_delta: 1 }],
    tasks: [{ id: 'TASK1', control: 8, predicted: 9, observed: 10, predicted_delta: 1 }],
    parameters: { population_counts: { control: 12, predicted: 13, observed: 14 } }, expression: { mse_relative_to_no_change: 1.2 },
  }
  assert.equal(wrapper.genes.value[0].control, 2)
  assert.equal(wrapper.tasks.value[0].control, 8)
  assert.equal(wrapper.tasks.value[1].control, null, 'Missing matched tasks cannot fall back to original means')
  assert.equal(wrapper.tasks.value[0].coverage, 1)
  assert.equal(wrapper.populationCounts.value.control, 12)
  assert.equal(wrapper.baselineRatio.value, 1.2)
  wrapper.coverage.value.tasks.push({ id: 'UNSCORED', fraction_present_all: 0.2 })
  wrapper.comparison.value.tasks.push({ id: 'MATCHED_ONLY', control: 2, predicted: 3, observed: 4, predicted_delta: 1 })
  for (const taskId of ['UNSCORED', 'MATCHED_ONLY']) {
    wrapper.openDetail('task', taskId)
    assert.deepEqual(navigations.at(-1), { path: '/methods/coverage', query: { run: 'run_test', task: taskId } }, 'Unavailable original task must open its exact coverage entry, never another task')
  }
  wrapper.openDetail('task', 'TASK1')
  assert.equal(navigations.at(-1).path, '/runs/run_test')
  assert.equal(navigations.at(-1).query.tab, 'metabolism')
  assert.equal(navigations.at(-1).query.task, 'TASK1')
  assert.equal(navigations.at(-1).query.view, 'function')
  wrapper.openDetail('gene', 'TARGET')
  assert.equal(navigations.at(-1).query.tab, 'genes')
  assert.equal(navigations.at(-1).query.gene, 'TARGET')
  assert.ok(events.some(([event, value]) => event === 'comparison-mode' && value === true), 'Matched display must publish comparison mode')
  assert.equal(assistantSource().view, 'comparison', 'Overview AI must read the same matched population as the displayed numbers')
  route.query.tab = 'genes'
  assert.equal(assistantSource().view, 'genes')
  route.query.tab = 'overview'
  wrapper.comparison.value.genes.pop()
  assert.equal(wrapper.tasks.value[0].coverage, null, 'Coverage cannot transfer to a different gene panel')
  entry.record.request.perturbation = 'ABSENT'
  assert.equal(wrapper.targetInPanel.value, false)
  entry.genes.data.truncated = true
  assert.equal(wrapper.targetInPanel.value, null, 'Truncated rows cannot prove the target is absent')
  wrapper.comparison.value = { status: 'unavailable' }
  assert.equal(assistantSource().view, 'overview', 'Unavailable comparison returns AI to original population')
  wrapper.comparison.value = { status: 'available', genes: [], tasks: [] }
  assert.equal(assistantSource().view, 'comparison')
  wrapper.comparison.value = null
  wrapper.comparisonError.value = 'request failed'
  assert.equal(assistantSource().view, 'overview', 'Comparison error returns AI to original population')
  wrapper.comparison.value = { status: 'available', genes: [], tasks: [] }
  route.query.run = 'run_stale_query'
  route.params.runId = 'run_next'
  assert.equal(workbench.runId.value, 'run_next')
  assert.equal(assistantSource().view, 'overview', 'A new run must reset comparison mode before its context loads')
})
for (const callback of cleanup) callback()
scope.stop()
console.log('Run overview: population isolation, missing tasks, panel coverage, target presence and AI population mapping passed')
