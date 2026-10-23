import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

const schema = 1
const statePath = root => join(root, '.cache', 'build-state.json')

function filesUnder(directory) {
  if (!existsSync(directory)) return []
  return readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))
    .flatMap(entry => entry.isDirectory() ? filesUnder(join(directory, entry.name)) : [join(directory, entry.name)])
}

const digest = path => createHash('sha256').update(readFileSync(path)).digest('hex')
const outputDigests = root => filesUnder(join(root, 'dist')).map(path => ({
  path: relative(join(root, 'dist'), path).replaceAll('\\', '/'), sha256: digest(path),
}))

export function sourceFingerprint(root, env = process.env) {
  const hash = createHash('sha256').update(`celllens-build-${schema}:${process.version}:${process.platform}:${process.arch}`)
  const topLevel = readdirSync(root, { withFileTypes: true })
    .filter(entry => entry.isFile() && (/\.(?:json|[cm]?[jt]s)$/.test(entry.name) || entry.name.startsWith('.env')))
    .map(entry => join(root, entry.name))
  const inputs = [...topLevel, join(root, 'index.html'), join(root, 'node_modules', '.package-lock.json'),
    join(root, '..', 'backend', 'app', 'resources', 'biology_zh.json'),
    ...['src', 'public', 'scripts'].flatMap(name => filesUnder(join(root, name)))]
  for (const path of [...new Set(inputs)].filter(existsSync).sort()) {
    hash.update(relative(root, path).replaceAll('\\', '/') + '\0').update(readFileSync(path)).update('\0')
  }
  const relevant = Object.keys(env).filter(key => key.startsWith('VITE_') ||
    ['NODE_ENV', 'NODE_OPTIONS', 'CELLLENS_API_PROXY_TARGET'].includes(key)).sort()
  for (const key of relevant) hash.update(key + '\0' + env[key] + '\0')
  return hash.digest('hex')
}

export function isBuildCurrent(root, env = process.env) {
  try {
    const state = JSON.parse(readFileSync(statePath(root), 'utf8'))
    return state.schema === schema && state.inputHash === sourceFingerprint(root, env) &&
      state.outputs.some(output => output.path === 'index.html') &&
      JSON.stringify(state.outputs) === JSON.stringify(outputDigests(root))
  } catch { return false }
}

export function saveBuildState(root, inputHash, env = process.env) {
  if (inputHash !== sourceFingerprint(root, env)) throw new Error('Frontend inputs changed during build; rebuild before reuse')
  const outputs = outputDigests(root)
  if (!outputs.some(output => output.path === 'index.html')) throw new Error('Frontend build has no index.html')
  mkdirSync(join(root, '.cache'), { recursive: true })
  writeFileSync(statePath(root), JSON.stringify({ schema, inputHash, outputs }, null, 2))
}
