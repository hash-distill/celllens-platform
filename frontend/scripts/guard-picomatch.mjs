// Temporary mitigation for GHSA-fc5q-39xc-vjpf until a patched release is available.
// CellLens uses ordinary path globs. Reject repeated extglobs during parsing.
import { createHash } from 'node:crypto'
import { createRequire } from 'node:module'
import { readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'

const require = createRequire(import.meta.url)
const scriptRoot = dirname(require.resolve('../package.json'))
const metadata = join(scriptRoot, 'node_modules', 'picomatch', 'package.json')
let present = true
try { readFileSync(metadata) } catch (error) {
  if (error.code !== 'ENOENT') throw error
  present = false // npm ci --omit=dev
}
if (present) {
  const file = join(dirname(metadata), 'lib', 'parse.js')
  const source = readFileSync(file, 'utf8')
  const anchor = '  const extglobOpen = (type, value) => {'
  const guard = anchor + "\n    if (type === 'plus' || type === 'star') throw new SyntaxError('Repeated extglobs disabled by CellLens');"
  const original = source.replace(guard, anchor)
  const digest = createHash('sha256').update(original).digest('hex')
  if (digest !== '4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4' || !original.includes(anchor)) {
    throw new Error('Review the picomatch mitigation for the new parser version')
  }
  if (source === original) {
    const temporary = file + '.celllens-' + process.pid
    writeFileSync(temporary, original.replace(anchor, guard), {flag: 'wx'})
    renameSync(temporary, file)
  }
}
