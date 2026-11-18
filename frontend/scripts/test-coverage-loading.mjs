import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'

const require = createRequire(import.meta.url)
const source = name => readFileSync(new URL('../src/' + name, import.meta.url), 'utf8')
function evaluate(code, modules = {}) {
  const js = ts.transpileModule(code, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const module = {exports:{}}
  new Function('require','module','exports',js)(name => modules[name] ?? require(name), module, module.exports)
  return module.exports
}
const {createCoverageCache, coverageSourceKey} = evaluate(source('utils/coverageCache.ts'))
const {summarizeCoverage, filterCoverageTasks} = evaluate(source('utils/coverageSummary.ts'))
const pagination = evaluate(source('utils/pagination.ts'))
const flush = async () => { await vue.nextTick(); await new Promise(setImmediate); await vue.nextTick() }
const model = cellLine => ({kind:'model',cellLine})
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => {resolve=a;reject=b});return {promise,resolve,reject} }
const cell = (id, status, present, total) => ({id,label:id,guide:null,coverage_status:status,n_present_all:present,n_genes_all:total,n_missing_all:total-present,present_genes_all:present?'A':'',missing_genes_all:total>present?'B':'',fraction_present_all:total?present/total:0})
function fixture(id = 'K562', kind = 'model') {
  return {source:{kind,id,cell_line:kind==='model'?id:undefined,title:id,panel_sha256:id},models:[{id,cell_line:id,panel_sha256:id}],panel_gene_count:2000,
    genes:[{symbol:'A',approved_symbol:'A',name_en:'A',in_panel:true,category_ids:[],tasks:['full'],reactions:[]},{symbol:'B',approved_symbol:'B',name_en:'B',in_panel:false,category_ids:[],tasks:[],reactions:[]}],
    tasks:[cell('full','full',1,1),cell('partial','partial',1,2),cell('absent','absent',0,2),cell('unmapped','unmapped',0,0)],
    reactions:[cell('r1','full',1,1),cell('r2','partial',1,2),cell('r3','absent',0,2),cell('r4','unmapped',0,0)],gene_categories:[],classification:{available:true},database_version:'test',warnings:[]}
}
function controlledCache(options = {}) {
  const calls = []
  const cache = createCoverageCache((source,signal) => {const d=deferred();calls.push({...d,source,signal});return d.promise}, options)
  return {cache,calls}
}

test('cache reuses immutable snapshot, expires at TTL, forces refresh, and evicts least recently read entry', async () => {
  let now=100, count=0
  const cache=createCoverageCache(async src => {count++;return fixture(src.cellLine)}, {now:()=>now,ttlMs:10,maxEntries:2})
  const signal=new AbortController().signal
  const first=await cache.load(model('A'),signal)
  assert.equal(await cache.load(model('A'),signal),first);assert.equal(count,1)
  now=110;assert.equal(cache.peek(model('A')),null)
  await cache.load(model('A'),signal);assert.equal(count,2)
  await cache.load(model('A'),signal,true);assert.equal(count,3)
  await cache.load(model('B'),signal);cache.peek(model('A'));await cache.load(model('C'),signal)
  assert.equal(cache.peek(model('B')),null);assert.ok(cache.peek(model('A')))
})

test('source keys isolate default model, named models, and saved runs', async () => {
  const keys=[model(),model('K562'),model('run_A'),{kind:'run',runId:'run_A'}].map(coverageSourceKey)
  assert.equal(new Set(keys).size,4)
})

test('concurrent consumers share one request and cancelling one does not cancel the other', async () => {
  const {cache,calls}=controlledCache(), a=new AbortController(),b=new AbortController()
  const pa=cache.load(model('A'),a.signal),pb=cache.load(model('A'),b.signal)
  await flush();assert.equal(calls.length,1)
  a.abort();await assert.rejects(pa,{name:'AbortError'});assert.equal(calls[0].signal.aborted,false)
  calls[0].resolve(fixture('A'));const snapshot=await pb
  assert.equal(snapshot.data.source.id,'A');assert.equal(cache.peek(model('A')),snapshot)
})

test('last consumer cancellation aborts transport and an ignored late response cannot populate cache', async () => {
  const {cache,calls}=controlledCache(), a=new AbortController()
  const first=cache.load(model('A'),a.signal);await flush();a.abort()
  await assert.rejects(first,{name:'AbortError'});assert.equal(calls[0].signal.aborted,true)
  const next=cache.load(model('A'),new AbortController().signal);await flush();assert.equal(calls.length,2)
  calls[0].resolve(fixture('old'));calls[1].resolve(fixture('new'));await next;await flush()
  assert.equal(cache.peek(model('A')).data.source.id,'new')
})

test('session clearing rejects active consumers and never restores private snapshots from late responses', async () => {
  const {cache,calls}=controlledCache()
  const run={kind:'run',runId:'run_private'}
  const request=cache.load(run,new AbortController().signal);await flush();cache.clear()
  await assert.rejects(request,{name:'AbortError'});assert.equal(calls[0].signal.aborted,true)
  calls[0].resolve(fixture('run_private','run'));await flush();assert.equal(cache.peek(run),null)
})

test('failed requests are retryable and do not become cached', async () => {
  let count=0
  const cache=createCoverageCache(async () => {if(++count===1)throw Error('temporary');return fixture()})
  await assert.rejects(cache.load(model('A'),new AbortController().signal),/temporary/)
  assert.equal(cache.peek(model('A')),null)
  assert.ok(await cache.load(model('A'),new AbortController().signal));assert.equal(count,2)
})

test('coverage totals keep full, partial, absent, unmapped and genuine zero denominators separate', () => {
  const data=fixture(),summary=summarizeCoverage(data)
  assert.deepEqual(summary,{tasks:{full:1,partial:1,absent:1,unmapped:1},reactions:{full:1,partial:1,absent:1,unmapped:1},coveredGenes:1,totalGenes:2,totalTasks:4,totalReactions:4})
  assert.equal(filterCoverageTasks(data.tasks,'all','').length,4)
  assert.equal(filterCoverageTasks(data.tasks,'covered','').length,2)
  assert.equal(filterCoverageTasks(data.tasks,'absent','B')[0].n_present_all,0)
  assert.equal(filterCoverageTasks(data.tasks,'unmapped','')[0].n_genes_all,0)
  assert.equal(filterCoverageTasks([], 'all','').length,0)
})

const noop=()=>{}
const renderer=vue.createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert:noop,remove:noop,setText:noop,setElementText:noop,patchProp:noop,parentNode:()=>null,nextSibling:()=>null})
function mount(cache, query={}) {
  const route=vue.reactive({path:'/methods/coverage',query})
  const modules={vue,'vue-router':{useRoute:()=>route,useRouter:()=>({replace:async target=>{route.query=target.query}})},
    '../api/coverage':{coverageCatalog:cache},'../utils/coverageCache':{coverageSourceKey},'../utils/coverageSummary':{summarizeCoverage,filterCoverageTasks},
    '../utils/pagination':pagination,'../utils/csv':{downloadBlob:noop,downloadCsv:noop},'../utils/exportArtifacts':{buildCoverageExport:noop}}
  const code=compileScript(parse(source('views/CoverageView.vue')).descriptor,{id:'coverage-test'}).content
  for(const name of ['TablePager','GeneCategoryGuide','TaskCoverageOverview','MethodsPageHeader'])modules['../components/'+name+'.vue']={}
  const component=evaluate(code,modules).default;component.render=()=>null
  const app=renderer.createApp(component),vm=app.mount({}).$
  return {app,state:vm.setupState,route}
}

test('route switching immediately clears old source, ignores late response, and keeps payload shallow', async () => {
  const {cache,calls}=controlledCache(), h=mount(cache,{cell_line:'A'})
  try {
    await flush();h.route.query={run:'run_B'};await flush()
    assert.equal(h.state.data,null);assert.equal(calls[0].signal.aborted,true)
    calls[1].resolve(fixture('run_B','run'));await flush()
    assert.equal(h.state.data.source.id,'run_B');assert.equal(vue.isProxy(h.state.data),false)
    calls[0].resolve(fixture('A'));await flush();assert.equal(h.state.data.source.id,'run_B')
    assert.equal(cache.peek(model('A')),null)
  } finally {h.app.unmount()}
})

test('cached route remount avoids a second request; explicit refresh retains labeled previous snapshot on failure', async () => {
  let calls=0
  const cache=createCoverageCache(async()=>{if(++calls>1)throw Error('refresh failed');return fixture()})
  let h=mount(cache);await flush();h.app.unmount();h=mount(cache)
  try {
    await flush();assert.equal(calls,1);assert.equal(h.state.fromCache,true)
    await h.state.load(true);assert.equal(calls,2);assert.equal(h.state.data.source.id,'K562');assert.equal(h.state.error,'refresh failed');assert.ok(h.state.fetchedAt)
  } finally {h.app.unmount()}
})

test('absent and unmapped task deep links remain discoverable and filter changes retain truthful totals', async () => {
  const cache=createCoverageCache(async()=>fixture()),h=mount(cache,{task:'absent'})
  try {
    await flush();assert.equal(h.state.tab,'tasks');assert.equal(h.state.selectedTask.id,'absent');assert.equal(h.state.selectedTask.n_present_all,0)
    h.route.query={task:'unmapped'};await flush();assert.equal(h.state.selectedTask.id,'unmapped');assert.equal(h.state.selectedTask.n_genes_all,0)
    h.state.taskCoverage='partial';await flush();assert.equal(h.state.tasks.length,1);assert.equal(h.state.summary.totalTasks,4)
  } finally {h.app.unmount()}
})

test('conflicting, empty and repeated source query parameters never fall back to a different dataset', async () => {
  let calls=0;const cache=createCoverageCache(async()=>{calls++;return fixture()})
  for(const query of [{run:'run_A',cell_line:'A'},{run:['run_A','run_B']},{cell_line:['A','B']},{run:null},{cell_line:''}]) {
    const h=mount(cache,query)
    try {await flush();assert.equal(h.state.data,null);assert.ok(h.state.error);assert.equal(h.state.loading,false)} finally {h.app.unmount()}
  }
  assert.equal(calls,0)
})

test('cancelling loading exposes retry and retry can complete for the same source', async () => {
  const {cache,calls}=controlledCache(),h=mount(cache)
  try {
    await flush();h.state.cancelLoad();assert.equal(h.state.cancelled,true);assert.equal(h.state.loading,false);assert.equal(h.state.data,null)
    const retried=h.state.load();await flush();calls[1].resolve(fixture());await retried
    assert.equal(h.state.cancelled,false);assert.equal(h.state.data.source.id,'K562')
    calls[0].resolve(fixture('late'));await flush();assert.equal(h.state.data.source.id,'K562')
  } finally {h.app.unmount()}
})
