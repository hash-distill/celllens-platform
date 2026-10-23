import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import ts from 'typescript'

const sourceUrl = new URL('../src/utils/resultOverview.ts', import.meta.url)
assert.ok(existsSync(sourceUrl), 'Result overview data helpers must exist')
const compiled = ts.transpileModule(readFileSync(sourceUrl, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
}).outputText
const { finiteValue, coverageState, rankTasks, rankGenes, comparisonBars } = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))
const row = (id, values = {}) => ({ id, control: null, delta: null, ...values })

assert.equal(finiteValue(0), 0)
for (const value of [null, undefined, NaN, Infinity, -Infinity, '0']) assert.equal(finiteValue(value), null)
assert.equal(coverageState(1), 'full')
assert.equal(coverageState(0), 'partial')
assert.equal(coverageState(0.999), 'partial')
for (const value of [null, undefined, NaN, Infinity, -0.1, 1.1]) assert.equal(coverageState(value), 'unknown')

const tasks = [row('large-incomplete', { coverage: 0.5, delta: 999 }), row('unknown', { delta: 500 }), row('complete-small', { coverage: 1, delta: 1 }), row('complete-large', { coverage: 1, delta: -2 }), row('more-covered', { coverage: 0.8, delta: 0 })]
assert.deepEqual(rankTasks(tasks).map(task => task.id), ['complete-large', 'complete-small', 'more-covered', 'large-incomplete', 'unknown'])
assert.equal(tasks[0].id, 'large-incomplete', 'Sorting must not mutate source evidence')
assert.deepEqual(rankGenes([row('missing'), row('zero', { delta: 0 }), row('negative', { delta: -5 }), row('positive', { delta: 2 })]).map(gene => gene.id), ['negative', 'positive', 'zero', 'missing'])

const mixed = comparisonBars(row('signed', { control: -2, predicted: 6, observed: 2 }), 'run')
assert.deepEqual(mixed.domain, [-2, 6])
assert.equal(mixed.zero, 25)
assert.deepEqual(mixed.bars.map(bar => [bar.source, bar.start, bar.width]), [['control', 0, 25], ['predicted', 25, 75], ['observed', 25, 25]])
const missing = comparisonBars(row('missing', { control: 0, predicted: Infinity }), 'run')
assert.equal(missing.bars[0].value, 0)
assert.equal(missing.bars[0].width, 0)
assert.equal(missing.bars[1].value, null)
assert.equal(missing.bars[1].width, null)
assert.deepEqual(comparisonBars(row('observed', { control: 2, predicted: 1000, observed: 4 }), 'measured').domain, [0, 4])
assert.deepEqual(comparisonBars(row('observed'), 'measured').bars.map(bar => bar.source), ['control', 'observed'])
assert.equal(comparisonBars(row('empty'), 'run').hasValues, false)
assert.equal(comparisonBars(row('zero', { control: 0 }), 'run').hasValues, true)
console.log('Result overview: finite/missing values, coverage order, signed shared scale and measured-only comparison passed')
