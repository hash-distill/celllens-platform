import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'
const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 } }).outputText
const url = source => 'data:text/javascript;base64,' + Buffer.from(source).toString('base64')
const base = url(compile(readFileSync(new URL('../src/utils/resultOverview.ts', import.meta.url), 'utf8')))
const source = compile(readFileSync(new URL('../src/utils/metabolicVisualization.ts', import.meta.url), 'utf8')).replace("'./resultOverview'", JSON.stringify(base))
const { taskPair, scoreLabel } = await import(url(source))
const row = values => ({ id: 'task', delta: 999, ...values })
test('metabolic pairs isolate measured and predicted populations and recompute their actual difference', () => {
  const input = row({ control: 2, observed: 4, predicted: -1 })
  assert.equal(taskPair(input, 'measured').delta, 2)
  assert.equal(taskPair(input, 'run').delta, -3)
  assert.equal(input.delta, 999)
})
test('missing values never become zero or a false direction', () => {
  for (const value of [null, undefined, NaN, Infinity]) {
    const pair = taskPair(row({ control: value, observed: 0 }), 'measured')
    assert.equal(pair.direction, 'missing')
    assert.equal(pair.delta, null)
    assert.equal(pair.controlPosition, null)
    assert.equal(pair.targetPosition, 0)
  }
  assert.equal(taskPair(row({ control: 0, observed: 0 }), 'measured').direction, 'same')
  assert.equal(scoreLabel(0), '0')
  assert.equal(scoreLabel(null), '—')
})
test('each task uses its own paired domain including negative and zero values', () => {
  const negative = taskPair(row({ control: -2, observed: 6 }), 'measured')
  assert.equal(negative.zeroPosition, .25)
  assert.equal(negative.controlPosition, 0)
  assert.equal(negative.targetPosition, 1)
  assert.equal(negative.direction, 'up')
  const large = taskPair(row({ control: 200, observed: 100 }), 'measured')
  assert.equal(large.controlPosition, 1)
  assert.equal(large.targetPosition, .5)
  assert.equal(large.direction, 'down')
  assert.notEqual(scoreLabel(.0000001, true), '+0')
})
