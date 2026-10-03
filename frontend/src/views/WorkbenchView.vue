<script setup lang="ts">
import ParamPanel from '../components/ParamPanel.vue'
import RecentRuns from '../components/RecentRuns.vue'
import CandidateTray from '../components/CandidateTray.vue'

/** 实验工作台：新建实验、最近运行、初始引导 */
</script>

<template>
  <div class="page">
    <p class="notice notice-info narrow-hint">当前屏幕较窄，建议在桌面宽度查看完整图表与证据栏。</p>
    <div class="layout-2col">
      <aside class="col-sticky">
        <ParamPanel />
      </aside>

      <section class="center-col">
        <div class="card intro">
          <h1 class="intro-title">细胞知镜 · 科研分析工作台</h1>
          <p class="intro-sub">
            单细胞扰动预测与代谢分析：选择细胞背景与扰动基因，提交实验后查看转录与代谢结果，
            并核对覆盖与证据等级。
          </p>
          <ol class="intro-steps">
            <li>在左侧选择细胞背景、扰动基因与运行模式（可用性每次从接口读取）。</li>
            <li>点击「开始实验」，HTTP 202 仅表示已接收，进入运行详情查看真实阶段进度。</li>
            <li>完成后阅读四个标签页：细胞状态、基因响应、代谢功能、预测验证。</li>
            <li>在右侧证据栏核对参数、覆盖率与警告，必要时复制诊断信息反馈。</li>
          </ol>
          <p class="muted small" style="margin: 10px 0 0">
            提示：预计算演示为合成演示数据，页面会常驻标记来源；「运行完成」只表示计算流程完成，
            不等于生物学验证通过。
          </p>
        </div>

        <div class="card">
          <RecentRuns />
        </div>
      </section>
    </div>
    <CandidateTray />
  </div>
</template>

<style scoped>
.intro-title {
  font-size: 22px;
}
.intro-sub {
  color: var(--muted);
  margin: 8px 0 12px;
  max-width: 720px;
}
.intro-steps {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--ink);
}
</style>
