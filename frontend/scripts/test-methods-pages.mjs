import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('methods shell has no duplicate heading and all four pages share one title component', () => {
  assert.doesNotMatch(source('views/MethodsView.vue'), /<h1|数据与方法/)
  for (const path of ['views/DataCatalogView.vue', 'views/ModelMethodsView.vue', 'components/DataOverview.vue', 'views/CoverageView.vue']) {
    assert.match(source(path), /<MethodsPageHeader/)
  }
  assert.match(source('components/MethodsPageHeader.vue'), /<h1>/)
})

test('background introductions are independent of API metadata and coverage title is stable', () => {
  const background = source('components/DataOverview.vue')
  assert.match(background, /v-for="background in backgrounds"/)
  assert.doesNotMatch(background, /v-else>\s*<div class="background-cards"/)
  assert.match(source('views/CoverageView.vue'), /title="代谢覆盖"/)
  assert.doesNotMatch(background, /正在读取模型与数据目录/)
})

test('control sampling explanation does not describe the historical 3000-cell pool as current', () => {
  const background = source('components/DataOverview.vue')
  assert.doesNotMatch(background, /本地提取上限设为 3000/)
  assert.match(background, /历史实验仍按自身冻结输入追溯/)
})
