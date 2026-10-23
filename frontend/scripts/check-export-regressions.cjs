const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const ts = require('typescript')
const root = path.resolve(__dirname, '..')
const cache = new Map()
function read(relative) { return fs.readFileSync(path.join(root, relative), 'utf8') }
function load(relative) {
  const filename = path.join(root, relative)
  if (cache.has(filename)) return cache.get(filename)
  const exports = {}, module = { exports }
  const source = read(relative).replace(/import\.meta\.env/g, '({DEV:false})')
  const code = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText
  const requireLocal = id => id.startsWith('.') ? load(path.relative(root, path.resolve(path.dirname(filename), id + '.ts'))) : require(id)
  vm.runInThisContext(`(function(require,module,exports){${code}\n})`, {filename})(requireLocal, module, exports)
  cache.set(filename, module.exports)
  return module.exports
}
async function main() {
  assert.match(read('src/components/function/FunctionWorkspace.vue'), /rawTrace/, 'F1: complete raw trace must be retained separately from display trace')
  const {buildTraceExport, buildCoverageExport} = load('src/utils/exportArtifacts.ts')
  const {predictionTrace} = load('src/utils/predictionEvidence.ts')
  const raw = {schema_version:1,scope:'all',run_id:'run_fixture',task:{id:'任务/α',control:1,predicted:2,predicted_delta:1},total_reactions:3,truncated:false,determinant_genes:[],warnings:['preserve me'],reactions:[
    {id:'changed',control:1,predicted:2,predicted_delta:1,total_genes:2,gene_rule:'A or B',genes:[{id:'A',control:1,predicted:2,predicted_delta:1},{id:'B',control:1,predicted:1,predicted_delta:0}]},
    {id:'unchanged',control:1,predicted:1,predicted_delta:0,total_genes:1,gene_rule:'C',genes:[{id:'C',control:1,predicted:1,predicted_delta:0}]},
    {id:'missing',control:null,predicted:null,predicted_delta:null,total_genes:1,gene_rule:'D',genes:[{id:'D',control:null,predicted:null,predicted_delta:null}]},
  ]}
  const before = JSON.stringify(raw), display = predictionTrace(raw)
  const result = buildTraceExport(raw, display, {selected_reaction:'changed',embedding:'umap',space:'metabolic'})
  assert.equal(JSON.stringify(raw), before, 'export must not mutate source')
  for (const key of Object.keys(raw)) assert.deepEqual(result[key], raw[key], `raw field ${key}`)
  assert.equal(result.display.source_counts.reactions, 3)
  assert.equal(result.display.source_counts.gene_associations, 4)
  assert.equal(result.display.displayed_counts.reactions, 1)
  assert.equal(result.display.displayed_counts.gene_associations, 1)
  const catalogue = {schema_version:1,parameters:{threshold:1},implementation_sha256:'frozen',warnings:['warning'],panel_gene_count:2,source:{id:'K562'},genes:[{symbol:'基因α',in_panel:true,reactions:['R1','R2','Rmissing'],tasks:['任务α']},{symbol:'B',in_panel:false,reactions:['R3'],tasks:[]}],tasks:[{id:'任务α',coverage_status:'partial',n_present_all:1},{id:'uncovered',coverage_status:'absent',n_present_all:0}],reactions:[{id:'R1',n_genes_all:1,n_present_all:1,n_missing_all:0},{id:'R2',n_genes_all:2,n_present_all:1,n_missing_all:1},{id:'R3',n_genes_all:1,n_present_all:0,n_missing_all:1}]}
  const coverage = buildCoverageExport(catalogue)
  for (const key of ['schema_version','parameters','implementation_sha256','warnings','panel_gene_count']) assert.deepEqual(coverage[key], catalogue[key])
  const ids = new Set(coverage.reactions.map(row => row.id))
  for (const gene of coverage.genes) for (const id of gene.reactions) assert.ok(ids.has(id) || coverage.omitted_references.reactions.some(row => row.id === id), `unresolved ${id}`)
  assert.equal(coverage.reaction_counts.exported, 3)
  assert.equal(coverage.reaction_counts.fully_covered, 1)
  assert.equal(coverage.reaction_counts.partially_covered, 1)
  assert.equal(coverage.task_counts.partially_covered, 1)
  assert.equal(coverage.genes[0].symbol, '基因α')
  assert.ok(coverage.inclusion_policy)
  const {featureFilenameToken, fetchDownload} = load('src/utils/download.ts')
  const token = await featureFilenameToken('任务/α')
  assert.match(token, /^[A-Za-z0-9_-]+-[0-9a-f]{8}$/)
  assert.notEqual(token, await featureFilenameToken('任务/β'))
  assert.notEqual(await featureFilenameToken('ALDOA'), await featureFilenameToken('ALDOB'))
  const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  const {createHash} = require('node:crypto')
  const featureVectors = ['', 'abc', 'ALDOA', 'MT-ATP6', 'ND3', '任务/α', '任务/β', '-_任务 / α:()!?_-', '🧬表达\u0000', ...[55,56,63,64,65,128,1000].map(length => 'x'.repeat(length)), '中文任务'.repeat(40)]
  const expectedTokens = featureVectors.map(feature => {
    const slug = feature.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^[_-]+|[_-]+$/g, '').slice(0,48) || 'feature'
    return `${slug}-${createHash('sha256').update(feature,'utf8').digest('hex').slice(0,8)}`
  })
  for (let index=0; index<featureVectors.length; index++) assert.equal(await featureFilenameToken(featureVectors[index]), expectedTokens[index], 'WebCrypto filename contract')
  try {
    for (const availableCrypto of [undefined, {}, {subtle:undefined}]) {
      Object.defineProperty(globalThis, 'crypto', {configurable:true,writable:true,value:availableCrypto})
      for (let index=0; index<featureVectors.length; index++) assert.equal(await featureFilenameToken(featureVectors[index]), expectedTokens[index], `HTTP portable SHA256 for ${JSON.stringify(featureVectors[index])}`)
    }
  } finally {
    if (cryptoDescriptor) Object.defineProperty(globalThis, 'crypto', cryptoDescriptor)
    else delete globalThis.crypto
  }
  const originalFetch = global.fetch
  global.window = {location:{origin:'http://localhost'},setTimeout,clearTimeout}
  try {
    global.fetch = async () => new Response('not csv', {headers:{'content-type':'text/html'}})
    await assert.rejects(fetchDownload('/x', {format:'csv',filename:'x.csv'}), /文件类型/)
    global.fetch = async () => new Response('{"detail":{"message":"precise error"}}', {status:409,headers:{'content-type':'application/json'}})
    await assert.rejects(fetchDownload('/x', {format:'csv',filename:'x.csv'}), /precise error/)
    global.fetch = async () => new Response('a,b\n1,2', {headers:{'content-type':'text/csv','content-disposition':'attachment; filename="wrong.html"'}})
    await assert.rejects(fetchDownload('/x', {format:'csv',filename:'x.csv'}), /文件后缀/)
    global.fetch = async () => new Response('a,b\n1,2', {headers:{'content-type':'text/csv','content-disposition':"attachment; filename*=UTF-8''%E5%9F%BA%E5%9B%A0.csv"}})
    assert.equal((await fetchDownload('/x', {format:'csv',filename:'x.csv'})).filename, '基因.csv')
    global.fetch = async () => new Response('not a pdf', {headers:{'content-type':'application/pdf'}})
    await assert.rejects(fetchDownload('/x', {format:'pdf',filename:'x.pdf'}), /内容/)
    const aborted = new AbortController(); aborted.abort()
    let called = false
    global.fetch = async () => {called=true; return new Response('a,b', {headers:{'content-type':'text/csv'}})}
    await assert.rejects(fetchDownload('/x', {format:'csv',filename:'x.csv',signal:aborted.signal}), /取消/)
    assert.equal(called, false)
    global.fetch = async (_url, opts) => new Promise((_resolve, reject) => opts.signal.addEventListener('abort', () => reject(new DOMException('Aborted','AbortError'))))
    await assert.rejects(fetchDownload('/x', {format:'csv',filename:'x.csv',timeoutMs:5}), /超时/)
  } finally {global.fetch = originalFetch}
  const {buildCsv} = load('src/utils/csv.ts')
  assert.equal(buildCsv(['text','number'], [['=1+1',-2]]), "text,number\r\n'=1+1,-2")
  assert.equal(buildCsv(['text'], [['\t@SUM(1,2)']]), 'text\r\n"\'\t@SUM(1,2)"')
  for (const [file, expected] of [
    ['src/components/function/FunctionWorkspace.vue', /导出完整关联 JSON/],
    ['src/views/CoverageView.vue', /buildCoverageExport\(data.value\)/],
    ['src/components/tabs/GenesTab.vue', /getExportTable/],
    ['src/views/WorkbenchView.vue', /single-cell/],
  ]) assert.match(read(file), expected)
  console.log('PASS: raw trace/GPR, reference closure, feature identity, download validation/cancellation, CSV text safety, UI wiring')
}
main().catch(error => {console.error(error); process.exitCode=1})
