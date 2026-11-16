import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
import * as vue from 'vue'
import { parse, compileScript } from '@vue/compiler-sfc'

function evaluate(source, requireModule = () => ({})) {
  const compiled = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText
  const module = {exports:{}}
  new Function('require','module','exports',compiled)(requireModule,module,module.exports)
  return module.exports
}
const helper = evaluate(readFileSync(new URL('../src/utils/researchCanvas.ts',import.meta.url),'utf8'))
const points = [
 {x:-10,y:-20,source:'control',cell_id:'control-cell'},
 {x:40,y:30,source:'control',cell_id:'control-cell-2'},
 {x:-2,y:-1.5,source:'observed',cell_id:'<img src=x onerror="alert(1)">&'},
 {x:4,y:1.5,source:'observed',cell_id:'target-cell'},
]
assert.deepEqual(helper.projectionBounds(points),{x:[-14,44],y:[-24,34]})
assert.deepEqual(helper.projectionBounds([{x:NaN,y:4},{x:Infinity,y:1}]),{x:[-1,1],y:[-1,1]})
assert.ok(helper.projectionBounds([{x:0,y:0}]).x[0] < 0)
const tasks = [
 {id:'er',rawCategory:'Processing in the ER',control:0,observed:2,coverage:1},
 {id:'golgi',rawCategory:'Processing in the Golgi',control:2,observed:4,coverage:.5},
 {id:'energy',rawCategory:'ENERGY METABOLISM',control:2,predicted:3},
 {id:'translated-only',category:'Processing in the ER',control:2,observed:3},
 {id:'no-score',rawCategory:'Processing in the ER',control:null,observed:null},
]
assert.deepEqual(helper.structureTasks(tasks,'er').map(row=>row.id),['er'])
assert.deepEqual(helper.structureTasks(tasks,'golgi').map(row=>row.id),['golgi'])
for (const region of ['nucleus','mitochondria','membrane','cytoplasm',null]) assert.deepEqual(helper.structureTasks(tasks,region),[])
assert.equal(helper.escapeTooltip('<a x="y">&\''),'&lt;a x=&quot;y&quot;&gt;&amp;&#39;')

const events=[],actions=[],scope=vue.effectScope()
let canvas,measured
const requireModule = name => {
 if(name==='vue') return vue
 if(name.endsWith('api/http')) return {apiFetch:()=>new Promise(()=>{})}
 if(name.endsWith('utils/researchCanvas')) return helper
 if(name.endsWith('charts/useEChart')) return {CHART_COLORS:{control:'#aaa',observed:'#bbb',predicted:'#ccc'},useEChart:()=>({getChart:()=>({dispatchAction:action=>actions.push(action),getOption:()=>({dataZoom:[{start:30,end:70},{start:20,end:80}]})})})}
 if(name==='echarts/core') return {use(){}}
 return {}
}
function setup(filename, props) {
 const descriptor=parse(readFileSync(new URL('../src/components/'+filename,import.meta.url),'utf8')).descriptor
 return evaluate(compileScript(descriptor,{id:filename}).content,requireModule).default.setup(props,{emit:(event,value)=>events.push([event,value]),expose(){}})
}
await scope.run(async()=>{
 const props=vue.reactive({kind:'measured',recordId:'record-a',tasks})
 canvas=setup('ResearchCanvas.vue',props)
 canvas.data.value={method:'control-reference-pca',points,counts:{control:2,observed:2}}
 const complete=canvas.option()
 for(const group of ['all','control','observed']) {
  canvas.group.value=group
  await vue.nextTick()
  const option=canvas.option()
  assert.deepEqual([option.xAxis.min,option.xAxis.max,option.yAxis.min,option.yAxis.max],[-14,44,-24,34])
  assert.ok(option.dataZoom.every(item=>item.filterMode==='none'))
  assert.equal(canvas.visiblePoints.value.length,group==='all'?4:2)
 }
 const tooltip=canvas.option().tooltip.formatter({data:{point:points[2]}})
 assert.ok(tooltip.includes('&lt;img'))
 assert.ok(!tooltip.includes('<img'))
 assert.ok(tooltip.includes('source: observed'))
 canvas.embedding.value='umap'
 await vue.nextTick()
 assert.deepEqual(events.at(-1),['selection',{layer:'expression',projection_id:'umap',group_id:'observed'}])
 canvas.selectStructure('er')
 assert.deepEqual(events.at(-1),['selection',{layer:'structure'}])
 assert.equal(canvas.relatedTasks.value[0].id,'er')
 canvas.resetProjection()
 assert.deepEqual(actions.at(-1).batch.map(item=>[item.start,item.end]),[[0,100],[0,100]])
 canvas.zoomProjection(.7)
 assert.ok(actions.at(-1).batch.every(item=>item.start>=0&&item.end<=100))
 const measuredProps=vue.reactive({data:{method:'control-reference-pca',points,counts:{control:2,observed:2},gene_count:100},embedding:'pca',analysisId:'a'})
 measured=setup('MeasuredProjection.vue',measuredProps)
 for(const group of ['all','control','observed']) {
  measured.group.value=group
  await vue.nextTick()
  const option=measured.option()
  assert.deepEqual([option.xAxis.min,option.xAxis.max,option.yAxis.min,option.yAxis.max],[-14,44,-24,34])
 }
 assert.ok(measured.option().tooltip.formatter({seriesName:'扰动实测',data:{point:points[2]}}).includes('&lt;img'))
 props.recordId='record-b'
 measuredProps.analysisId='b'
 await vue.nextTick()
 assert.equal(canvas.group.value,'all')
 assert.equal(canvas.selected.value,null)
 assert.equal(canvas.embedding.value,'pca')
 assert.equal(measured.group.value,'all')
})
scope.stop()
console.log('Research canvas: shared domains, finite coordinates, explicit ER/Golgi metadata, safe point identity, selection context, record reset and zoom restore passed')
