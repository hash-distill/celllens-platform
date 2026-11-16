import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('methods shell has no duplicate heading and method pages share one title component', () => {
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

test('data atlas exposes combination lookup before overview material and retains actionable empty states', () => {
  const atlas = source('views/DataCatalogView.vue')
  for (const label of ['数据与扰动', '查询研究组合', '搜索扰动基因', '没有匹配的组合', '请重新读取目录后继续查询', '直接分析实测']) {
    assert.ok(atlas.includes(label), label)
  }
  const template = atlas.slice(atlas.indexOf('<template>'))
  assert.ok(template.indexOf('查询研究组合') < template.indexOf('细胞背景与覆盖'))
  assert.ok(template.indexOf('查询研究组合') < template.indexOf('继续了解数据图谱'))
})


test('atlas navigation connects each content purpose and retains public-case scope', () => {
  const navigation = source('components/SectionNavigation.vue')
  for (const [path, label] of [['/data-catalog','数据与扰动'], ['/methods/backgrounds','细胞与样本'], ['/methods/models','模型与方法'], ['/methods/coverage','代谢覆盖']]) {
    assert.ok(navigation.includes(`to:'${path}', label:'${label}'`))
  }
  assert.match(navigation, /accessSession\.value\?\.read_only/)
  assert.match(navigation, /案例覆盖子集/)
  assert.match(navigation, /:aria-current="item.active/)
  const coverage = source('views/CoverageView.vue')
  assert.match(coverage, /encodeURIComponent\(data\.value\.source\.id\)/)
  assert.doesNotMatch(coverage, /path:'\/demo'/)
})
