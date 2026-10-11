<script setup lang="ts">
import { onMounted } from 'vue'
import { useServiceStore } from '../stores/service'

const service = useServiceStore()
onMounted(() => {
  if (!service.lastCheckedAt) void service.refresh()
})
function checkLabel(value: boolean | undefined): string {
  if (value === undefined) return '未获取'
  return value ? '正常' : '不可用'
}
</script>

<template>
  <div class="page about-page">
    <div class="card">
      <h1 class="page-title">使用说明</h1>
      <p class="muted">细胞知镜面向单基因扰动研究，将表达预测、代谢任务分析和运行来源整合在同一实验中。</p>
      <ol class="guide-list">
        <li><strong>设置实验：</strong>选择 K562、RPE1、Jurkat 或 HepG2，再从当前背景的在线支持列表选择一个扰动基因。可设置 64–4,096 个预测细胞及随机种子。</li>
        <li><strong>上传分析：</strong>无需登录，可在“上传分析”页面上传 H5AD 表达数据，校验后进行表达质量分析、PCA、分组比较和代谢任务分析。上传数据与分析记录在当前部署中共享。</li>
        <li><strong>运行实验：</strong>点击“开始实验”，查看运行阶段与进度。页面刷新后可继续查看同一实验，完成的实验保存在“实验记录”。相同参数可复用已有计算结果。</li>
        <li><strong>分析结果：</strong>单细胞状态提供共同对照 PCA、基因与任务着色和累积分布；基因响应展示群体平均表达差；代谢功能展示任务、反应、相关基因与 GPR 规则。</li>
        <li><strong>核对来源：</strong>查看模型与数据版本、表达尺度、数据完整性和匹配观测。将实验加入比较，或导出科研图、数据及分析报告；“结果解读”按四个章节讲解所选实验。</li>
        <li><strong>辅助解读：</strong>在右上角“设置”填写 OpenAI 兼容服务地址、模型和 API Key。打开已完成实验或上传分析，预览摘要后手动生成解读。生成文本供科研参考，需核对原始结果；密钥仅保存在当前标签页，可随时清除。</li>
        <li><strong>页面工具：</strong>右侧快捷栏可切换亮暗、直达顶部或底部；设置中可选择跟随系统外观。</li>
        <li><strong>处理运行问题：</strong>读取页面提示，必要时重新连接或重试对应结果。“复制诊断信息”可保存运行编号、参数与错误信息，便于排查。</li>
      </ol>
    </div>

    <div class="card">
      <div class="flex-between">
        <h2 class="card-title" style="margin-bottom: 0">服务状态</h2>
        <button class="btn btn-sm" type="button" :disabled="service.checking" @click="service.refresh()">{{ service.checking ? '检查中…' : '重新检查' }}</button>
      </div>
      <dl class="evidence-list" style="margin-top: 12px">
        <dt>总体状态</dt><dd>{{ service.levelLabel }}</dd>
        <dt>服务连接</dt><dd>{{ service.health ? (service.healthFieldsOk === false ? '状态响应异常' : '已连接') : '未获取' }}</dd>
        <dt>计算资源</dt><dd v-if="service.checks">数据库 {{ checkLabel(service.checks.database) }} · 分析服务 {{ checkLabel(service.checks.worker) }} · GPU {{ checkLabel(service.checks.gpu) }}</dd><dd v-else>未获取</dd>
        <dt>检查时间</dt><dd>{{ service.lastCheckedAt ? new Date(service.lastCheckedAt).toLocaleString() : '—' }}</dd>
      </dl>
      <p class="muted small">在线计算需要可用的模型、输入数据、分析服务和 GPU。从实验记录打开已有结果不需要重新执行模型。上传分析由独立 CPU 工作进程执行。</p>
    </div>

    <div class="card">
      <h2 class="card-title">结果含义</h2>
      <div class="table-wrap"><table class="table">
        <thead><tr><th scope="col">结果</th><th scope="col">解读方法</th></tr></thead>
        <tbody>
          <tr><td>单细胞状态</td><td>PCA 基于本次对照拟合，对照、预测及可用观测共用坐标。每个点表示表达状态，坐标不表示物理位置或同一细胞的前后轨迹。</td></tr>
          <tr><td>表达变化</td><td>统一 log1p(CP10K) 尺度上的预测平均表达减对照平均表达。差值排序不等于差异表达显著性检验。</td></tr>
          <tr><td>代谢任务与反应分数</td><td>scCellFie 根据表达和冻结代谢数据库计算的功能支持分数；分数变化不直接表示实测通量、物质浓度或 ATP 产量。</td></tr>
          <tr><td>数据完整性</td><td>展示模型预测基因对代谢任务和反应的覆盖及缺失基因。完整性衡量输入信息范围，不能解释为预测准确率。</td></tr>
          <tr><td>功能关联图</td><td>读取本次保存的任务—反应—基因知识关联。布局用于比较，连线不表示模型已证明的因果贡献。</td></tr>
          <tr><td>分析完成</td><td>本次计算与结果保存已完成。预测结论仍需结合数据完整性、匹配观测和后续实验判断。</td></tr>
          <tr><td>大模型辅助解读</td><td>由外部模型根据已保存摘要生成的文字，可解释结果和建议验证工作；它不是原始分析证据或生物学验证，不改动计算结果。</td></tr>
        </tbody>
      </table></div>
    </div>

    <div class="card">
      <h2 class="card-title">适用范围</h2>
      <p>系统支持四种已登记细胞背景中的单基因扰动分析。在线目标以支持列表为准；已有结果从实验记录打开。当前 Replogle 数据主要为 CRISPRi 扰动，系统不提供敲除、过表达或剂量的独立设置。</p>
      <p class="muted small">实验比较最多保存四个候选，候选列表保存在当前浏览器。系统目前用于受控科研环境，支持上传符合格式要求的人类 H5AD 表达数据；尚不提供账号权限隔离、多基因联合扰动或在线训练。上传数据不会自动成为 STATE 在线推演的输入。</p>
    </div>
  </div>
</template>

<style scoped>
.about-page { max-width: 1360px; }
.page-title { font-size: 21px; margin-bottom: 10px; }
.guide-list { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 8px; }
</style>
