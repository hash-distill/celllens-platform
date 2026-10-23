import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { test } from 'node:test'
import ts from 'typescript'

const require = createRequire(import.meta.url)
function evaluate(path, imports = require) {
  const source = readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const code = ts.transpileModule(source, {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
  const result = {}
  new Function('require','exports',code)(imports,result)
  return result
}
const config = evaluate('utils/modelConfig.ts')

test('lengths use provider defaults unless explicitly overridden, including import and export', () => {
  const defaults = config.cleanPreferences({provider:'deepseek',model:'chosen'})
  assert.equal(defaults.max_tokens,null)
  assert.equal(defaults.context_window,null)
  const explicit = config.cleanPreferences({...defaults,max_tokens:64000,context_window:128000})
  assert.equal(explicit.max_tokens,64000)
  const restored = config.parseConnectionConfig(config.exportConnectionConfig([defaults])).connections[0]
  assert.equal(restored.max_tokens,null)
  assert.equal(restored.context_window,null)
})

test('generic JSON aliases normalize full endpoint and safely export without credentials', () => {
  const imported = config.parseConnectionConfig(JSON.stringify({name:'Lab API',baseURL:'https://api.example.org/v1/chat/completions',apiKey:'test-import-secret',model:'text-a',reasoning_effort:'high',context_window:64000}))
  assert.equal(imported.connections[0].base_url,'https://api.example.org/v1')
  assert.equal(imported.connections[0].provider,'custom')
  assert.equal(imported.connections[0].api_key,'test-import-secret')
  const exported = config.exportConnectionConfig(imported.connections)
  assert.ok(!exported.includes('test-import-secret'))
  const restored = config.parseConnectionConfig(exported).connections[0]
  assert.equal(restored.model,'text-a')
  assert.equal(restored.context_window,64000)
  assert.equal(restored.reasoning_effort,'high')
})

test('dotenv import is data only, handles quotes, and rejects shell expansion', () => {
  const imported = config.parseConnectionConfig('export OPENAI_BASE_URL="https://api.openai.com/v1"\nOPENAI_API_KEY=\'test-env-secret\'\nOPENAI_MODEL="user-model"\nAI_CONTEXT_WINDOW=64000\nAI_REASONING_EFFORT=low')
  assert.equal(imported.connections[0].provider,'openai')
  assert.equal(imported.connections[0].context_window,64000)
  assert.equal(imported.connections[0].api_key,'test-env-secret')
  assert.throws(() => config.parseConnectionConfig('OPENAI_API_KEY=${SECRET}\nOPENAI_MODEL=hi'))
})

test('multi-connection import is bounded, requires valid URLs and never echoes secrets in errors', () => {
  const values = [
    {base_url:'https://user:test-secret@example.org/v1',api_key:'test-secret'},
    {base_url:'https://example.org/v1?key=test-secret'},
    {base_url:'javascript:alert(1)'}, {context_window:2},
    {max_tokens:4096,context_window:4096}, {reasoning_effort:'arbitrary'},
    {provider:'siliconflow',reasoning_effort:'high'},
  ]
  for (const value of values) {
    assert.throws(() => config.parseConnectionConfig(JSON.stringify(value)), error => !error.message.includes('test-secret'))
  }
  assert.throws(() => config.parseConnectionConfig(' '.repeat(70000)))
  assert.throws(() => config.parseConnectionConfig(JSON.stringify({format:'celllens.ai-connections',version:999,connections:[]})))
  const imported = config.parseConnectionConfig(JSON.stringify({connections:[{name:'A',base_url:'https://a.example.org/v1'},{name:'B',base_url:'https://b.example.org/v1'}]}))
  assert.equal(imported.connections.length,2)
})

function storage() {
  const values = new Map()
  return {getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key),values}
}

test('legacy preferences migrate; profiles persist without keys; switching restores tab-only credentials', () => {
  globalThis.localStorage = storage()
  globalThis.sessionStorage = storage()
  localStorage.setItem('celllens.model',JSON.stringify({base_url:'https://api.deepseek.com',model:'old-model',max_tokens:2048}))
  sessionStorage.setItem('celllens.api-key','test-legacy-secret')
  const store = evaluate('stores/preferences.ts', name => name === '../utils/modelConfig' ? config : name === './appearance' ? {} : require(name))
  assert.equal(store.modelPreferences.provider,'deepseek')
  assert.equal(store.modelPreferences.context_window,null)
  assert.equal(store.modelPreferences.max_tokens,null)
  const original = store.activeConnectionId.value
  store.addConnection('Local', {...config.DEFAULT_MODEL,provider:'custom',base_url:'http://127.0.0.1:11434/v1',model:'local-a'},'test-second-secret')
  assert.equal(store.modelConnection().model,'local-a')
  store.selectConnection(original)
  assert.equal(store.apiKey.value,'test-legacy-secret')
  assert.equal(store.modelPreferences.model,'old-model')
  assert.ok(!JSON.stringify([...localStorage.values]).includes('secret'))
  store.clearKey()
  assert.equal(store.apiKey.value,'')
  assert.ok(!JSON.stringify([...sessionStorage.values]).includes('test-legacy-secret'))
})

test('an active profile changed by another tab cannot inherit the legacy key of a different connection', () => {
  globalThis.localStorage = storage()
  globalThis.sessionStorage = storage()
  localStorage.setItem('celllens.connection-profiles',JSON.stringify({version:1,active_id:'different',connections:[{...config.DEFAULT_MODEL,id:'different',name:'Other'}]}))
  sessionStorage.setItem('celllens.api-key','test-wrong-profile-secret')
  const store = evaluate('stores/preferences.ts', name => name === '../utils/modelConfig' ? config : name === './appearance' ? {} : require(name))
  assert.equal(store.apiKey.value,'')
})

test('existing profiles migrate all lengths once while preserving connection identity and session keys', () => {
  globalThis.localStorage = storage()
  globalThis.sessionStorage = storage()
  localStorage.setItem('celllens.connection-profiles',JSON.stringify({version:1,active_id:'lab',connections:[{...config.DEFAULT_MODEL,id:'lab',name:'Lab',model:'chosen',max_tokens:2048,context_window:32768}]}))
  sessionStorage.setItem('celllens.api-key.profiles',JSON.stringify({lab:'test-session-secret'}))
  const load = () => evaluate('stores/preferences.ts', name => name === '../utils/modelConfig' ? config : name === './appearance' ? {} : require(name))
  const store = load()
  assert.equal(store.modelPreferences.max_tokens,null)
  assert.equal(store.modelPreferences.context_window,null)
  assert.equal(store.apiKey.value,'test-session-secret')
  assert.equal(store.activeConnectionId.value,'lab')
  assert.equal(JSON.parse(localStorage.getItem('celllens.connection-profiles')).version,2)
  store.saveModel({...store.modelPreferences,max_tokens:64000,context_window:128000},store.apiKey.value)
  const reloaded = load()
  assert.equal(reloaded.modelPreferences.max_tokens,64000)
  assert.equal(reloaded.modelPreferences.context_window,128000)
  assert.ok(!JSON.stringify([...localStorage.values]).includes('test-session-secret'))
})
