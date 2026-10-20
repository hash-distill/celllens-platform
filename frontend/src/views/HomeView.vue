<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useCatalogStore } from '../stores/catalog'
import UiIcon from '../components/UiIcon.vue'

const catalog = useCatalogStore()

const onlineContexts = computed(() =>
  catalog.contexts.filter(ctx => ctx.online_ready).map(ctx => ctx.cell_line),
)

function storyImageStyle(url: string): { backgroundImage: string } {
  return {
    backgroundImage: `linear-gradient(180deg, rgba(251, 251, 248, 0.08), rgba(251, 251, 248, 0.42) 44%, rgba(251, 251, 248, 0.82)), radial-gradient(circle at 74% 22%, rgba(206, 228, 226, 0.38), transparent 30%), url("${url}")`,
  }
}

function browseImageStyle(url: string): { backgroundImage: string } {
  return {
    backgroundImage: `linear-gradient(180deg, rgba(251, 251, 248, 0.06), rgba(251, 251, 248, 0.28) 54%, rgba(251, 251, 248, 0.74)), linear-gradient(135deg, rgba(229, 241, 239, 0.3), rgba(255, 255, 255, 0)), url("${url}")`,
  }
}

const storySections = [
  {
    key: 'predict',
    eyebrow: 'PERTURBATION FORECAST',
    title: '从一次基因扰动开始，把变化先看见。',
    body:
      '输入细胞背景、运行模式与目标基因后，CellLens 会把预测流程组织成一条清晰的实验路径，让研究问题从一开始就有结构可循。',
    metrics: ['4 种登记背景', '64–4,096 个预测细胞', '在线 / 回放 / 对照三种模式'],
    accent: 'teal',
    image: '/image3.png',
  },
  {
    key: 'state',
    eyebrow: 'CELL STATE',
    title: '不只给结果，也把细胞状态的空间关系展开。',
    body:
      '在共同对照坐标下比较对照、预测与可用观测，结合基因或代谢任务着色，把群体迁移、分布偏移和不同区域的变化放到同一视图里阅读。',
    metrics: ['共同坐标', '逐细胞散点', '表达与任务着色'],
    accent: 'sand',
    image: '/image2.png',
  },
  {
    key: 'metabolism',
    eyebrow: 'FUNCTION LAYERS',
    title: '把表达变化一路追到代谢功能。',
    body:
      '基因响应、代谢任务、反应网络与 GPR 关系被组织成连续的解释层，让你从“发生了什么”继续追问“可能为什么会这样”。',
    metrics: ['基因响应', '任务与反应评分', '任务-反应-基因关联'],
    accent: 'slate',
    image: '/image4.png',
  },
  {
    key: 'evidence',
    eyebrow: 'TRACEABILITY',
    title: '关键结果可以回看来源、覆盖范围与导出记录。',
    body:
      '参数、版本、文件哈希、完整性信息和导出能力被放在同一条证据链里，让展示页面不只是好看，也能真正支撑研究讨论与复核。',
    metrics: ['来源记录', '完整性信息', 'CSV / HTML / SVG / PDF / PNG 导出'],
    accent: 'plum',
    image: '/image1.png',
  },
] as const

const entries = [
  {
    to: '/workbench',
    icon: 'chart',
    number: '01',
    title: '实验工作台',
    text: '从细胞背景与扰动条件开始，提交分析并阅读单细胞状态、表达变化与代谢功能。',
    action: '进入工作台',
    image: '/image3.png',
  },
  {
    to: '/records',
    icon: 'file',
    number: '02',
    title: '实验记录',
    text: '检索已运行实验，继续查看历史结果与来源，保持研究过程的连续性。',
    action: '浏览记录',
    image: '/image1.png',
  },
  {
    to: '/compare',
    icon: 'compare',
    number: '03',
    title: '实验比较',
    text: '把多个实验并排放在同一视图里，核对变化方向、强度与证据覆盖范围。',
    action: '开始比较',
    image: '/image2.png',
  },
  {
    to: '/demo',
    icon: 'play',
    number: '04',
    title: '结果解读',
    text: '沿着章节结构阅读一次完整实验，从问题提出到证据回看，逐段理解结果。',
    action: '查看解读',
    image: '/image4.png',
  },
] as const

const revealNodes = ref<HTMLElement[]>([])
const visibleKeys = ref<string[]>([])
const isAtPageBottom = ref(false)
let observer: IntersectionObserver | null = null

function setRevealNode(element: Element | { $el?: Element } | null, index: number): void {
  if (element && '$el' in element && element.$el instanceof HTMLElement) {
    revealNodes.value[index] = element.$el
    return
  }
  if (!(element instanceof HTMLElement)) return
  revealNodes.value[index] = element
}

function isVisible(key: string): boolean {
  return visibleKeys.value.includes(key)
}

function updateScrollState(): void {
  if (typeof window === 'undefined') return
  const scrollTop = window.scrollY || document.documentElement.scrollTop
  const viewportHeight = window.innerHeight
  const pageHeight = document.documentElement.scrollHeight
  isAtPageBottom.value = scrollTop + viewportHeight >= pageHeight - 24
}

function jumpPageEdge(): void {
  if (typeof window === 'undefined') return
  window.scrollTo({
    top: isAtPageBottom.value ? 0 : document.documentElement.scrollHeight,
    behavior: 'smooth',
  })
}

onMounted(() => {
  observer = new IntersectionObserver(
    entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        const key = entry.target.getAttribute('data-key')
        if (!key || visibleKeys.value.includes(key)) continue
        visibleKeys.value = [...visibleKeys.value, key]
      }
    },
    { threshold: 0.24, rootMargin: '0px 0px -8% 0px' },
  )

  for (const node of revealNodes.value) observer.observe(node)
  updateScrollState()
  window.addEventListener('scroll', updateScrollState, { passive: true })
  window.addEventListener('resize', updateScrollState)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  window.removeEventListener('scroll', updateScrollState)
  window.removeEventListener('resize', updateScrollState)
})
</script>

<template>
  <div class="home-shell">
    <div class="home-fixed-backdrop" aria-hidden="true"></div>
    <section class="home-hero">
      <div class="hero-backdrop" aria-hidden="true">
        <span class="orb orb-a"></span>
        <span class="orb orb-b"></span>
        <span class="orb orb-c"></span>
        <span class="grid-fade"></span>
      </div>

      <div class="hero-copy">
        <span class="hero-kicker">CELLLENS / SINGLE-CELL PERTURBATION</span>
        <h1>
          从扰动输入开始，
          <br />
          读懂细胞状态与功能变化。
        </h1>
        <p class="hero-lead">
          CellLens 将单细胞状态预测、基因响应分析、代谢功能解读与结果溯源整合在同一条阅读路径里，帮助你从一个扰动条件出发，逐步看到细胞如何变化、哪些功能受到影响，以及这些结果来自哪里。
        </p>

        <div class="hero-actions">
          <RouterLink to="/workbench" class="btn btn-primary hero-button">
            开始浏览
            <UiIcon name="arrow" :size="16" />
          </RouterLink>
          <RouterLink to="/about" class="btn hero-button hero-button-secondary">了解方法与数据</RouterLink>
        </div>

        <dl class="hero-metrics" aria-label="首页摘要信息">
          <div>
            <dt>AVAILABLE CONTEXTS</dt>
            <dd>{{ onlineContexts.length || '4' }}</dd>
          </div>
          <div>
            <dt>WORKFLOW LAYERS</dt>
            <dd>04</dd>
          </div>
          <div>
            <dt>OUTPUT TRAIL</dt>
            <dd>TRACEABLE</dd>
          </div>
        </dl>
      </div>

      <div class="hero-stage" aria-label="首页概念画面">
        <div class="stage-card stage-card-main">
          <span class="stage-label">RESEARCH FLOW</span>
          <h2>预测、解释、追溯</h2>
          <p>从实验设置、状态分布到功能解释，把一次分析串成连续可读的结果页面。</p>
          <div class="stage-bars">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>

        <div class="stage-card stage-card-float stage-card-top">
          <span>Single-cell state</span>
          <strong>Shared projection</strong>
        </div>
        <div class="stage-card stage-card-float stage-card-mid">
          <span>Metabolic function</span>
          <strong>Task and reaction layers</strong>
        </div>
        <div class="stage-card stage-card-float stage-card-low">
          <span>Evidence</span>
          <strong>Version, completeness, export</strong>
        </div>
        <div class="stage-ring stage-ring-a"></div>
        <div class="stage-ring stage-ring-b"></div>
      </div>
    </section>

    <section class="intro-strip">
      <div class="intro-copy">
        <span class="section-kicker">PLATFORM OVERVIEW</span>
        <h2>沿着一次实验的路径，认识系统的核心能力。</h2>
      </div>
      <p>
        从实验输入、单细胞状态到代谢功能与证据核对，下面几部分对应的是研究中最常被反复查看的几个层面。
      </p>
    </section>

    <section class="storyboard" aria-label="系统能力分段介绍">
      <article
        v-for="(section, index) in storySections"
        :key="section.key"
        :ref="element => setRevealNode(element, index)"
        class="story-panel"
        :class="[
          `accent-${section.accent}`,
          { 'story-panel-visible': isVisible(section.key) },
        ]"
        :data-key="section.key"
      >
        <div class="panel-copy">
          <span class="section-kicker">{{ section.eyebrow }}</span>
          <h3>{{ section.title }}</h3>
          <p>{{ section.body }}</p>
          <ul class="panel-points">
            <li v-for="item in section.metrics" :key="item">{{ item }}</li>
          </ul>
        </div>

        <div class="panel-visual" aria-hidden="true">
          <div class="visual-sheet visual-sheet-back"></div>
          <div class="visual-sheet visual-sheet-front">
            <div class="visual-image" :style="storyImageStyle(section.image)"></div>
            <div class="visual-scrim"></div>
            <div class="visual-content">
              <span class="visual-tag">{{ section.eyebrow }}</span>
            </div>
          </div>
          <div class="visual-glow"></div>
        </div>
      </article>
    </section>

    <section class="browse-section" aria-label="进入系统">
      <div class="browse-header">
        <span class="section-kicker">START EXPLORING</span>
        <h2>选择你要进入的部分，继续查看实验与结果。</h2>
        <p>你可以直接进入实验工作台开始分析，也可以浏览历史记录、比较不同实验，或按章节阅读一次完整结果。</p>
      </div>

      <div class="browse-grid">
        <RouterLink v-for="item in entries" :key="item.to" :to="item.to" class="browse-card">
          <div class="browse-card-media" :style="browseImageStyle(item.image)"></div>
          <div class="browse-card-top">
            <span class="browse-number">{{ item.number }}</span>
            <UiIcon :name="item.icon" :size="20" />
          </div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.text }}</p>
          <span class="browse-action">
            {{ item.action }}
            <UiIcon name="arrow" :size="15" />
          </span>
        </RouterLink>
      </div>

      <footer class="browse-foot">
        <span v-if="onlineContexts.length">当前在线推演背景：{{ onlineContexts.join('、') }}</span>
        <span v-else>实验可用性仍以工作台中的服务状态与资产状态为准</span>
        <span>模型预测用于提出研究线索，结论仍需实验验证。</span>
      </footer>
    </section>

    <Teleport to="body">
      <button
        type="button"
        class="page-edge-button"
        :class="{ 'page-edge-button-top': isAtPageBottom }"
        :aria-label="isAtPageBottom ? '返回页面顶部' : '滑动到页面底部'"
        @click="jumpPageEdge"
      >
        <UiIcon name="arrow" :size="20" />
      </button>
    </Teleport>
  </div>
</template>

<style scoped>
.home-shell {
  position: relative;
  isolation: isolate;
  max-width: 1440px;
  margin: 0 auto;
  padding: 18px 24px 72px;
}

.home-fixed-backdrop {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(244, 243, 239, 0.36), rgba(244, 243, 239, 0.14) 28%, rgba(244, 243, 239, 0.34)),
    url('/back.png');
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  opacity: 0.34;
  filter: saturate(0.96) brightness(1.02);
}

.home-shell > :not(.home-fixed-backdrop) {
  position: relative;
  z-index: 1;
}

.home-hero {
  position: relative;
  min-height: calc(100vh - 110px);
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 0.95fr);
  gap: 36px;
  align-items: center;
  padding: 42px 14px 28px;
  overflow: clip;
}

.hero-backdrop {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(10px);
  opacity: 0.8;
  animation: drift 18s ease-in-out infinite;
}

.orb-a {
  width: 380px;
  height: 380px;
  background: radial-gradient(circle, rgba(108, 164, 160, 0.34), rgba(108, 164, 160, 0));
  top: 4%;
  left: -4%;
}

.orb-b {
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(223, 203, 165, 0.26), rgba(223, 203, 165, 0));
  right: -7%;
  top: 16%;
  animation-delay: -6s;
}

.orb-c {
  width: 460px;
  height: 460px;
  background: radial-gradient(circle, rgba(124, 144, 171, 0.2), rgba(124, 144, 171, 0));
  bottom: -16%;
  left: 28%;
  animation-delay: -10s;
}

.grid-fade {
  position: absolute;
  inset: 10% 4% 6%;
  border-radius: 36px;
  background:
    linear-gradient(var(--hero-grid-overlay), var(--hero-grid-overlay-fade)),
    linear-gradient(var(--hero-grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--hero-grid-line) 1px, transparent 1px);
  background-size: auto, 34px 34px, 34px 34px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.82), rgba(0, 0, 0, 0));
}

.hero-copy,
.hero-stage {
  position: relative;
  z-index: 1;
}

.hero-kicker,
.section-kicker {
  display: inline-flex;
  align-items: center;
  letter-spacing: 0.28em;
  font-size: 10px;
  color: var(--faint);
}

.hero-copy h1 {
  max-width: 9.5em;
  margin: 24px 0 20px;
  font-size: clamp(42px, 6.1vw, 82px);
  line-height: 1.04;
  letter-spacing: -0.055em;
  font-weight: 550;
}

.hero-lead {
  max-width: 620px;
  margin: 0;
  font-size: clamp(15px, 1.5vw, 18px);
  line-height: 1.9;
  color: var(--muted);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 30px;
}

.hero-button {
  min-height: 48px;
  padding-inline: 20px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
}

.hero-button-secondary {
  background: var(--glass-bg-strong);
  border-color: var(--glass-border);
  backdrop-filter: blur(14px);
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 42px 0 0;
}

.hero-metrics div {
  padding: 18px 18px 20px;
  border: 1px solid var(--glass-border);
  border-radius: 24px;
  background: var(--glass-bg);
  backdrop-filter: blur(16px);
}

.hero-metrics dt {
  font-size: 10px;
  letter-spacing: 0.18em;
  color: var(--faint);
}

.hero-metrics dd {
  margin: 12px 0 0;
  font-size: clamp(18px, 2vw, 28px);
  font-weight: 560;
  letter-spacing: -0.04em;
}

.hero-stage {
  min-height: 620px;
  display: grid;
  place-items: center;
}

.stage-card {
  position: absolute;
  border-radius: 30px;
  background: var(--glass-bg-strong);
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(18px);
  box-shadow: 0 28px 90px rgba(45, 61, 67, 0.09);
}

.stage-card-main {
  position: relative;
  width: min(100%, 540px);
  padding: 34px;
  min-height: 380px;
}

.stage-label {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(36, 122, 112, 0.1);
  color: var(--primary-strong);
  font-size: 10px;
  letter-spacing: 0.18em;
}

.stage-card-main h2 {
  margin: 22px 0 14px;
  font-size: clamp(30px, 4vw, 46px);
  letter-spacing: -0.05em;
  font-weight: 540;
}

.stage-card-main p {
  max-width: 26em;
  margin: 0;
  color: var(--muted);
  line-height: 1.8;
}

.stage-bars {
  display: grid;
  gap: 12px;
  margin-top: 30px;
}

.stage-bars span {
  height: 11px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(36, 122, 112, 0.74), rgba(36, 122, 112, 0.08));
}

.stage-bars span:nth-child(2) {
  width: 82%;
}

.stage-bars span:nth-child(3) {
  width: 58%;
}

.stage-card-float {
  width: 240px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  animation: floatCard 11s ease-in-out infinite;
}

.stage-card-float span {
  font-size: 10px;
  letter-spacing: 0.14em;
  color: var(--faint);
}

.stage-card-float strong {
  font-size: 16px;
  font-weight: 520;
}

.stage-card-top {
  top: 6%;
  right: 4%;
}

.stage-card-mid {
  right: 0;
  bottom: 23%;
  animation-delay: -3s;
}

.stage-card-low {
  left: 4%;
  bottom: 10%;
  animation-delay: -6s;
}

.stage-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid var(--glass-border);
}

.stage-ring-a {
  width: 620px;
  height: 620px;
}

.stage-ring-b {
  width: 760px;
  height: 760px;
  border-style: dashed;
  opacity: 0.5;
}

.intro-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 20px;
  align-items: end;
  padding: 72px 14px 12px;
}

.intro-copy h2,
.browse-header h2 {
  margin-top: 10px;
  font-size: clamp(30px, 3.4vw, 52px);
  letter-spacing: -0.05em;
  line-height: 1.08;
  font-weight: 540;
}

.intro-strip p,
.browse-header p {
  max-width: 34em;
  margin: 0;
  font-size: 15px;
  line-height: 1.9;
  color: var(--muted);
}

.storyboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px 0 0;
}

.story-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 520px);
  gap: 32px;
  align-items: center;
  min-height: 64vh;
  padding: 18px 14px;
  opacity: 0.18;
  transform: translateY(56px) scale(0.985);
  transition:
    opacity 0.8s ease,
    transform 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}

.story-panel:nth-child(even) {
  grid-template-columns: minmax(320px, 520px) minmax(0, 1fr);
}

.story-panel:nth-child(even) .panel-copy {
  order: 2;
}

.story-panel:nth-child(even) .panel-visual {
  order: 1;
}

.story-panel-visible {
  opacity: 1;
  transform: translateY(0) scale(1);
}

.panel-copy {
  max-width: 590px;
}

.panel-copy h3 {
  margin: 16px 0 18px;
  font-size: clamp(34px, 4vw, 60px);
  line-height: 1.08;
  letter-spacing: -0.05em;
  font-weight: 540;
}

.panel-copy p {
  margin: 0;
  font-size: 16px;
  line-height: 1.95;
  color: var(--muted);
}

.panel-points {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin: 28px 0 0;
  padding: 0;
  list-style: none;
}

.panel-points li {
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  color: var(--muted);
  font-size: 12px;
  backdrop-filter: blur(14px);
}

.panel-visual {
  position: relative;
  min-height: 520px;
  display: grid;
  place-items: center;
}

.visual-sheet {
  position: absolute;
  width: min(100%, 470px);
  aspect-ratio: 0.9;
  border-radius: 34px;
}

.visual-sheet-back {
  transform: rotate(-8deg) translate(-18px, 18px);
  opacity: 0.48;
}

.visual-sheet-front {
  position: relative;
  overflow: hidden;
  padding: 26px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(18px);
  box-shadow: 0 28px 80px rgba(36, 47, 59, 0.08);
}

.visual-image,
.visual-scrim {
  position: absolute;
  inset: 0;
}

.visual-image {
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  opacity: 0.98;
  filter: saturate(0.9) brightness(1.04) contrast(1.02);
  transform: scale(1.01);
}

.visual-scrim {
  background:
    linear-gradient(180deg, rgba(252, 252, 250, 0.06), rgba(252, 252, 250, 0.18) 38%, rgba(252, 252, 250, 0.58)),
    radial-gradient(circle at 22% 82%, rgba(255, 255, 255, 0.22), transparent 28%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.22), rgba(255, 255, 255, 0.02));
  backdrop-filter: blur(0.5px);
}

.visual-content {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  height: 100%;
}

.visual-tag {
  display: inline-flex;
  align-self: flex-start;
  padding: 7px 12px;
  border-radius: 999px;
  background: var(--glass-tag-bg);
  font-size: 10px;
  letter-spacing: 0.18em;
  color: var(--glass-tag-ink);
}

.visual-glow {
  position: absolute;
  width: 360px;
  height: 360px;
  border-radius: 50%;
  filter: blur(28px);
  opacity: 0.8;
}

.accent-teal .visual-sheet-back,
.accent-teal .visual-glow {
  background: linear-gradient(180deg, rgba(116, 186, 176, 0.34), rgba(116, 186, 176, 0.08));
}

.accent-sand .visual-sheet-back,
.accent-sand .visual-glow {
  background: linear-gradient(180deg, rgba(222, 201, 163, 0.3), rgba(222, 201, 163, 0.08));
}

.accent-slate .visual-sheet-back,
.accent-slate .visual-glow {
  background: linear-gradient(180deg, rgba(142, 156, 176, 0.28), rgba(142, 156, 176, 0.08));
}

.accent-plum .visual-sheet-back,
.accent-plum .visual-glow {
  background: linear-gradient(180deg, rgba(171, 147, 174, 0.28), rgba(171, 147, 174, 0.08));
}

.browse-section {
  padding: 68px 14px 14px;
}

.browse-header {
  max-width: 760px;
}

.browse-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-top: 34px;
}

.browse-card {
  display: flex;
  flex-direction: column;
  min-height: 280px;
  padding: 18px;
  border-radius: 28px;
  border: 1px solid var(--glass-border);
  background: var(--glass-bg-strong);
  color: var(--ink);
  text-decoration: none;
  backdrop-filter: blur(16px);
  transition:
    transform 0.35s cubic-bezier(0.22, 1, 0.36, 1),
    border-color 0.2s ease,
    box-shadow 0.35s ease;
}

.browse-card-media {
  height: 148px;
  border-radius: 22px;
  border: 1px solid var(--image-frame-border);
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  box-shadow: inset 0 1px 0 var(--image-frame-highlight);
  filter: saturate(0.78) brightness(1.03);
}

.browse-card:hover {
  transform: translateY(-6px);
  border-color: var(--surface-tint-border);
  box-shadow: 0 20px 48px rgba(36, 47, 59, 0.08);
  text-decoration: none;
}

.browse-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--primary-strong);
}

.browse-number {
  font-size: 28px;
  letter-spacing: -0.05em;
}

.browse-card h3 {
  margin: 18px 0 12px;
  font-size: 22px;
  font-weight: 520;
}

.browse-card p {
  margin: 0;
  font-size: 13px;
  line-height: 1.9;
  color: var(--muted);
}

.browse-action {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
  padding-top: 28px;
  color: var(--primary);
  font-size: 13px;
}

.browse-foot {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 22px;
  padding-top: 18px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--faint);
}

.page-edge-button {
  position: fixed;
  right: clamp(18px, 3vw, 34px);
  bottom: clamp(18px, 3vw, 30px);
  z-index: 120;
  width: 56px;
  height: 56px;
  border: 1px solid var(--surface-tint-border-strong);
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--card) 80%, transparent);
  color: var(--primary-strong);
  box-shadow: 0 14px 34px rgba(19, 31, 35, 0.12);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  cursor: pointer;
  transition:
    transform 180ms ease,
    background-color 180ms ease,
    border-color 180ms ease,
    color 180ms ease;
}

.page-edge-button:hover {
  transform: translateY(-2px);
  background: color-mix(in srgb, var(--card) 88%, transparent);
  border-color: var(--primary-soft);
}

.page-edge-button:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 3px;
}

.page-edge-button :deep(svg) {
  transform: rotate(90deg);
  transition: transform 180ms ease;
}

.page-edge-button-top :deep(svg) {
  transform: rotate(-90deg);
}

@keyframes drift {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(0, -18px, 0) scale(1.04);
  }
}

@keyframes floatCard {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@media (max-width: 1180px) {
  .home-shell {
    padding-inline: 18px;
  }

  .home-hero,
  .intro-strip,
  .story-panel,
  .story-panel:nth-child(even) {
    grid-template-columns: 1fr;
  }

  .hero-stage {
    min-height: 560px;
  }

  .story-panel:nth-child(even) .panel-copy,
  .story-panel:nth-child(even) .panel-visual {
    order: initial;
  }

  .browse-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .home-shell {
    padding: 8px 12px 44px;
  }

  .home-hero {
    min-height: auto;
    padding-top: 24px;
  }

  .hero-copy h1 {
    max-width: none;
    font-size: clamp(38px, 14vw, 62px);
  }

  .hero-metrics,
  .browse-grid {
    grid-template-columns: 1fr;
  }

  .hero-stage {
    min-height: 500px;
  }

  .stage-card-main {
    padding: 24px;
    min-height: 320px;
  }

  .stage-card-float {
    width: min(72vw, 220px);
  }

  .stage-card-top {
    top: 4%;
    right: 2%;
  }

  .stage-card-mid {
    bottom: 20%;
  }

  .stage-card-low {
    left: 0;
    bottom: 6%;
  }

  .stage-ring-a {
    width: 420px;
    height: 420px;
  }

  .stage-ring-b {
    width: 520px;
    height: 520px;
  }

  .story-panel {
    min-height: auto;
    padding-block: 20px;
  }

  .panel-copy h3,
  .intro-copy h2,
  .browse-header h2 {
    font-size: clamp(30px, 9vw, 44px);
  }

  .panel-visual {
    min-height: 400px;
  }

  .page-edge-button {
    width: 50px;
    height: 50px;
    right: 14px;
    bottom: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb,
  .stage-card-float {
    animation: none;
  }

  .story-panel,
  .browse-card {
    transition: none;
  }

  .page-edge-button,
  .page-edge-button :deep(svg) {
    transition: none;
  }
}

:global(html[data-theme='dark']) .visual-scrim {
  background:
    linear-gradient(180deg, rgba(20, 27, 31, 0.04), rgba(20, 27, 31, 0.12) 38%, rgba(20, 27, 31, 0.48)),
    radial-gradient(circle at 22% 82%, rgba(123, 197, 187, 0.18), transparent 28%),
    linear-gradient(135deg, rgba(19, 28, 32, 0.12), rgba(19, 28, 32, 0.01));
}

:global(html[data-theme='dark']) .home-fixed-backdrop {
  background:
    linear-gradient(180deg, rgba(20, 27, 31, 0.34), rgba(20, 27, 31, 0.1) 32%, rgba(20, 27, 31, 0.3)),
    url('/back.png');
  background-position: center;
  background-repeat: no-repeat;
  background-size: cover;
  opacity: 0.34;
  filter: saturate(0.94) brightness(0.88);
}
</style>
