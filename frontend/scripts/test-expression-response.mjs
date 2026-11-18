import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import test from 'node:test'
import ts from 'typescript'
import * as vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
const require = createRequire(import.meta.url)
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
function evaluate(source, modules) { const module={exports:{}};new Function('require','module','exports',compile(source))(name=>modules[name] ?? require(name),module,module.exports);return module.exports }
const base = evaluate(readFileSync(new URL('../src/utils/resultOverview.ts',import.meta.url),'utf8'),{})
const helpers = evaluate(readFileSync(new URL('../src/utils/expressionResponse.ts',import.meta.url),'utf8'),{'./resultOverview':base})
const {expressionPairs,strongestGenes,scatterSample}=helpers
test('expression views isolate populations, keep zeros and exclude missing pairs from ranks',()=>{
  const rows=[{id:'a',control:2,predicted:-1,observed:3,delta:999},{id:'zero',control:0,observed:0},{id:'missing',control:null,observed:2}]
  const pairs=expressionPairs(rows,'measured')
  assert.equal(pairs[0].delta,1);assert.equal(expressionPairs(rows,'run')[0].delta,-3)
  assert.equal(pairs[1].delta,0);assert.equal(pairs[2].delta,null)
  assert.deepEqual(strongestGenes(pairs).map(row=>row.id),['a','zero'])
  assert.equal(rows[0].delta,999)
})
test('scatter sampling is bounded and deterministic without altering complete statistics',()=>{
  const rows=expressionPairs(Array.from({length:6546},(_,i)=>({id:String(i),control:i,observed:i+1})),'measured')
  assert.equal(scatterSample(rows).length,2000)
  assert.equal(new Set(scatterSample(rows).map(row=>row.id)).size,2000)
  assert.deepEqual(scatterSample(rows),scatterSample(rows))
  assert.equal(rows.length,6546);assert.equal(strongestGenes(rows).length,12)
})
const noop=()=>{}
const renderer=vue.createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert:noop,remove:noop,setText:noop,setElementText:noop,patchProp:noop,parentNode:()=>null,nextSibling:()=>null})
const flush=async()=>{for(let i=0;i<5;i++){await vue.nextTick();await new Promise(setImmediate)}}
const pending=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}}
function mountGallery(request){
  const props=vue.reactive({recordId:'first',sourceKind:'measured'}),calls=[]
  const modules={vue,'../stores/assistantSource':{openChartAssistant:noop,assistantFigure:vue.shallowRef(null)},'../utils/expressionResponse':helpers,'../utils/metabolicVisualization':{scoreLabel:String},'../api/measured':{measuredApi:{expressionSummary:(...args)=>{calls.push(args);return request(...args)}}},'../utils/csv':{},'./GeneDistribution.vue':{},'./SingleCellAtlas.vue':{}}
  const component=evaluate(compileScript(parse(readFileSync(new URL('../src/components/ExpressionResponseGallery.vue',import.meta.url),'utf8')).descriptor,{id:'expression-test'}).content,modules).default
  component.render=()=>null
  let instance
  const app=renderer.createApp({render:()=>vue.h(component,{...props,ref:value=>{instance=value}})})
  app.mount({})
  return{app,props,calls,get state(){return instance.$.setupState}}
}
test('measured chart loader uses one complete summary and refuses incomplete data',async()=>{
  const row=i=>({gene:`G${i}`,control:i,observed:i+1,observed_delta:1})
  const h=mountGallery(async(id)=>({record_id:id,total:450,items:Array.from({length:450},(_,i)=>row(i))}))
  try {await flush();assert.equal(h.state.pairs.length,450);assert.equal(h.state.loading,false);assert.equal(h.state.error,'');assert.equal(h.calls.length,1)}finally{h.app.unmount()}
  const broken=mountGallery(async(id)=>({record_id:id,total:2,items:[row(0)]}))
  try {await flush();assert.equal(broken.state.pairs.length,0);assert.match(broken.state.error,/不完整/)}finally{broken.app.unmount()}
})
test('switching research records aborts an old read and discards its late response',async()=>{
  const old=pending()
  const h=mountGallery(id=>id==='first'?old.promise:Promise.resolve({record_id:id,total:1,items:[{gene:'NEW',control:1,observed:2,observed_delta:1}]}))
  try {await flush();h.props.recordId='second';await flush();assert.equal(h.calls[0][1].aborted,true);old.resolve({total:1,items:[{gene:'OLD',control:1,observed:3,observed_delta:2}]});await flush();assert.deepEqual(h.state.pairs.map(row=>row.id),['NEW'])}finally{h.app.unmount()}
})
test('single-gene distribution drops late renders and clears export when gene changes',async()=>{
  globalThis.window={setTimeout}
  const props=vue.reactive({kind:'measured',recordId:'r1',gene:'A'}),a=pending(),b=pending(),requests=[]
  const modules={vue,'../stores/assistantSource':{openChartAssistant:noop,assistantFigure:vue.shallowRef(null)},'../utils/metabolicVisualization':{scoreLabel:String},'../utils/csv':{downloadBlob:noop},'../api/http':{apiFetch:(path,args)=>{
    if(path.endsWith('/context'))return Promise.resolve({genes:['A','B'],availability:{distribution:true}})
    requests.push(args);return args.body.gene==='A'?a.promise:b.promise
  }}}
  const component=evaluate(compileScript(parse(readFileSync(new URL('../src/components/GeneDistribution.vue',import.meta.url),'utf8')).descriptor,{id:'distribution-test'}).content,modules).default
  component.render=()=>null;let instance
  const app=renderer.createApp({render:()=>vue.h(component,{...props,ref:value=>{instance=value}})});app.mount({})
  try {
    await flush();await new Promise(resolve=>setTimeout(resolve,210));assert.equal(requests[0].body.gene,'A')
    props.gene='B';await flush();assert.equal(requests[0].signal.aborted,true);assert.equal(instance.$.setupState.svg,null)
    await new Promise(resolve=>setTimeout(resolve,210))
    b.resolve(new Blob(['<svg><text>B</text></svg>'],{type:'image/svg+xml'}));await flush()
    a.resolve(new Blob(['<svg><text>A</text></svg>'],{type:'image/svg+xml'}));await flush()
    assert.match(await instance.$.setupState.svg.text(),/>B</)
  } finally { app.unmount();delete globalThis.window }
})
test('single-cell atlas rejects mismatched source and discards late gene-panel responses',async()=>{
  const props=vue.reactive({kind:'measured',recordId:'r1',genes:['A'],selected:'A'}),old=pending(),calls=[]
  const modules={vue,'../stores/assistantSource':{openChartAssistant:noop,assistantFigure:vue.shallowRef(null)},'../utils/csv':{},'../utils/metabolicVisualization':{scoreLabel:String},'../api/http':{apiFetch:(path,args)=>{
    calls.push({path,args});return args.body.genes[0]==='A'?old.promise:Promise.resolve({record_id:'r1',kind:'measured',genes:['B'],groups:[],cells:[],value_domain:[0,1]})
  }}}
  const component=evaluate(compileScript(parse(readFileSync(new URL('../src/components/SingleCellAtlas.vue',import.meta.url),'utf8')).descriptor,{id:'atlas-test'}).content,modules).default
  component.render=()=>null;let instance
  const app=renderer.createApp({render:()=>vue.h(component,{...props,ref:value=>{instance=value}})});app.mount({})
  try {
    await flush();props.genes=['B'];await flush()
    assert.equal(calls[0].args.signal.aborted,true)
    old.resolve({record_id:'r1',kind:'measured',genes:['A'],groups:[],cells:[],value_domain:[0,1]});await flush()
    assert.deepEqual(instance.$.setupState.data.genes,['B'])
    props.recordId='r2';await flush()
    assert.equal(instance.$.setupState.data,null);assert.match(instance.$.setupState.error,/来源/)
  } finally {app.unmount()}
})
