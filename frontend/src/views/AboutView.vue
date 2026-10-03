<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useServiceStore } from '../stores/service'
import { API_ROOT } from '../api/http'
import { isMockEnabled, isMockOverrideOn, mockEnvEnabled, setMockOverride } from '../api/mockFlag'

/** Mock 演示模式显式开关（默认关闭；切换后刷新页面生效） */
const mockActive = isMockEnabled()
const mockChecked = ref(isMockOverrideOn() || mockEnvEnabled)

function toggleMock(event: Event): void {
  const on = (event.target as HTMLInputElement).checked
  setMockOverride(on)
  window.location.reload()
}

/** 使用说明 / 服务状态 / 术语与适用范围 */

const service = useServiceStore()

onMounted(() => {
  if (!service.lastCheckedAt) void service.refresh()
})

function checkLabel(value: boolean | undefined): string {
  if (value === undefined) return '未知'
  return value ? '正常' : '异常'
}
</script>

<template>
  <div class="page about-page">
    <div class="card">
      <h1 class="page-title">使用说明</h1>
      <ol class="guide-list">
        <li>
          <strong>新建实验：</strong>工作台左侧选择细胞背景、扰动基因（从接口列表选择，不支持任意文本）
          与运行模式；可用性每次从接口读取，不写死。
        </li>
        <li>
          <strong>提交与轮询：</strong>HTTP 202 仅表示已接收；页面每 2 秒串行轮询真实阶段，
          网络异常自动退避重试且不改写任务状态；刷新后按 URL 恢复。
        </li>
        <li>
          <strong>阅读结果：</strong>细胞状态（二维随机投影）、基因响应（平均归一化表达差，不是 log2FC）、
          代谢功能（scCellFie 任务分数变化，不是实测通量）与预测验证。
        </li>
        <li>
          <strong>核对证据：</strong>右侧证据栏常驻参数、注册模型、覆盖率、警告与错误码；
          覆盖率偏低时按证据等级解读代谢结论。
        </li>
        <li>
          <strong>反馈问题：</strong>使用「复制诊断信息」，附带 run_id、参数、接口与错误码，
          避免只反馈「页面没有结果」。
        </li>
      </ol>
    </div>

    <div class="card">
      <div class="flex-between">
        <h2 class="card-title" style="margin-bottom: 0">服务状态</h2>
        <button class="btn btn-sm" type="button" :disabled="service.checking" @click="service.refresh()">
          {{ service.checking ? '检查中…' : '重新检查' }}
        </button>
      </div>
      <dl class="evidence-list" style="margin-top: 12px">
        <dt>API 基址</dt>
        <dd class="mono">{{ API_ROOT }}</dd>
        <dt>总体状态</dt>
        <dd>{{ service.levelLabel }}</dd>
        <dt>服务存活</dt>
        <dd>
          <template v-if="service.health">
            {{ service.health.service }} / status={{ service.health.status }} / database={{ service.health.database }}
            <span v-if="service.healthFieldsOk === false" class="pill pill-warn">字段异常</span>
          </template>
          <template v-else>未获取</template>
        </dd>
        <dt>就绪检查</dt>
        <dd>
          <template v-if="service.checks">
            数据库 {{ checkLabel(service.checks.database) }} · Worker
            {{ checkLabel(service.checks.worker) }} · GPU {{ checkLabel(service.checks.gpu) }}
            <span class="muted small">（HTTP {{ service.readyHttpStatus }}；服务存活不等于在线可运行）</span>
          </template>
          <template v-else>未获取</template>
        </dd>
        <dt>检查时间</dt>
        <dd>{{ service.lastCheckedAt ? new Date(service.lastCheckedAt).toLocaleString() : '—' }}</dd>
      </dl>
    </div>

    <div class="card">
      <h2 class="card-title">Mock 演示模式</h2>
      <p class="muted small" style="margin: 0 0 10px">
        用于后端不在线时演示界面与调试样式。开启后所有接口返回固定种子的合成样例数据
        ，页面顶部会出现常驻「Mock 样例数据」标记。
        真实请求失败不会自动切换到本模式，两种启用方式都是显式操作，默认关闭。
      </p>
      <label class="mock-toggle">
        <input
          type="checkbox"
          :checked="mockChecked"
          :disabled="mockEnvEnabled"
          @change="toggleMock"
        />
        <span>启用 Mock 演示模式（本浏览器，切换后页面自动刷新）</span>
      </label>
      <p v-if="mockEnvEnabled" class="field-hint">
        已通过环境变量 VITE_ENABLE_MOCK=true 启用，界面开关被锁定。
      </p>
      <p v-else class="field-hint">
        也可以在启动时通过环境变量 VITE_ENABLE_MOCK=true 启用（见 .env.example）。
      </p>
      <p v-if="mockActive" class="notice notice-warn" style="margin-top: 10px">
        当前 Mock 模式已启用：全部为合成样例，不能作为真实结果。运行记录在本浏览器保存，与真实 API 记录隔离。
      </p>
    </div>

    <div class="card">
      <h2 class="card-title">术语与解释</h2>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th scope="col">术语</th><th scope="col">含义</th></tr>
          </thead>
          <tbody>
            <tr><td>二维随机投影</td><td> seeded-random-projection 的共享二维坐标；不是 UMAP / t-SNE，也不是真实细胞空间</td></tr>
            <tr><td>预测变化</td><td>预测减对照的平均归一化表达差；不标 log2FC</td></tr>
            <tr><td>代谢任务分数变化</td><td>scCellFie 任务分数变化；不是实测代谢通量</td></tr>
            <tr><td>覆盖支持</td><td>覆盖规则支持的任务；不等于预测被实验证实</td></tr>
            <tr><td>探索性</td><td>有限制的候选解释</td></tr>
            <tr><td>证据不足</td><td>不能作为可靠代谢结论；也不代表没有生物效应</td></tr>
            <tr><td>合成演示数据</td><td>预计算演示包（当前确认为 K562/MYC synthetic_demo_bundle）；不能标为真实预测</td></tr>
            <tr><td>分析完成</td><td>仅表示计算流程完成，不自动转换为生物学验证通过</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h2 class="card-title">适用范围与待后端协作项</h2>
      <p class="muted small" style="margin: 0 0 10px">
        以下说明当前数据可用范围；缺少产物时局部提示，不补造结果：
      </p>
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr><th scope="col">编号</th><th scope="col">缺口</th><th scope="col">当前降级</th></tr>
          </thead>
          <tbody>
            <tr><td>B1</td><td>运行溯源（来源类型 / 模型与数据版本 / 哈希）</td><td>读取历史 manifest；证据栏可查看历史模型、数据与哈希</td></tr>
            <tr><td>B2</td><td>预计算组合目录（合成或真实、产物种类）</td><td>目录只列通过哈希核验的组合；缺失产物局部提示</td></tr>
            <tr><td>B3</td><td>验证扰动目录与开发名单</td><td>验证提交入口未开放，页面保留</td></tr>
            <tr><td>B4</td><td>全量验证指标接口</td><td>读取已有后端指标；缺失时提示，实验协议仍待确认</td></tr>
            <tr><td>B5</td><td>全量代谢任务与分页计数</td><td>读取完整有效任务并分页，旧产物明确退回 Top 摘要</td></tr>
            <tr><td>B6</td><td>基因—反应—任务映射</td><td>展示已有任务与反应，关系图延期</td></tr>
            <tr><td>B7</td><td>完整证据报告与真实预计算结果</td><td>仅提供现有 HTML 报告与合成演示标记</td></tr>
          </tbody>
        </table>
      </div>
      <p class="muted small" style="margin: 10px 0 0">
        账号系统、任意数据上传、药物剂量、双基因扰动、在线训练、实时迁移轨迹与多租户不属于本轮范围。

      </p>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  max-width: 960px;
}
.page-title {
  font-size: 21px;
  margin-bottom: 10px;
}
.mock-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
}
.guide-list {
  margin: 0;
  padding-left: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
