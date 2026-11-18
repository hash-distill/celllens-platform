import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'
const require=createRequire(import.meta.url),noop=()=>{}
const flush=async()=>{for(let i=0;i<3;i++){await vue.nextTick();await new Promise(setImmediate)}}
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}}
class RequestError extends Error{constructor(kind,message){super(message);this.kind=kind}}
const renderer=vue.createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert:noop,remove:noop,setText:noop,setElementText:noop,patchProp:noop,parentNode:()=>null,nextSibling:()=>null})
const dataset=(id='sciPlex2')=>({id,title:id,version:'1.4',status:'ready',cell_count:23733,total_cell_count:24262,condition_count:16,source:{}})
const condition=(id='drug-1')=>({id,label:id,cell_line:'A549',perturbation:'drug',dose:'1',dose_unit:null,time:null,time_unit:null,control_type:'zero_dose_same_drug_label',cell_count:50,control_cell_count:100,analysis_available:true})
function mount(options={}){
 const route=vue.reactive({params:{},query:options.query??{},path:'/datasets'}),accessSession=vue.ref({read_only:Boolean(options.public)}),calls=[],navigation=[]
 const apiFetch=(path,request={})=>{calls.push({path,...request});if(options.request){const result=options.request(path,request);if(result!==undefined)return result}return Promise.resolve(path==='/datasets'?{items:[dataset(),dataset('other')]}:path.endsWith('/analyses')?{id:'new-analysis'}:{items:[condition()],total:16})}
 const modules={vue,'vue-router':{useRoute:()=>route,useRouter:()=>({push:async to=>navigation.push(to)})},'../stores/access':{accessSession},'../api/http':{apiFetch,ApiError:RequestError},'../api/measured':{measuredApi:{get:()=>new Promise(noop),coverage:()=>{throw Error('Dataset retry must not query Perturb-seq')}}},'../stores/assistantSource':{useAssistantSource:noop,openAssistant:noop},'../utils/csv':{downloadBlob:noop},'../utils/format':{fmtServerTime:x=>x},'../utils/biologyLocale':{taskName:x=>x,metabolicGroupName:x=>x}}
 const file=options.measured?'MeasuredAnalysisView.vue':'DatasetLibraryView.vue',source=readFileSync(new URL('../src/views/'+file,import.meta.url),'utf8')
 const code=ts.transpileModule(compileScript(parse(source).descriptor,{id:file}).content,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,module={exports:{}}
 new Function('require','module','exports',code)(name=>modules[name]??(name.endsWith('.vue')?{}:require(name)),module,module.exports)
 const component=module.exports.default;component.render=()=>null
 const app=renderer.createApp(component),instance=app.mount({}).$
 return{app,state:instance.setupState,route,accessSession,calls,navigation}
}

test('fresh installations render nullable counts and missing units/time truthfully',async()=>{
 const h=mount({request:path=>path==='/datasets'?Promise.resolve({items:[{...dataset(),cell_count:null,total_cell_count:null,condition_count:0,status:'needs_preparation'}]}):undefined})
 try{await flush();assert.equal(h.state.count(h.state.dataset.cell_count),'未核验');assert.equal(h.state.count(0),'0');assert.equal(h.state.quantity('10',null,'剂量'),'10 （单位未记录）');assert.equal(h.state.quantity(null,null,'处理时间'),'处理时间未记录');assert.equal(h.state.quantity(0,'h','处理时间'),'0 h');assert.match(h.state.controlLabel(condition()),/同一药物标签.*零剂量.*非已核实 DMSO/)}finally{h.app.unmount()}
})

test('dataset selection resets page before request; query and pagination stay server-filtered',async()=>{
 const h=mount()
 try{await flush();h.state.page=2;await flush();assert.equal(h.calls.at(-1).query.offset,10);h.state.selected='other';await flush();assert.equal(h.calls.at(-1).path,'/datasets/other/conditions');assert.equal(h.calls.at(-1).query.offset,0);h.state.query=' drug ';h.state.search();await flush();assert.equal(h.calls.at(-1).query.query,'drug');assert.equal(h.calls.at(-1).query.limit,10);h.route.query={dataset:'sciPlex2'};await flush();assert.equal(h.state.selected,'sciPlex2')}finally{h.app.unmount()}
})

test('latest condition request wins and corrected page remains within returned bounds',async()=>{
 const pending=[],h=mount({request:path=>{if(path.endsWith('/conditions')){const d=deferred();pending.push(d);return d.promise}}})
 try{await flush();h.state.selected='other';await flush();pending[1].resolve({items:[condition('new')],total:1});await flush();pending[0].resolve({items:[condition('old')],total:20});await flush();assert.equal(h.state.items[0].id,'new');h.state.page=3;await flush();pending[2].resolve({items:[],total:1});await flush();assert.equal(h.state.page,1);pending[3].resolve({items:[condition('new')],total:1});await flush();assert.equal(h.state.items[0].id,'new')}finally{h.app.unmount()}
})

test('catalog errors are independently retryable and condition failures never show stale rows',async()=>{
 let failCatalog=true,failConditions=false
 const h=mount({request:path=>path==='/datasets'&&failCatalog?Promise.reject(Error('catalog down')):path.endsWith('/conditions')&&failConditions?Promise.reject(Error('conditions down')):undefined})
 try{await flush();assert.equal(h.state.error,'catalog down');failCatalog=false;h.state.retryLoad();await flush();assert.equal(h.state.items.length,1);failConditions=true;h.state.refresh++;await flush();assert.equal(h.state.items.length,0);assert.equal(h.state.error,'conditions down');failConditions=false;h.state.retryLoad();await flush();assert.equal(h.state.error,'');assert.equal(h.state.items.length,1)}finally{h.app.unmount()}
})

test('read-only transitions cancel reads/submission and discard late private navigation',async()=>{
 const publicView=mount({public:true});try{await flush();assert.equal(publicView.calls.length,0)}finally{publicView.app.unmount()}
 let pending
 const h=mount({request:(path)=>{if(path.endsWith('/analyses')){pending=deferred();return pending.promise}}})
 try{await flush();const job=h.state.analyse(h.state.items[0]),request=h.calls.at(-1);h.accessSession.value={read_only:true};assert.equal(request.signal.aborted,true);assert.equal(h.state.datasets.length,0);assert.equal(h.state.items.length,0);pending.resolve({id:'late'});await job;assert.equal(h.navigation.length,0);assert.equal(h.state.uncertain,true)}finally{h.app.unmount()}
 const d=deferred(),reading=mount({request:()=>d.promise});try{const request=reading.calls[0];reading.accessSession.value={read_only:true};d.resolve({items:[dataset()]});await flush();assert.equal(request.signal.aborted,true);assert.equal(reading.state.datasets.length,0)}finally{reading.app.unmount()}
})

test('submission uses actual condition identity and blocks unavailable, stale, invalid or uncertain requests',async()=>{
 let fail=false
 const h=mount({request:path=>path.endsWith('/analyses')&&fail?Promise.reject(new RequestError('network','offline')):undefined})
 try{await flush();const before=h.calls.length;await h.state.analyse({...h.state.items[0],analysis_available:false});await h.state.analyse(condition('stale'));h.state.maxCells=0;await h.state.analyse(h.state.items[0]);assert.equal(h.calls.length,before);h.state.maxCells=64;h.state.seed=7;await h.state.analyse(h.state.items[0]);assert.deepEqual(h.calls.at(-1).body,{condition_id:'drug-1',max_cells:64,seed:7});assert.equal(h.navigation[0],'/measured/new-analysis');fail=true;await h.state.analyse(h.state.items[0]);assert.equal(h.state.uncertain,true);const after=h.calls.length;await h.state.analyse(h.state.items[0]);assert.equal(h.calls.length,after)}finally{h.app.unmount()}
})

test('catalog reload ignores an older completed request and never hides an in-flight condition load',async()=>{
 const reads=[],h=mount({request:path=>{if(path==='/datasets'){const d=deferred();reads.push(d);return d.promise}if(path.endsWith('/conditions'))return new Promise(noop)}})
 try{const second=h.state.loadDatasets();reads[1].resolve({items:[dataset('new')]});await second;await flush();assert.equal(h.state.loading,true);reads[0].resolve({items:[dataset('old')]});await flush();assert.equal(h.state.selected,'new');assert.equal(h.state.loading,true)}finally{h.app.unmount()}
})

const failedRecord=source=>({id:'old',dataset_id:'sciPlex2',condition_id:'drug-1',cell_line:'A549',perturbation:'drug',max_cells:64,seed:7,status:'failed',summary:null,...source})
test('public dataset retries preserve frozen condition and sampling without entering gene/import APIs',async()=>{
 const h=mount({measured:true})
 try{h.state.selected=failedRecord();assert.equal(h.state.imported,false);assert.equal(h.state.sourceLabel,'公开药物扰动 · 实测数据');await h.state.retry();assert.equal(h.calls[0].path,'/datasets/sciPlex2/analyses');assert.deepEqual(h.calls[0].body,{condition_id:'drug-1',max_cells:64,seed:7});assert.equal(h.navigation[0],'/measured/new-analysis');h.state.selected=failedRecord({dataset_id:null,condition_id:null,source:{dataset_id:'sciPlex2',condition_id:'frozen'}});await h.state.retry();assert.equal(h.calls.at(-1).body.condition_id,'frozen');h.state.selected=failedRecord({condition_id:null});await h.state.retry();assert.deepEqual(h.navigation.at(-1),{path:'/datasets',query:{dataset:'sciPlex2'}})}finally{h.app.unmount()}
})

test('dataset retry discards response after route/access changes and blocks public POST',async()=>{
 const d=deferred(),h=mount({measured:true,request:()=>d.promise})
 try{h.state.selected=failedRecord();const job=h.state.retry();h.accessSession.value={read_only:true};assert.equal(h.calls[0].signal.aborted,true);d.resolve({id:'late'});await job;assert.equal(h.navigation.length,0);await h.state.retry();assert.equal(h.calls.length,1)}finally{h.app.unmount()}
})
