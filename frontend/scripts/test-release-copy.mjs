import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { test } from 'node:test'

const source = path => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')

test('page copy does not brand the system as a test release', () => {
  for (const directory of ['src/views', 'src/components']) {
    for (const filename of readdirSync(new URL(`../${directory}`, import.meta.url))) {
      if (!filename.endsWith('.vue')) continue
      assert.doesNotMatch(source(`${directory}/${filename}`), /测试版|预览版|开发版|内测版|公测版|试运行版/)
    }
  }
  assert.doesNotMatch(source('src/views/HomeView.vue'), /展示页面不只是好看/)
})

test('synthetic-result messages describe their source without development jargon', () => {
  assert.doesNotMatch(source('src/fixtures/mockApi.ts'), /message:\s*'开发演示模式/)
  assert.doesNotMatch(source('src/api/client.ts'), /message:\s*'Mock |new Error\('Mock /)
  assert.match(source('src/utils/source.ts'), /合成示例|合成数据/)
  assert.match(source('src/App.vue'), /当前显示合成示例/)
})

test('connection checks and scientific limitations remain explicit', () => {
  assert.match(source('src/components/ModelConnectionSettings.vue'), /测试连接/)
  assert.match(source('src/views/AboutView.vue'), /这不代表模型的独立泛化已验证/)
  assert.match(source('src/views/AboutView.vue'), /评分也不等于实测代谢通量/)
})

test('routine explanations do not occupy blue notice boxes', () => {
  for (const path of ['src/views/WorkbenchView.vue', 'src/components/tabs/ValidationTab.vue', 'src/components/tabs/MeasuredComparisonTab.vue', 'src/components/tabs/MetabolismTab.vue']) {
    assert.equal(source(path).includes('notice-info'), false, path)
  }
  assert.match(source('src/views/WorkbenchView.vue'), /原运行群体/)
  assert.match(source('src/components/tabs/MeasuredComparisonTab.vue'), /scCellFie 计算/)
  assert.doesNotMatch(source('src/views/ResearchView.vue'), /\.experiment-description\{[^}]*background:/)
  assert.doesNotMatch(source('src/components/MeasuredSetup.vue'), /\.coverage-state\{[^}]*background:/)
})
