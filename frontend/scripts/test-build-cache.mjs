import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { strict as assert } from 'node:assert'
import { test } from 'node:test'
import { isBuildCurrent, saveBuildState, sourceFingerprint } from './build-cache.mjs'

test('reuse only a complete build of identical inputs, environment and outputs', () => {
  const root = mkdtempSync(join(tmpdir(), 'celllens-build-'))
  try {
    for (const dir of ['src', 'scripts', 'dist/assets']) mkdirSync(join(root, dir), { recursive: true })
    writeFileSync(join(root, 'src', 'App.vue'), '<template>current</template>')
    writeFileSync(join(root, 'package.json'), '{}')
    writeFileSync(join(root, 'dist', 'index.html'), '<script src="/assets/app.js"></script>')
    writeFileSync(join(root, 'dist', 'assets', 'app.js'), 'application')
    const env = { VITE_API_BASE: '/api', CELLLENS_API_PROXY_TARGET: 'http://localhost:8000' }
    assert.equal(isBuildCurrent(root, env), false)
    saveBuildState(root, sourceFingerprint(root, env), env)
    assert.equal(isBuildCurrent(root, env), true)
    assert.equal(isBuildCurrent(root, { ...env, VITE_API_BASE: '/other' }), false)
    const source = join(root, 'src', 'App.vue'), original = readFileSync(source)
    writeFileSync(source, '<template>changed</template>')
    assert.equal(isBuildCurrent(root, env), false)
    assert.throws(() => saveBuildState(root, sourceFingerprint(root, env) + 'stale', env), /changed during build/)
    writeFileSync(source, original)
    assert.equal(isBuildCurrent(root, env), true)
    writeFileSync(join(root, 'package-lock.json'), '{"lockfileVersion":3}')
    assert.equal(isBuildCurrent(root, env), false)
    rmSync(join(root, 'package-lock.json'))
    assert.equal(isBuildCurrent(root, env), true)
    writeFileSync(join(root, 'dist', 'assets', 'app.js'), 'tampered output')
    assert.equal(isBuildCurrent(root, env), false)
    saveBuildState(root, sourceFingerprint(root, env), env)
    rmSync(join(root, 'dist', 'assets', 'app.js'))
    assert.equal(isBuildCurrent(root, env), false)
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test('shared biology display translations invalidate the frontend build', () => {
  const workspace = mkdtempSync(join(tmpdir(), 'celllens-build-localization-'))
  try {
    const root = join(workspace, 'frontend')
    const resources = join(workspace, 'backend', 'app', 'resources')
    mkdirSync(join(root, 'dist'), { recursive: true })
    mkdirSync(resources, { recursive: true })
    writeFileSync(join(root, 'index.html'), '<main></main>')
    writeFileSync(join(root, 'dist', 'index.html'), '<main>compiled</main>')
    const dictionary = join(resources, 'biology_zh.json')
    writeFileSync(dictionary, JSON.stringify({ task_names: { original: '旧译名' } }))
    saveBuildState(root, sourceFingerprint(root, {}), {})
    assert.equal(isBuildCurrent(root, {}), true)
    writeFileSync(dictionary, JSON.stringify({ task_names: { original: '新译名' } }))
    assert.equal(isBuildCurrent(root, {}), false)
  } finally {
    assert.ok(workspace.startsWith(join(tmpdir(), 'celllens-build-localization-')))
    rmSync(workspace, { recursive: true, force: true })
  }
})
