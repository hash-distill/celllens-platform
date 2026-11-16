<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import CellScene from '../components/CellScene.vue'
import BrandMark from '../components/BrandMark.vue'
import UiIcon from '../components/UiIcon.vue'
import { listResearchRecords } from '../api/researchRecords'
import { dataCatalogApi, type CatalogResponse } from '../api/dataCatalog'
import { selectRecords, type ResearchRecord } from '../utils/researchRecords'
import { fmtServerTime } from '../utils/format'
import { useServiceStore } from '../stores/service'
import { accessSession } from '../stores/access'
import image2 from '../assets/optimized/image2.webp'
import image3 from '../assets/optimized/image3.webp'
import image4 from '../assets/optimized/image4.webp'

const service = useServiceStore()
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const records = ref<ResearchRecord[]>([])
const catalog = ref<CatalogResponse | null>(null)
const recordsLoading = ref(true), recordsError = ref(''), catalogError = ref('')
let recordsController: AbortController | undefined
let catalogController: AbortController | undefined
const recent = computed(() => selectRecords(records.value, { category: 'all', status: 'all', resultsOnly: false, query: '' }).slice(0, 3))
const completed = computed(() => selectRecords(records.value, { category: 'all', status: 'completed', resultsOnly: true, query: '' })[0])
const contexts = [
  { name: 'HepG2', label: '肝母细胞瘤来源细胞系', tint: 'olive' },
  { name: 'Jurkat', label: 'T 淋巴细胞系', tint: 'mint' },
  { name: 'K562', label: '白血病细胞系', tint: 'gold' },
  { name: 'RPE1', label: '视网膜色素上皮细胞系', tint: 'sage' },
]
const visibleContexts = computed(() => readOnly.value ? contexts.filter(context => catalog.value?.summary.contexts.some(item => item.cell_line === context.name)) : contexts)
const statusLabels: Record<string, string> = { completed: '已完成', failed: '失败', cancelled: '已取消', interrupted: '已中断', queued: '等待执行', pending: '等待执行', preparing: '准备数据', analysing: '分析中', running: '运行中' }
const narratives = [
  { label: '01 / OBSERVATION', title: '看见表达响应', body: '在共同坐标与群体定义下比较表达变化，让每个细胞群回到它的数据上下文。', image: image2, to: '/research?type=measured' },
  { label: '02 / INTERPRETATION', title: '连接功能线索', body: '从基因到反应与代谢任务，查看表达支持及缺失成员，提出可继续核查的问题。', image: image4, to: '/methods/coverage' },
  { label: '03 / EVIDENCE', title: '保留研究来处', body: '对照结果身份、计算定义与来源文件，为研究讨论和后续复核留下一份清晰记录。', image: image3, to: '/records?view=results' },
]
async function loadRecords() {
  recordsController?.abort()
  const current = recordsController = new AbortController()
  recordsLoading.value = true; recordsError.value = ''
  try { const result = await listResearchRecords(current.signal); if (!current.signal.aborted) records.value = result }
  catch (reason) { if (!current.signal.aborted) recordsError.value = reason instanceof Error ? reason.message : '研究记录暂时无法读取' }
  finally { if (!current.signal.aborted) recordsLoading.value = false }
}
async function loadCatalog() {
  catalogController?.abort()
  const current = catalogController = new AbortController()
  catalogError.value = ''
  try { const result = await dataCatalogApi.query({ limit: 1 }, current.signal); if (!current.signal.aborted) catalog.value = result }
  catch (reason) { if (!current.signal.aborted) catalogError.value = reason instanceof Error ? reason.message : '覆盖信息暂时无法读取' }
}
function coverage(name: string) { return catalog.value?.summary.contexts.find(item => item.cell_line === name) }
function checkLabel(value: boolean | undefined) { return value === true ? '就绪' : value === false ? '未就绪' : '待核验' }
onMounted(() => { void loadRecords(); void loadCatalog() })
onBeforeUnmount(() => { recordsController?.abort(); catalogController?.abort() })
</script>

<template>
  <div class="national-page national-home">
    <section class="portal-hero" aria-labelledby="portal-title">
      <div class="portal-hero-copy">
        <span class="portal-kicker">OBSERVE. INTERPRET. DISCOVER.</span>
        <h1 id="portal-title">让细胞变化，<br>成为<span>可追溯的发现。</span></h1>
        <p>分析实测单细胞数据，或预测基因扰动后的表达响应。查看表达差异、功能支持与来源记录，为实验讨论和后续验证提供可核查的线索。</p>
        <div class="portal-hero-actions"><RouterLink :to="readOnly?'/records?view=results':'/research'" class="portal-button portal-lime">{{readOnly?'浏览已发布案例':'开启一项研究'}} <UiIcon name="arrow" :size="17" /></RouterLink><RouterLink :to="completed?.target ?? '/data-catalog'" class="portal-button portal-ghost"><UiIcon :name="completed ? 'play' : 'layers'" :size="15" />{{ completed ? '探索已完成研究' : '探索公开数据' }}</RouterLink></div>
        <div class="portal-hero-principles"><span><i/>多视图联动</span><span><i/>实测与预测分层</span><span><i/>来源与方法可查</span></div>
      </div>
      <div class="portal-hero-visual"><span class="portal-watermark" aria-hidden="true">C</span><CellScene /></div>
    </section>

    <section aria-labelledby="pathways-title">
      <div class="portal-section-heading"><h2 id="pathways-title">选择一项分析任务 <span>RESEARCH TASKS</span></h2><RouterLink to="/about" class="portal-text-link">了解研究流程 <UiIcon name="arrow" :size="15" /></RouterLink></div>
      <div class="portal-pathways">
        <RouterLink :to="readOnly?'/records?category=measured':'/research?type=measured'" class="portal-pathway path-observe"><span class="path-index">01 / OBSERVE</span><h3>实测数据分析</h3><p>公开数据或自有 H5AD → 比较对照与扰动的表达变化、功能支持。</p><svg class="path-art" viewBox="0 0 130 100" aria-hidden="true"><g fill="none" stroke="#67906c" stroke-width="1.4"><ellipse cx="66" cy="50" rx="43" ry="36"/><ellipse cx="66" cy="50" rx="34" ry="28" stroke-dasharray="3 4"/><path d="M34 61Q63 15 96 52M37 40Q71 82 97 48" opacity=".6"/></g><g fill="#8eae80"><circle cx="65" cy="47" r="15"/><circle cx="89" cy="36" r="5"/><circle cx="41" cy="60" r="4"/></g><circle cx="64" cy="45" r="5" fill="#d4e3b6"/><circle cx="89" cy="36" r="3" fill="#c2ae70"/></svg><span class="path-arrow">↗</span></RouterLink>
        <RouterLink :to="readOnly?'/records?category=predicted':'/research?type=prediction'" class="portal-pathway path-predict"><span class="path-index">02 / PREDICT</span><h3>基因扰动预测</h3><p>细胞背景与目标基因 → 预测表达响应，在有实测时查看诊断对照。</p><svg class="path-art" viewBox="0 0 130 100" aria-hidden="true"><g fill="none" stroke="#6b9e98" stroke-width="1.2"><path d="m28 25 38 22 36-26M66 47v32M28 25v50l38-28 36 27V21M28 75l38 4 36-5"/><path d="m28 25 74 49M28 75l74-54" stroke-dasharray="3 4"/></g><g fill="#96b9ac" stroke="#d5e5d7" stroke-width="4"><circle cx="28" cy="25" r="8"/><circle cx="102" cy="21" r="8"/><circle cx="28" cy="75" r="8"/><circle cx="102" cy="74" r="8"/><circle cx="66" cy="47" r="12"/><circle cx="66" cy="79" r="7"/></g></svg><span class="path-arrow">↗</span></RouterLink>
      </div>
    </section>

    <div class="portal-middle">
      <section aria-labelledby="recent-title"><div class="portal-section-heading"><h2 id="recent-title">继续探索 <span>RECENT STUDIES</span></h2><RouterLink to="/records" class="portal-text-link">全部记录 <UiIcon name="arrow" :size="15" /></RouterLink></div>
        <div class="portal-panel portal-recent" :aria-busy="recordsLoading">
          <div v-if="recordsLoading" class="portal-empty" role="status"><span class="portal-loader"/>正在读取近期研究…</div>
          <div v-else-if="recordsError" class="portal-empty" role="alert"><strong>暂时无法读取研究记录</strong><p>{{ recordsError }}</p><button class="portal-text-link" @click="loadRecords">重新读取 <UiIcon name="reset" :size="14" /></button></div>
          <div v-else-if="!recent.length" class="portal-empty"><UiIcon name="layers" :size="28"/><strong>{{readOnly?'尚无已发布案例':'第一项研究，从这里开始'}}</strong><p>{{readOnly?'此处仅展示部署者登记的冻结结果。':'创建分析后，参数、运行状态和完成结果将在这里保留。'}}</p><RouterLink :to="readOnly?'/records':'/research'" class="portal-text-link">{{readOnly?'浏览案例目录':'新建研究'}} <UiIcon name="arrow" :size="14" /></RouterLink></div>
          <RouterLink v-for="(record, index) in recent" v-else :key="record.key" :to="record.target" class="portal-study"><span class="study-mark" :class="record.category">{{ ['α', 'β', 'γ'][index] }}</span><span class="study-info"><strong>{{ record.title }}</strong><small>{{ record.sourceLabel }} · {{ fmtServerTime(record.createdAt) }}</small></span><span class="portal-tag" :class="record.status === 'completed' ? 'tag-green' : record.status === 'failed' ? 'tag-rose' : 'tag-outline'">{{ statusLabels[record.status] ?? record.status }}</span><UiIcon name="arrow" :size="15" /></RouterLink>
        </div>
      </section>
      <section aria-labelledby="contexts-title"><div class="portal-section-heading"><h2 id="contexts-title">细胞背景图谱 <span>CELL CONTEXTS</span></h2><RouterLink to="/data-catalog" class="portal-text-link">浏览数据 <UiIcon name="arrow" :size="15" /></RouterLink></div>
        <div class="portal-panel"><div class="portal-contexts"><RouterLink v-for="(context, index) in visibleContexts" :key="context.name" :to="{ path: '/data-catalog', query: { cell_line: context.name } }" class="portal-context" :class="context.tint"><svg viewBox="0 0 80 72" aria-hidden="true"><path :d="index % 2 === 0 ? 'M12 27C20 7 58 8 69 28S57 64 35 64S3 48 12 27Z' : 'M17 15C33 3 59 15 66 33S57 64 35 63S2 29 17 15Z'" fill="currentColor" fill-opacity=".12" stroke="currentColor" stroke-opacity=".5"/><ellipse cx="39" cy="35" :rx="index === 0 ? 17 : 13" ry="14" fill="currentColor" fill-opacity=".38"/><ellipse cx="36" cy="32" rx="5" ry="5" fill="currentColor" fill-opacity=".6"/><path d="m20 42 6 6m28-22 4 7m-8 18 6-2" stroke="currentColor" stroke-width="3" stroke-linecap="round" opacity=".55"/></svg><strong>{{ context.name }}</strong><small>{{ context.label }}</small><span>{{ catalog?.source_verified ? (coverage(context.name)?.measured_pairs.toLocaleString() ?? '—') + ' 个实测扰动' : '覆盖待核验' }}</span></RouterLink></div><div class="portal-context-footer"><span>{{readOnly?'已发布案例白名单子集；不代表全库覆盖':'按公开来源、实测覆盖与模型支持组织'}}</span><span class="portal-tag tag-green">{{visibleContexts.length}} 个细胞背景</span></div><div v-if="catalogError" class="portal-context-error" role="status">覆盖数据读取失败 <button class="portal-text-link" @click="loadCatalog">重试</button></div></div>
      </section>
    </div>

    <section class="portal-evidence" aria-labelledby="evidence-title"><div class="portal-section-heading"><h2 id="evidence-title">两项任务，共同的证据能力 <span>EXPRESSION TO EVIDENCE</span></h2><RouterLink :to="completed?.target ?? '/records?view=results'" class="portal-text-link">{{ completed ? '打开实际结果' : '查看完成结果' }} <UiIcon name="arrow" :size="15" /></RouterLink></div><div class="portal-story-grid"><RouterLink v-for="story in narratives" :key="story.label" :to="readOnly?'/records?view=results':story.to" class="portal-story"><img :src="story.image" alt="" loading="lazy"/><div><span>{{ story.label }}</span><h3>{{ story.title }}</h3><p>{{ story.body }}</p><UiIcon name="arrow" :size="18" /></div></RouterLink></div></section>

    <section v-if="!readOnly" class="portal-capabilities" aria-label="实际服务探针状态"><div><span class="portal-kicker">RESEARCH READINESS</span><h2>每一次探索，都有清晰的能力边界</h2><p>以下状态来自服务与执行器心跳。模型资产、支持范围和数据完整性，在启动前继续核查。</p></div><div class="portal-checks"><RouterLink to="/status"><i :class="{ ready: service.checks?.database }"/><span>数据服务<strong>{{ checkLabel(service.checks?.database) }}</strong></span></RouterLink><RouterLink to="/status"><i :class="{ ready: service.capabilities?.cpu_analysis }"/><span>分析执行<strong>{{ checkLabel(service.capabilities?.cpu_analysis) }}</strong></span></RouterLink><RouterLink to="/status"><i :class="{ ready: service.capabilities?.prediction }"/><span>模型推断<strong>{{ checkLabel(service.capabilities?.prediction) }}</strong></span></RouterLink></div><RouterLink to="/status" class="portal-text-link">完整状态 <UiIcon name="arrow" :size="15" /></RouterLink></section>
    <footer class="portal-footer"><span><BrandMark :size="24"/> CellLens <i>细胞知镜</i></span><p>表达支持不等于代谢通量 · 模型预测用于假设探索 · 细胞结构为学习示意</p><RouterLink to="/about">关于与使用说明 ↗</RouterLink></footer>
  </div>
</template>
