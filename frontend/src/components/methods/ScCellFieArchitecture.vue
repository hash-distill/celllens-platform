<script setup lang="ts">
import { useId } from 'vue'
import { architectureStyle } from './architectureStyle'
const id = useId()
const arrow = `url(#${id}-arrow)`
const knowledgeArrow = `url(#${id}-knowledge)`
</script>

<template>
  <svg class="architecture-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 730" role="img" :aria-labelledby="`${id}-title ${id}-desc`">
    <title :id="`${id}-title`">scCellFie：从基因表达、GPR 反应规则到代谢任务分数</title>
    <desc :id="`${id}-desc`">CP10K 表达按冻结阈值转为基因分数，GPR 规则中 AND 取最小值、OR 取最大值。反应按决定基因特异性校正后，在任务内取均值。human Recon2 提供阈值、GPR 及任务反应映射；关联基因覆盖另行检查。</desc>
    <defs>
      <component :is="'style'">{{ architectureStyle }}</component>
      <marker :id="`${id}-arrow`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10Z" fill="#3e5e6a" /></marker>
      <marker :id="`${id}-knowledge`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 10 5 0 10Z" fill="#698b87" /></marker>
    </defs>
    <rect class="arch-paper" width="1440" height="730" />
    <text x="52" y="49" class="arch-title">scCellFie</text>
    <text x="232" y="48" class="arch-subtitle">从表达证据到代谢任务 · human Recon2</text>
    <text x="1388" y="48" text-anchor="end" class="arch-small">02 / FUNCTION</text>
    <path class="arch-rule" d="M52 70H1388" />
    <text x="64" y="113" class="arch-stage">A　表达输入</text>
    <text x="290" y="113" class="arch-stage">B　基因分数</text>
    <text x="600" y="113" class="arch-stage">C　GPR 逻辑</text>
    <text x="906" y="113" class="arch-stage">D　反应校正</text>
    <text x="1170" y="113" class="arch-stage">E　任务汇总</text>
    <text x="64" y="176" class="arch-label">CP10K 表达</text>
    <text x="64" y="203" class="arch-small">对照／预测／可用实测</text>
    <rect x="64" y="224" width="156" height="130" class="arch-matrix-frame" />
    <g v-for="row in 6" :key="row"><rect v-for="gene in 8" :key="gene" class="arch-matrix-cell" :x="73 + (gene - 1) * 18" :y="233 + (row - 1) * 19" width="12" height="14" :opacity=".15 + ((row * 3 + gene * 5) % 8) * .1" /></g>
    <path class="arch-flow" d="M220 267H276" :marker-end="arrow" />
    <rect x="276" y="170" width="270" height="200" rx="3" class="arch-box" />
    <text x="298" y="204" class="arch-label">相对于基因阈值评分</text>
    <text x="411" y="256" class="arch-math arch-center">s<tspan baseline-shift="sub" font-size="14">g</tspan> = 5 ln(1 + E<tspan baseline-shift="sub" font-size="14">g</tspan> / T<tspan baseline-shift="sub" font-size="14">g</tspan>)</text>
    <path class="arch-rule" d="M298 279H524" />
    <text x="298" y="308" class="arch-small">E_g：当前细胞的基因表达</text>
    <text x="298" y="338" class="arch-small">T_g：冻结的基因阈值</text>
    <path class="arch-flow" d="M546 267H600" :marker-end="arrow" />
    <rect x="600" y="170" width="250" height="200" rx="3" class="arch-accent" />
    <text x="622" y="204" class="arch-label">基因 → 蛋白 → 反应</text>
    <text x="622" y="250" class="arch-math">AND</text>
    <path class="arch-flow" d="M686 244H714" :marker-end="arrow" />
    <text x="726" y="250" class="arch-math">min(s<tspan baseline-shift="sub" font-size="14">a</tspan>, s<tspan baseline-shift="sub" font-size="14">b</tspan>)</text>
    <text x="622" y="291" class="arch-math">OR</text>
    <path class="arch-flow" d="M686 285H714" :marker-end="arrow" />
    <text x="726" y="291" class="arch-math">max(s<tspan baseline-shift="sub" font-size="14">a</tspan>, s<tspan baseline-shift="sub" font-size="14">b</tspan>)</text>
    <path class="arch-rule" d="M622 312H828" />
    <text x="622" y="342" class="arch-small">保留决定分数的基因 g*</text>
    <path class="arch-flow" d="M850 267H906" :marker-end="arrow" />
    <rect x="906" y="170" width="208" height="200" rx="3" class="arch-box" />
    <text x="928" y="204" class="arch-label">决定基因特异性</text>
    <text x="1010" y="256" class="arch-math arch-center">R<tspan baseline-shift="sub" font-size="14">r</tspan> = s<tspan baseline-shift="sub" font-size="14">r</tspan> / n<tspan baseline-shift="sub" font-size="14">g*</tspan></text>
    <path class="arch-rule" d="M928 279H1092" />
    <text x="928" y="307" class="arch-small">n_g*：同一细胞内</text>
    <text x="928" y="332" class="arch-small">由 g* 决定分数的</text>
    <text x="928" y="354" class="arch-small">反应数量</text>
    <path class="arch-flow" d="M1114 267H1170" :marker-end="arrow" />
    <rect x="1170" y="170" width="218" height="200" rx="3" class="arch-box" />
    <text x="1192" y="204" class="arch-label">关联反应取均值</text>
    <text x="1279" y="256" class="arch-math arch-center">M<tspan baseline-shift="sub" font-size="14">t</tspan> = Σ R<tspan baseline-shift="sub" font-size="14">r</tspan> / |R<tspan baseline-shift="sub" font-size="14">t</tspan>|</text>
    <text x="1279" y="283" class="arch-tiny arch-center">r ∈ 任务 t 的反应集合 R_t</text>
    <path class="arch-rule" d="M1192 300H1366" />
    <text x="1279" y="336" class="arch-small arch-center">逐细胞代谢任务分数</text>
    <!-- Dashed branches supply rules, independently of the solid scoring chain. -->
    <rect x="276" y="470" width="1112" height="114" rx="3" class="arch-soft" />
    <text x="300" y="506" class="arch-label">human Recon2 冻结知识库</text>
    <text x="1366" y="506" text-anchor="end" class="arch-small">虚线：知识与规则　　实线：数据计算</text>
    <path class="arch-rule" d="M300 522H1366" />
    <text x="411" y="558" class="arch-center">基因阈值 T_g</text>
    <text x="725" y="558" class="arch-center">GPR 规则</text>
    <text x="1279" y="558" class="arch-center">任务—反应映射</text>
    <path class="arch-knowledge" d="M411 470V370" :marker-end="knowledgeArrow" />
    <path class="arch-knowledge" d="M725 470V370" :marker-end="knowledgeArrow" />
    <path class="arch-knowledge" d="M1279 470V370" :marker-end="knowledgeArrow" />
    <path class="arch-flow" d="M142 354V470" :marker-end="arrow" />
    <rect x="64" y="470" width="170" height="114" rx="3" class="arch-soft" />
    <text x="149" y="506" class="arch-label arch-center">关联基因覆盖</text>
    <text x="149" y="540" class="arch-small arch-center">输入面板 ∩ 知识库</text>
    <text x="149" y="566" class="arch-tiny arch-center">与评分并行核查</text>
    <path class="arch-knowledge" d="M276 527H234" :marker-end="knowledgeArrow" />
    <path class="arch-rule" d="M64 622H1388" />
    <text x="64" y="654" class="arch-stage">同规则比较</text>
    <text x="64" y="684" class="arch-small">对照、预测、可用实测分别评分</text>
    <text x="518" y="654" class="arch-stage">当前设置</text>
    <text x="518" y="684" class="arch-small">逐细胞计算，不进行跨来源 KNN 平滑</text>
    <text x="1010" y="654" class="arch-stage">阅读边界</text>
    <text x="1010" y="684" class="arch-small">表达支持度分数，不等同于代谢通量</text>
  </svg>
</template>
