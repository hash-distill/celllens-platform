import { mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'

const root = fileURLToPath(new URL('../', import.meta.url))
const temporary = join(root, '.cache', 'build-tmp')
mkdirSync(temporary, { recursive: true })
// Isolate build IPC files from Windows' shared user temp directory.
const env = { ...process.env, TEMP: temporary, TMP: temporary, TMPDIR: temporary }
for (const [cli, args] of [
  ['vue-tsc/bin/vue-tsc.js', ['--noEmit']],
  ['vite/bin/vite.js', ['build']],
]) {
  const result = spawnSync(process.execPath, [join(root, 'node_modules', cli), ...args], {
    cwd: root, env, stdio: 'inherit',
  })
  if (result.error) { console.error(result.error); process.exit(1) }
  if (result.status !== 0) process.exit(result.status ?? 1)
}
