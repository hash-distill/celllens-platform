<script setup lang="ts">
import { useId } from 'vue'
import { architectureStyle } from './architectureStyle'
const id = useId()
const arrow = `url(#${id}-arrow)`
</script>

<template>
  <svg class="architecture-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1440 730" role="img" :aria-labelledby="`${id}-title ${id}-desc`">
    <title :id="`${id}-title`">STATE：当前 ST-HVG 分支的细胞集合扰动预测</title>
    <desc :id="`${id}-desc`">对照表达、单基因扰动及批次分别编码并相加。细胞集合经八层双向注意力 Transformer，输出与对照表达编码相加后解码为非负的两千基因表达。SE 不在默认推理链路中。</desc>
    <defs>
      <component :is="'style'">{{ architectureStyle }}</component>
      <marker :id="`${id}-arrow`" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0 10 5 0 10Z" fill="#3e5e6a" /></marker>
    </defs>
    <rect class="arch-paper" width="1440" height="730" />
    <text x="52" y="49" class="arch-title">STATE</text>
    <text x="178" y="48" class="arch-subtitle">细胞集合扰动预测 · 当前 ST-HVG 分支</text>
    <text x="1388" y="48" text-anchor="end" class="arch-small">01 / EXPRESSION</text>
    <path class="arch-rule" d="M52 70H1388" />
    <text x="64" y="104" class="arch-stage">A　输入与条件编码</text>
    <text x="540" y="104" class="arch-stage">B　集合内信息交互</text>
    <text x="970" y="104" class="arch-stage">C　表达解码与分析</text>
    <!-- Matrix entries show dimensions only, not measured or predicted values. -->
    <g v-for="column in [0, 1]" :key="column" :transform="`translate(${column ? 1190 : 64}, 180)`">
      <text x="69" y="-19" class="arch-label arch-center">{{ column ? '扰动预测表达' : '对照表达集合' }}</text>
      <rect class="arch-matrix-frame" width="138" height="126" />
      <g v-for="row in 6" :key="row"><rect v-for="gene in 8" :key="gene" class="arch-matrix-cell" :x="8 + (gene - 1) * 16" :y="8 + (row - 1) * 19" width="11" height="14" :opacity=".15 + ((row * 3 + gene * 5 + column * 2) % 8) * .1" /></g>
      <text x="69" y="153" class="arch-small arch-center">{{ column ? 'N × 2,000 基因' : 'N 个采样细胞' }}</text>
    </g>
    <path class="arch-flow" d="M202 242H250" :marker-end="arrow" />
    <rect x="250" y="210" width="150" height="64" rx="3" class="arch-box" />
    <text x="325" y="238" class="arch-label arch-center">表达编码器</text>
    <text x="325" y="260" class="arch-small arch-center">h_ctrl = E(X_ctrl)</text>
    <path class="arch-flow" d="M400 242H442" :marker-end="arrow" />
    <circle cx="460" cy="242" r="18" class="arch-box" />
    <text x="460" y="249" class="arch-center arch-math">+</text>
    <text x="64" y="394" class="arch-label">单基因扰动 p</text>
    <text x="64" y="420" class="arch-small">one-hot 条件</text>
    <path class="arch-flow" d="M202 410H250" :marker-end="arrow" />
    <rect x="250" y="378" width="150" height="64" rx="3" class="arch-box" />
    <text x="325" y="405" class="arch-label arch-center">扰动编码器</text>
    <text x="325" y="428" class="arch-small arch-center">E_pert(p)</text>
    <path class="arch-flow" d="M400 410H460V260" :marker-end="arrow" />
    <text x="64" y="504" class="arch-label">批次信息 b</text>
    <text x="64" y="530" class="arch-small">匹配细胞背景</text>
    <path class="arch-flow" d="M202 520H250" :marker-end="arrow" />
    <rect x="250" y="488" width="150" height="64" rx="3" class="arch-box" />
    <text x="325" y="515" class="arch-label arch-center">批次编码器</text>
    <text x="325" y="538" class="arch-small arch-center">E_batch(b)</text>
    <path class="arch-flow" d="M400 520H460V410" />
    <circle cx="460" cy="410" r="3" class="arch-junction" />
    <text x="500" y="298" class="arch-tiny arch-center">条件相加</text>
    <!-- Outer residual branches before adding perturbation and batch conditions. -->
    <circle cx="420" cy="242" r="3" class="arch-junction" />
    <path class="arch-flow" d="M420 242V135H904V224" :marker-end="arrow" />
    <text x="664" y="125" class="arch-small arch-center">表达编码的残差支路 h_ctrl</text>
    <rect x="540" y="174" width="300" height="282" rx="4" class="arch-accent" />
    <path class="arch-flow" d="M478 242H568" :marker-end="arrow" />
    <text x="690" y="198" class="arch-small arch-center">Cell-set Transformer</text>
    <rect x="568" y="216" width="244" height="58" rx="2" class="arch-box" />
    <text x="690" y="240" class="arch-label arch-center">双向多头自注意力</text>
    <text x="690" y="262" class="arch-small arch-center">跨细胞 token 交互</text>
    <path class="arch-flow" d="M690 274V304" :marker-end="arrow" />
    <rect x="568" y="304" width="244" height="52" rx="2" class="arch-box" />
    <text x="690" y="337" class="arch-label arch-center">前馈网络</text>
    <path class="arch-flow" d="M812 330H826V242H886" :marker-end="arrow" />
    <text x="690" y="382" class="arch-tiny arch-center">层内含归一化与残差</text>
    <path class="arch-rule" d="M568 411H812" />
    <text x="690" y="438" class="arch-small arch-center">× 8 层 · 一个 token 对应一个细胞</text>
    <circle cx="904" cy="242" r="18" class="arch-box" />
    <text x="904" y="249" class="arch-center arch-math">+</text>
    <text x="904" y="294" class="arch-small arch-center">残差融合</text>
    <path class="arch-flow" d="M922 242H970" :marker-end="arrow" />
    <rect x="970" y="210" width="160" height="64" rx="3" class="arch-box" />
    <text x="1050" y="238" class="arch-label arch-center">表达解码器</text>
    <text x="1050" y="260" class="arch-small arch-center">非负输出</text>
    <path class="arch-flow" d="M1130 242H1190" :marker-end="arrow" />
    <path class="arch-flow" d="M1328 242H1365V354H1018V380" :marker-end="arrow" />
    <path class="arch-flow" d="M1170 354V380" :marker-end="arrow" />
    <path class="arch-flow" d="M1322 354V380" :marker-end="arrow" />
    <rect x="952" y="380" width="132" height="58" rx="2" class="arch-soft" />
    <rect x="1104" y="380" width="132" height="58" rx="2" class="arch-soft" />
    <rect x="1256" y="380" width="132" height="58" rx="2" class="arch-soft" />
    <text x="1018" y="415" class="arch-center">基因响应</text>
    <text x="1170" y="415" class="arch-center">状态分布</text>
    <text x="1322" y="415" class="arch-center">代谢评分</text>
    <text x="1170" y="470" class="arch-small arch-center">PCA／UMAP 比较表达状态分布</text>
    <text x="1170" y="494" class="arch-small arch-center">不表示细胞形态或真实空间位置</text>
    <path class="arch-rule" d="M64 600H1388" />
    <text x="64" y="635" class="arch-stage">训练机制</text>
    <text x="64" y="663">预测扰动群体与实测扰动群体进行分布匹配</text>
    <text x="64" y="690" class="arch-small">不要求逐细胞前后配对；当前权重配置使用 energy 分布损失。</text>
    <text x="790" y="635" class="arch-stage">当前接入</text>
    <text x="790" y="663">在 2,000 基因表达空间运行 ST-HVG</text>
    <text x="790" y="690" class="arch-small">SE 为独立表示模块，不串接在当前默认推理链路中。</text>
  </svg>
</template>
