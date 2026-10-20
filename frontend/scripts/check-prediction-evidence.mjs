import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

const source = await readFile(new URL('../src/utils/predictionEvidence.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.ESNext}}).outputText
const {hasPredictionChange, predictionTrace} = await import('data:text/javascript;base64,' + Buffer.from(compiled).toString('base64'))
const valid = {control: 2, predicted: 1, predicted_delta: -1}
assert.ok(hasPredictionChange(valid))
assert.ok(hasPredictionChange({control: 0, predicted: 1, predicted_delta: 1}))
for (const field of ['control', 'predicted', 'predicted_delta']) {
  for (const value of [null, undefined, NaN, Infinity, -Infinity, '1']) {
    assert.equal(hasPredictionChange({...valid, [field]: value}), false)
  }
}
assert.equal(hasPredictionChange({...valid, predicted_delta: 0}), false)
const gene = {...valid, id: 'scored-gene'}
const reaction = {...valid, id: 'scored-reaction', genes: [gene, {...gene, id: 'unscored-gene', control: null}], gene_rule: 'scored-gene OR unscored-gene', total_genes: 2}
const trace = {task: valid, reactions: [reaction, {...reaction, id: 'unscored-reaction', predicted: null}, {...reaction, id: 'no-scored-genes', genes: [{...gene, predicted_delta: 0}]}], determinant_genes: ['unsupported-driver'], total_reactions: 3}
const frozen = structuredClone(trace)
const filtered = predictionTrace(trace)
assert.equal(filtered.total_reactions, 1)
assert.equal(filtered.reactions[0].total_genes, 1)
assert.equal(filtered.reactions[0].genes[0].id, 'scored-gene')
assert.equal(filtered.reactions[0].gene_rule, null)
assert.deepEqual(filtered.determinant_genes, [])
assert.deepEqual(trace, frozen)
assert.equal(predictionTrace({...trace, task: {...valid, control: null}}), null)
console.log('Prediction evidence: finite/nonzero checks, scored paths, no unsupported attribution, frozen source preserved.')
