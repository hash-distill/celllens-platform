import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import * as vue from 'vue'
import ts from 'typescript'
import { compileScript, parse } from '@vue/compiler-sfc'
const require = createRequire(import.meta.url), noop = () => {}
const source = path => readFileSync(new URL('../src/' + path, import.meta.url), 'utf8')
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return {promise,resolve,reject} }
const flush = async () => { await vue.nextTick(); await new Promise(setImmediate); await vue.nextTick() }
function evaluate(text, modules = {}) {
  const code = ts.transpileModule(text, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText, module = {exports:{}}
  new Function('require','module','exports',code)(name => modules[name] ?? (name.endsWith('.vue') ? {} : require(name)),module,module.exports)
  return module.exports
}
const http = evaluate(source('api/http.ts').replace('import.meta.env.VITE_API_BASE', "''"))
const { uploadH5ad } = evaluate(source('api/uploads.ts'), {'./http':http})
const caps = {available:true,max_bytes:1024,max_cells:2000,max_genes:1000,max_matrix_elements:2000000}
const categorical = (name, values, extra={}) => ({name,kind:'categorical',dtype:'category',missing_count:0,unique_count:values.length,values:values.map(([label,count])=>({label,count})),truncated:false,...extra})
const metadata = () => ({upload_id:'upload-1',filename:'sample.h5ad',bytes:20,sha256:'hash',cells:60,genes:10,obs_columns:[categorical('condition',[['control',30],['ALDOA',30],['single',1]]),categorical('cell_line',[['K562',60]]),{...categorical('total_counts',[]),kind:'numeric',truncated:true,unique_count:60}]})
const frozen = () => ({import_id:'immutable-v1',cell_line:'K562',perturbation:'ALDOA',gene_count:10,manifest_sha256:'hash',group_counts:{control:30,observed:30},selected_counts:{control:30,observed:30},normalization:{input_scale:'cp10k',output_scale:'log1p_cp10k',denominator:'provided'},limitations:[]})
const file = (name='sample.h5ad',size=20) => new File([new Uint8Array(size)],name)
const renderer = vue.createRenderer({createElement:()=>({}),createText:()=>({}),createComment:()=>({}),insert:noop,remove:noop,setText:noop,setElementText:noop,patchProp:noop,parentNode:()=>null,nextSibling:()=>null})
function mount(options={}) {
  const calls=[],uploads=[],navigation=[],events=[],accessSession=vue.ref({read_only:Boolean(options.public)})
  const modules={vue,'vue-router':{useRouter:()=>({push:async to=>navigation.push(to)})},'../stores/access':{accessSession},'../api/http':{ApiError:http.ApiError,apiFetch:(path,request={})=>{calls.push({path,...request});return options.request?.(path,request) ?? Promise.resolve(path.endsWith('/capabilities')?caps:path.endsWith('/imports')?frozen():{id:'new-analysis'})}},'../api/uploads':{uploadH5ad:(selected,request)=>{uploads.push({file:selected,...request});return options.upload?.(selected,request) ?? Promise.resolve(metadata())}}}
  const component=evaluate(compileScript(parse(source('components/ControlledImport.vue')).descriptor,{id:'upload'}).content,modules).default
  component.render=()=>null
  const app=renderer.createApp(component,{onBusyChange:value=>events.push(['busy',value]),onReviewChange:value=>events.push(['review',value])}),instance=app.mount({}).$
  return{app,state:instance.setupState,calls,uploads,navigation,events,accessSession}
}
async function configure(h) {
  await flush(); await h.state.selectFile(file())
  Object.assign(h.state.form,{group_key:'condition',control_label:'control',target_label:'ALDOA',expression_scale:'cp10k',perturbation:'ALDOA'})
}

test('uploaded metadata supplies exact counted choices but never guesses expression scale or perturbation',async()=>{
  const h=mount()
  try{await flush();await h.state.selectFile(file());assert.equal(h.state.stage,2);assert.equal(h.state.form.cell_line,'K562');assert.equal(h.state.form.expression_scale,'');assert.equal(h.state.form.perturbation,'');assert.equal(h.state.ready,false);h.state.form.group_key='condition';assert.deepEqual(h.state.groupColumn.values[0],{label:'control',count:30});Object.assign(h.state.form,{control_label:'control',target_label:'ALDOA',perturbation:'ALDOA'});assert.equal(h.state.ready,false);h.state.form.expression_scale='raw_counts';assert.equal(h.state.ready,false);h.state.form.total_counts_key='condition';assert.equal(h.state.ready,false);h.state.form.total_counts_key='total_counts';assert.equal(h.state.ready,true);h.state.form.target_label='control';assert.equal(h.state.ready,false);h.state.form.target_label='single';assert.equal(h.state.ready,false);h.state.form.target_label='invented';assert.equal(h.state.ready,false);h.state.form.target_label='ALDOA';h.state.form.perturbation='中文名称';assert.equal(h.state.ready,false);h.state.form.group_key='cell_line';assert.equal(h.state.form.control_label,'');assert.equal(h.state.form.target_label,'')}finally{h.app.unmount()}
})

test('format, empty-file and size errors remain actionable and do not send uploads',async()=>{
  const h=mount()
  try{await flush();for(const [name,size,pattern] of [['sample.csv',20,/\.h5ad/],['sample.h5ad',0,/为空/],['sample.h5ad',1025,/超过/]]){await h.state.selectFile(file(name,size));assert.match(h.state.error,pattern);assert.equal(h.state.upload,null)}assert.equal(h.uploads.length,0);await h.state.selectFile(file());assert.equal(h.state.error,'');assert.equal(h.state.upload.upload_id,'upload-1')}finally{h.app.unmount()}
})

test('cancel, retry and late upload responses cannot restore stale metadata or progress',async()=>{
  const pending=[],h=mount({upload:()=>{const d=deferred();pending.push(d);return d.promise}})
  try{await flush();const old=h.state.selectFile(file());h.uploads[0].onProgress(100);assert.equal(h.state.progress,100);assert.equal(h.state.uploading,true);assert.equal(h.state.upload,null);h.state.cancelUpload();assert.equal(h.uploads[0].signal.aborted,true);assert.equal(h.state.uploading,false);const latest=h.state.selectFile(file('new.h5ad'));h.uploads[1].onProgress(40);pending[0].resolve(metadata());await old;h.uploads[0].onProgress(99);assert.equal(h.state.upload,null);assert.equal(h.state.progress,40);pending[1].resolve({...metadata(),filename:'new.h5ad'});await latest;assert.equal(h.state.upload.filename,'new.h5ad');assert.equal(h.state.uploading,false)}finally{h.app.unmount()}
})

test('failed upload releases lock, reports server error and supports retry',async()=>{
  let fail=true;const h=mount({upload:()=>fail?Promise.reject(Error('invalid HDF5 structure')):Promise.resolve(metadata())})
  try{await flush();await h.state.selectFile(file());assert.equal(h.state.error,'invalid HDF5 structure');assert.equal(h.state.locked,false);fail=false;await h.state.selectFile(h.state.selectedFile);assert.equal(h.state.error,'');assert.equal(h.state.stage,2)}finally{h.app.unmount()}
})

test('truncated columns require explicit labels and multiple backgrounds are not guessed',async()=>{
  const data=metadata();data.obs_columns[0].truncated=true;data.obs_columns[1]=categorical('cell_line',[['K562',30],['RPE1',30]])
  const h=mount({upload:()=>Promise.resolve(data)})
  try{await configure(h);assert.equal(h.state.form.cell_line,'');assert.equal(h.state.exactLabels,false);h.state.form.cell_line='K562';assert.equal(h.state.ready,true);h.state.form.target_label='another exact label';assert.equal(h.state.ready,true)}finally{h.app.unmount()}
})

test('validation uses upload ID, frozen result requires explicit review, edits and replacement invalidate it',async()=>{
  const h=mount()
  try{await configure(h);await h.state.inspect();assert.equal(h.calls.at(-1).path,'/research/uploads/upload-1/imports');assert.equal('relative_path' in h.calls.at(-1).body,false);assert.equal(h.state.stage,3);const count=h.calls.length;await h.state.create();assert.equal(h.calls.length,count,'No analysis before explicit review');h.state.form.seed=7;assert.equal(h.state.result,null);await h.state.inspect();h.state.review(true);assert.equal(h.state.reviewing,true);await h.state.create();assert.equal(h.calls.at(-1).path,'/research/imports/immutable-v1/analyses');assert.deepEqual(h.navigation,['/measured/new-analysis']);await h.state.selectFile(file('replacement.h5ad'));assert.equal(h.state.result,null);assert.equal(h.state.form.expression_scale,'');assert.ok(h.calls.some(call=>call.method==='DELETE'&&call.path==='/research/uploads/upload-1'))}finally{h.app.unmount()}
})

test('editing during validation aborts and drops a late frozen result',async()=>{
  const pending=deferred(),h=mount({request:path=>path.endsWith('/imports')?pending.promise:undefined})
  try{await configure(h);const task=h.state.inspect(),request=h.calls.at(-1);assert.equal(h.state.busy,true);h.state.form.seed=9;assert.equal(request.signal.aborted,true);pending.resolve(frozen());await task;assert.equal(h.state.result,null);assert.equal(h.state.busy,false)}finally{h.app.unmount()}
})

test('replacement waits for removal; failed removal retains its identity for retry',async()=>{
  const pending=deferred();let removal=pending.promise
  const h=mount({request:(_path,request)=>request.method==='DELETE'?removal:undefined})
  try{await configure(h);await h.state.inspect();const replacing=h.state.selectFile(file('next.h5ad'));assert.equal(h.state.locked,true);assert.equal(h.uploads.length,1);assert.equal(h.state.upload.upload_id,'upload-1');pending.reject(Error('removal unavailable'));await replacing;assert.match(h.state.error,/更换文件未完成/);assert.equal(h.state.upload.upload_id,'upload-1');assert.equal(h.uploads.length,1);assert.equal(h.state.locked,false);removal=Promise.resolve(null);await h.state.selectFile(file('next.h5ad'));assert.equal(h.uploads.length,2);assert.equal(h.state.result,null)}finally{h.app.unmount()}
})

test('read-only transition while replacing a file cannot start its delayed upload',async()=>{
  const pending=deferred(),h=mount({request:(_path,request)=>request.method==='DELETE'?pending.promise:undefined})
  try{await configure(h);const replacing=h.state.selectFile(file('next.h5ad')),request=h.calls.at(-1);h.accessSession.value={read_only:true};assert.equal(request.signal.aborted,true);pending.resolve(null);await replacing;assert.equal(h.uploads.length,1);assert.equal(h.state.upload,null)}finally{h.app.unmount()}
})

test('already expired or removed upload does not block choosing another file',async()=>{
  const h=mount({request:(_path,request)=>request.method==='DELETE'?Promise.reject(new http.ApiError({kind:'http',status:404,code:null,message:'expired',endpoint:'/research/uploads/upload-1'})):undefined})
  try{await configure(h);await h.state.selectFile(file('next.h5ad'));assert.equal(h.uploads.length,2);assert.equal(h.state.error,'')}finally{h.app.unmount()}
})

test('readonly blocks all direct actions and cancels pending upload or analysis without late navigation',async()=>{
  const publicView=mount({public:true});try{await flush();await publicView.state.selectFile(file());await publicView.state.inspect();publicView.state.result=frozen();publicView.state.review(true);await publicView.state.create();assert.equal(publicView.calls.length,0);assert.equal(publicView.uploads.length,0)}finally{publicView.app.unmount()}
  const pending=deferred(),h=mount({request:path=>path.endsWith('/analyses')?pending.promise:undefined})
  try{await configure(h);await h.state.inspect();h.state.review(true);const task=h.state.create(),request=h.calls.at(-1);h.accessSession.value={read_only:true};assert.equal(request.signal.aborted,true);assert.equal(h.state.upload,null);assert.equal(h.state.result,null);assert.equal(h.state.uncertain,true);pending.resolve({id:'late'});await task;assert.deepEqual(h.navigation,[])}finally{h.app.unmount()}
  const late=deferred(),u=mount({upload:()=>late.promise});try{await flush();const task=u.state.selectFile(file());u.accessSession.value={read_only:true};assert.equal(u.uploads[0].signal.aborted,true);late.resolve(metadata());await task;assert.equal(u.state.upload,null)}finally{u.app.unmount()}
})

test('unmount aborts upload and drops delayed metadata',async()=>{
  const pending=deferred(),h=mount({upload:()=>pending.promise});await flush();const task=h.state.selectFile(file());h.app.unmount();assert.equal(h.uploads[0].signal.aborted,true);pending.resolve(metadata());await task;assert.equal(h.state.upload,null);assert.equal(h.events.at(-1)[1],false)
})

test('upload page retains accessible file button, progress state and no server-file instructions',()=>{
  const text=source('components/ControlledImport.vue');assert.match(text,/type="file" accept="\.h5ad"/);assert.match(text,/正在读取字段/);assert.match(text,/<progress/);assert.match(text,/<button[^>]+@click="fileInput\?\.click\(\)"/);assert.doesNotMatch(text,/relative_path|受控目录|服务器路径|preparationScript/)
})

test('HTML name patterns compile under browser Unicode-set rules and accept literal hyphens',()=>{
  const patterns=[...source('components/ControlledImport.vue').matchAll(/pattern="([^"]+)"/g)].map(match=>new RegExp(`^(?:${match[1]})$`,'v'))
  assert.equal(patterns.length,2)
  assert.equal(patterns[0].test('K562-clone 1'),true)
  assert.equal(patterns[1].test('ALDOA-KO'),true)
  for(const pattern of patterns){assert.equal(pattern.test('中文'),false);assert.equal(pattern.test('name/path'),false)}
})

class FakeXHR {
  static instances=[]
  constructor(){this.upload={};this.headers={};this.status=201;this.responseText=JSON.stringify(metadata());FakeXHR.instances.push(this)}
  open(method,url){this.method=method;this.url=url}
  setRequestHeader(key,value){this.headers[key]=value}
  send(body){this.body=body}
  abort(){this.aborted=true;this.onabort?.()}
}
async function withXHR(callback){const prior=globalThis.XMLHttpRequest,win=globalThis.window;globalThis.XMLHttpRequest=FakeXHR;globalThis.window={location:{origin:'http://localhost'}};FakeXHR.instances=[];try{await callback()}finally{globalThis.XMLHttpRequest=prior;globalThis.window=win}}
test('XHR uploads raw File with encoded name, progress and 100% before metadata, preserving same-origin cookies',()=>withXHR(async()=>{
  const values=[],selected=file('实验 A.h5ad'),promise=uploadH5ad(selected,{onProgress:value=>values.push(value)}),xhr=FakeXHR.instances.at(-1)
  assert.equal(xhr.body,selected);assert.equal(xhr.method,'POST');assert.equal(new URL(xhr.url).searchParams.get('filename'),selected.name);assert.equal(xhr.headers['Content-Type'],'application/octet-stream');assert.equal(xhr.withCredentials,false);assert.equal(xhr.timeout,600000)
  xhr.upload.onprogress({lengthComputable:true,loaded:10,total:20});xhr.upload.onload();assert.deepEqual(values,[50,100]);xhr.onload();assert.equal((await promise).upload_id,'upload-1');assert.equal(xhr.upload.onprogress,null)
}))
test('XHR cancel rejects once and ignores saved late progress and response callbacks',()=>withXHR(async()=>{
  const controller=new AbortController(),values=[],promise=uploadH5ad(file(),{signal:controller.signal,onProgress:value=>values.push(value)}),xhr=FakeXHR.instances.at(-1),lateLoad=xhr.onload,lateProgress=xhr.upload.onprogress
  controller.abort();await assert.rejects(promise,error=>error.kind==='abort');assert.equal(xhr.aborted,true);lateProgress({lengthComputable:true,loaded:20,total:20});lateLoad();assert.deepEqual(values,[])
  const already=new AbortController();already.abort();await assert.rejects(uploadH5ad(file(),{signal:already.signal}),error=>error.kind==='abort');assert.equal(FakeXHR.instances.at(-1).body,undefined)
}))
test('XHR parses structured backend errors and distinguishes timeout and network failures',()=>withXHR(async()=>{
  for(const mode of ['http','timeout','network','invalid']){const promise=uploadH5ad(file()),xhr=FakeXHR.instances.at(-1);if(mode==='http'){xhr.status=413;xhr.responseText=JSON.stringify({detail:{code:'TOO_LARGE',message:'文件超过上传上限'}});xhr.onload()}else if(mode==='timeout')xhr.ontimeout();else if(mode==='network')xhr.onerror();else{xhr.responseText='unexpected';xhr.onload()}await assert.rejects(promise,error=>mode==='http'?error.code==='TOO_LARGE'&&error.status===413:error.kind===(mode==='timeout'?'timeout':'network'))}
}))
