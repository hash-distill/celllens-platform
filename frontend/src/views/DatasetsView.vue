<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { userDataApi } from '../api/userData'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'
import type { DataCapabilities, DatasetMetadata, UserDataset, UserAnalysis } from '../types/userData'
const route = useRoute(), router = useRouter(), auth = useAuthStore(), ui = useUiStore()
const capabilities = ref<DataCapabilities | null>(null), datasets = ref<UserDataset[]>([]), total = ref(0)
const analyses = ref<UserAnalysis[]>([]), analysisTotal = ref(0), analysisPage = ref(0), page = ref(0)
const selected = ref<UserDataset | null>(null), busy = ref(false), loading = ref(false), error = ref('')
const file = ref<File | null>(null), fileInput = ref<HTMLInputElement | null>(null)
const name = ref(''), scale = ref<DatasetMetadata['expression_scale']>('raw_counts')
const layer = ref('X'), scope = ref<DatasetMetadata['matrix_scope']>('selected_panel')
const totals = ref(''), context = ref(''), description = ref('')
const kind = ref<'explore' | 'metabolism'>('explore'), group = ref(''), reference = ref(''), seed = ref(42)
const newUser = ref(''), newPassword = ref(''), creatingUser = ref(false)
const groupChoices = computed(() => selected.value?.summary.group_columns[group.value] ?? [])
const canAnalyze = computed(() => !!selected.value && !selected.value.archived && capabilities.value?.worker_enabled && capabilities.value.expression_ready && (kind.value !== 'metabolism' || capabilities.value.metabolism_ready))
const bytes = (value: number) => `${(value / 1024 / 1024).toFixed(1)} MB`
const statusLabel: Record<UserAnalysis['status'], string> = {queued: '排队中', running: '分析中', completed: '已完成', failed: '失败'}
async function handleError(reason: unknown) {
  error.value = reason instanceof Error ? reason.message : '操作失败'
  if (reason instanceof ApiError && reason.status === 401) {
    await auth.refresh(); await router.push({path: '/login', query: {next: route.fullPath}})
  }
}
async function load() {
  loading.value = true; error.value = ''
  try {
    const [data, jobs, service] = await Promise.all([userDataApi.datasets(page.value * 20), userDataApi.analyses(analysisPage.value * 20), userDataApi.capabilities()])
    datasets.value = data.items; total.value = data.total; analyses.value = jobs.items; analysisTotal.value = jobs.total; capabilities.value = service
    if (typeof route.query.dataset === 'string') selected.value = await userDataApi.dataset(route.query.dataset)
  } catch (reason) {await handleError(reason)}
  finally {loading.value = false}
}
async function selectDataset(id: string) {await router.replace({path: '/datasets', query: {dataset: id}})}
watch(() => route.query.dataset, async id => {
  group.value = ''; reference.value = ''; error.value = ''
  if (typeof id !== 'string') {selected.value = null; return}
  try {selected.value = await userDataApi.dataset(id)} catch (reason) {selected.value = null; await handleError(reason)}
})
watch(group, () => {reference.value = ''})
function chooseFile(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  if (file.value && !name.value) name.value = file.value.name.replace(/\.h5ad$/i, '')
}
async function upload() {
  if (!file.value) return
  if (capabilities.value && file.value.size > capabilities.value.max_upload_bytes) {error.value = '文件超过上传大小上限'; return}
  busy.value = true; error.value = ''
  try {
    const dataset = await userDataApi.upload(file.value, {name: name.value.trim(), expression_scale: scale.value, input_layer: layer.value.trim() || 'X', matrix_scope: scope.value, total_counts_key: totals.value.trim() || null, organism: 'human', cell_context: context.value.trim(), description: description.value.trim()})
    file.value = null; name.value = ''; description.value = ''; if (fileInput.value) fileInput.value.value = ''
    page.value = 0; await selectDataset(dataset.id); await load(); ui.push('success', '数据已校验并保存，可以创建分析任务')
  } catch (reason) {await handleError(reason)} finally {busy.value = false}
}
async function archive() {
  if (!selected.value) return
  busy.value = true; error.value = ''
  try {selected.value = await userDataApi.archive(selected.value.id); await load()}
  catch (reason) {await handleError(reason)} finally {busy.value = false}
}
async function analyze() {
  if (!selected.value) return
  busy.value = true; error.value = ''
  try {
    const job = await userDataApi.createAnalysis({dataset_id: selected.value.id, kind: kind.value, group_key: group.value || null, reference_group: reference.value || null, seed: seed.value})
    await router.push(`/analyses/${job.id}`)
  } catch (reason) {await handleError(reason)} finally {busy.value = false}
}
async function addUser() {
  creatingUser.value = true; error.value = ''
  try {await userDataApi.createUser({username: newUser.value.trim(), password: newPassword.value, role: 'user'}); newUser.value = ''; newPassword.value = ''; ui.push('success', '科研用户账号已创建')}
  catch (reason) {await handleError(reason)} finally {creatingUser.value = false}
}
onMounted(load)
</script>
<template>
  <div class="page data-page">
    <header class="page-heading"><div><span class="eyebrow">RESEARCH DATA / {{ auth.user?.username }}</span><h1>我的数据</h1><p>从自己的表达数据出发，探索细胞结构、分组响应与代谢功能。</p></div><button class="btn" :disabled="loading || busy" @click="load">刷新数据与任务</button></header>
    <div v-if="error" class="notice notice-danger" role="alert">{{ error }}</div>
    <div v-if="capabilities && !capabilities.worker_enabled" class="notice notice-warn" role="status">CPU 分析服务未启用。数据仍可上传和管理，请联系管理员启用分析服务。</div>
    <div class="data-layout">
      <section class="card upload-panel"><span class="eyebrow">01 / IMPORT</span><h2>上传表达数据</h2><p class="muted">支持人类单细胞 H5AD。基因符号使用 var_names 或 var.gene_symbol；分组信息放在 obs。</p>
        <form @submit.prevent="upload">
          <label class="file-drop" for="dataset-file"><strong>{{ file ? file.name : '选择 .h5ad 文件' }}</strong><span>{{ file ? bytes(file.size) : `单文件上限 ${bytes(capabilities?.max_upload_bytes ?? 268435456)}` }}</span><input id="dataset-file" ref="fileInput" type="file" accept=".h5ad" required :disabled="busy" @change="chooseFile" /></label>
          <label class="label" for="dataset-name">数据集名称</label><input id="dataset-name" v-model="name" class="input" maxlength="128" required :disabled="busy" />
          <div class="field-pair"><div><label class="label" for="dataset-scale">表达单位</label><select id="dataset-scale" v-model="scale" class="select" :disabled="busy"><option value="raw_counts">原始计数（raw counts）</option><option value="cp10k">每万计数（CP10K）</option><option value="log1p_cp10k">log1p(CP10K)</option></select></div><div><label class="label" for="dataset-layer">表达矩阵位置</label><input id="dataset-layer" v-model="layer" class="input" maxlength="128" placeholder="X 或 layers 中的名称" :disabled="busy" /></div></div>
          <template v-if="scale === 'raw_counts'"><label class="label" for="dataset-scope">矩阵包含的基因范围</label><select id="dataset-scope" v-model="scope" class="select" :disabled="busy"><option value="selected_panel">筛选后的基因面板</option><option value="full_library">完整文库基因矩阵</option></select><label class="label" for="dataset-totals">完整文库总计数列（obs）{{ scope === 'selected_panel' ? ' · 必填' : ' · 可选' }}</label><input id="dataset-totals" v-model="totals" class="input" :required="scope === 'selected_panel'" maxlength="128" placeholder="例如 total_counts" :disabled="busy" /><p class="muted">仅完整文库矩阵可直接计算总计数。筛选后的面板需提供筛选前的文库总计数。</p></template>
          <template v-else><p class="muted">请确认这些数值已按完整文库归一化；系统不会再按所选基因重新归一化。</p></template>
          <label class="label" for="dataset-context">细胞背景 / 来源</label><input id="dataset-context" v-model="context" class="input" maxlength="128" placeholder="例如 PBMC、K562 或实验来源" :disabled="busy" />
          <label class="label" for="dataset-description">实验说明</label><textarea id="dataset-description" v-model="description" class="input" rows="3" maxlength="2000" placeholder="条件、样本来源、预处理步骤" :disabled="busy"></textarea>
          <p v-if="capabilities" class="muted">最多 {{ capabilities.max_cells.toLocaleString() }} 个细胞、{{ capabilities.max_genes.toLocaleString() }} 个基因；稀疏非零值或单个数组最多 {{ capabilities.max_matrix_values.toLocaleString() }} 个。个人源数据配额 {{ bytes(capabilities.max_user_storage_bytes) }}。</p>
          <button class="btn btn-primary upload-button" type="submit" :disabled="busy || !file || !capabilities?.expression_ready">{{ busy ? '正在处理，请稍候…' : '上传并校验' }}</button>
          <p v-if="capabilities && !capabilities.expression_ready" class="notice notice-warn">服务端科学分析依赖尚未安装。</p>
        </form>
      </section>
      <div class="data-main">
        <section class="card"><div class="section-title"><div><span class="eyebrow">02 / DATASETS</span><h2>数据集 <small>{{ total }}</small></h2></div><span class="privacy-mark">所属账号可见</span></div>
          <p v-if="loading" class="muted" role="status">正在读取…</p><p v-else-if="!datasets.length" class="empty-copy">还没有数据集。上传后会保存源文件、校验信息和独立版本。</p>
          <div v-else class="dataset-list"><button v-for="item in datasets" :key="item.id" class="dataset-row" :class="{chosen: selected?.id === item.id}" @click="selectDataset(item.id)"><span><strong>{{ item.name }}</strong><small>{{ item.metadata.cell_context || '未填写背景' }} · {{ item.summary.n_cells.toLocaleString() }} 细胞 × {{ item.summary.n_genes.toLocaleString() }} 基因</small></span><span>{{ item.archived ? '已归档' : '可分析' }}<small>{{ bytes(item.size_bytes) }}</small></span></button></div>
          <div v-if="total > 20" class="pagination"><button class="btn btn-sm" :disabled="!page || loading" @click="page--; load()">上一页</button><span>第 {{ page + 1 }} 页</span><button class="btn btn-sm" :disabled="(page + 1) * 20 >= total || loading" @click="page++; load()">下一页</button></div>
        </section>
        <section v-if="selected" class="card selected-panel"><span class="eyebrow">03 / ANALYSIS SETUP</span><div class="section-title"><h2>{{ selected.name }}</h2><span class="privacy-mark">{{ selected.archived ? '已归档' : '校验通过' }}</span></div><p class="muted">{{ selected.metadata.description || '未填写实验说明' }}</p><dl class="data-facts"><div><dt>源矩阵 / 单位</dt><dd>{{ selected.metadata.input_layer }} / {{ selected.metadata.expression_scale }}</dd></div><div><dt>源文件版本</dt><dd class="mono">{{ selected.id }}</dd></div><div><dt>SHA-256</dt><dd class="mono hash">{{ selected.sha256 }}</dd></div></dl>
          <div class="btn-row"><a class="btn btn-sm" :href="userDataApi.sourceUrl(selected.id)">下载源文件</a><button class="btn btn-sm" :disabled="busy || selected.archived" @click="archive">归档数据集</button></div><p class="muted">归档后停止创建新任务，已有数据和结果继续保留。</p>
          <details class="compatibility"><summary>STATE 模型兼容性检查</summary><p>{{ selected.summary.state_compatibility.message }}</p><p v-if="selected.summary.state_compatibility.required_genes">登记面板匹配 {{ selected.summary.state_compatibility.matched_genes }} / {{ selected.summary.state_compatibility.required_genes }} 个基因。</p><p v-if="selected.summary.state_compatibility.missing_columns.length">缺少模型元数据列：{{ selected.summary.state_compatibility.missing_columns.join('、') }}</p><p v-if="selected.summary.state_compatibility.missing_genes.length">缺失基因：{{ selected.summary.state_compatibility.missing_genes.slice(0, 30).join('、') }}{{ selected.summary.state_compatibility.missing_genes.length > 30 ? '…' : '' }}</p></details>
          <form class="analysis-form" @submit.prevent="analyze"><label class="label" for="analysis-kind">分析任务</label><select id="analysis-kind" v-model="kind" class="select"><option value="explore">表达探索 · 质控 / PCA / 基因分组比较</option><option value="metabolism" :disabled="!capabilities?.metabolism_ready">代谢分析 · 表达探索 + scCellFie</option></select><div class="field-pair"><div><label class="label" for="analysis-group">分组列（obs）</label><select id="analysis-group" v-model="group" class="select"><option value="">不分组</option><option v-for="(_, column) in selected.summary.group_columns" :key="column" :value="column">{{ column }}</option></select></div><div><label class="label" for="analysis-reference">参考组</label><select id="analysis-reference" v-model="reference" class="select" :disabled="!group"><option value="">仅展示各组均值</option><option v-for="choice in groupChoices" :key="choice" :value="choice">{{ choice }}</option></select></div></div><label class="label" for="analysis-seed">PCA 随机种子</label><input id="analysis-seed" v-model.number="seed" class="input" type="number" min="0" max="4294967295" required /><p class="muted">使用全部上传基因进行统计和代谢分析。PCA 最多展示 2,000 个细胞；组间差值是描述性结果。</p><button class="btn btn-primary" type="submit" :disabled="busy || !canAnalyze">创建分析任务</button><p v-if="!capabilities?.metabolism_ready" class="muted">scCellFie 依赖或冻结数据库未就绪，代谢分析暂不可用。</p></form>
        </section>
        <section class="card"><div class="section-title"><div><span class="eyebrow">ANALYSIS RECORDS</span><h2>分析任务 <small>{{ analysisTotal }}</small></h2></div></div><p v-if="!analyses.length" class="empty-copy">选择数据集，创建第一个分析任务。</p><div v-else class="analysis-list"><RouterLink v-for="job in analyses" :key="job.id" :to="`/analyses/${job.id}`"><span><strong>{{ job.kind === 'metabolism' ? '代谢分析' : '表达探索' }}</strong><small>{{ job.id }}</small></span><span :class="{failed: job.status === 'failed'}">{{ statusLabel[job.status] }} →</span></RouterLink></div><div v-if="analysisTotal > 20" class="pagination"><button class="btn btn-sm" :disabled="!analysisPage || loading" @click="analysisPage--; load()">上一页</button><span>第 {{ analysisPage + 1 }} 页</span><button class="btn btn-sm" :disabled="(analysisPage + 1) * 20 >= analysisTotal || loading" @click="analysisPage++; load()">下一页</button></div></section>
        <section v-if="auth.user?.role === 'admin'" class="card"><details><summary>创建科研用户账号</summary><form class="account-form" @submit.prevent="addUser"><div><label class="label" for="new-user">用户名</label><input id="new-user" v-model="newUser" class="input" required pattern="[a-zA-Z0-9_.-]+" maxlength="64" autocomplete="off" /></div><div><label class="label" for="new-password">初始密码（至少 12 位）</label><input id="new-password" v-model="newPassword" class="input" type="password" minlength="12" maxlength="256" required autocomplete="new-password" /></div><button class="btn" :disabled="creatingUser" type="submit">创建用户</button></form><p class="muted">新账号为普通用户，可管理自己的数据与任务。</p></details></section>
      </div>
    </div>
  </div>
</template>
<style scoped>
.data-layout{display:grid;grid-template-columns:minmax(300px,390px) minmax(0,1fr);gap:24px;align-items:start}.upload-panel{padding:26px}.data-page h2{font-size:20px;font-weight:500;margin:8px 0 12px}.muted{font-size:12px;color:var(--muted);line-height:1.9}.file-drop{border:1px dashed var(--border-strong);padding:24px 18px;background:#f3f6f1;display:grid;gap:7px;margin:24px 0;color:var(--primary)}.file-drop strong{font-size:14px;overflow-wrap:anywhere}.file-drop span{font-size:11px;color:var(--muted)}.file-drop input{width:100%;font-size:11px;margin-top:8px}.upload-panel .input,.upload-panel .select{margin-bottom:15px}.field-pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}.upload-button{width:100%;margin-top:10px}.section-title{display:flex;justify-content:space-between;align-items:center;gap:14px}.section-title h2 small{font-size:13px;color:var(--muted);margin-left:6px}.privacy-mark{font-size:10px;color:var(--primary);background:var(--primary-weak);padding:4px 8px;white-space:nowrap}.dataset-row{width:100%;display:flex;gap:15px;justify-content:space-between;border:0;border-top:1px solid var(--border);background:transparent;text-align:left;font:inherit;padding:17px 12px;cursor:pointer;color:var(--ink)}.dataset-row.chosen{background:var(--primary-weak);box-shadow:inset 3px 0 var(--primary)}.dataset-row strong{font-weight:500;font-size:14px}.dataset-row small,.analysis-list small{display:block;font-size:10px;margin-top:5px;color:var(--muted);overflow-wrap:anywhere}.dataset-row>span:last-child{text-align:right;white-space:nowrap;font-size:11px}.data-facts{display:grid;gap:10px;font-size:11px;margin:22px 0}.data-facts>div{display:grid;grid-template-columns:110px minmax(0,1fr);gap:10px}.data-facts dt{color:var(--muted)}.data-facts dd{margin:0;overflow-wrap:anywhere}.data-facts .hash{font-size:10px}.compatibility{border-top:1px solid var(--border);padding:16px 0;margin-top:18px;font-size:12px}.compatibility p{color:var(--muted);overflow-wrap:anywhere}.analysis-form{border-top:1px solid var(--border);padding-top:20px}.analysis-form .input,.analysis-form .select{margin-bottom:16px}.analysis-form input[type=number]{max-width:160px}.analysis-list>a{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--border);padding:16px 0;font-size:12px;color:var(--ink)}.analysis-list strong{font-weight:500}.analysis-list .failed{color:var(--danger)}.empty-copy{padding:22px 0;color:var(--muted);font-size:12px}.pagination{display:flex;align-items:center;justify-content:flex-end;gap:14px;margin-top:16px;font-size:11px}.account-form{display:grid;grid-template-columns:1fr 1fr auto;gap:14px;align-items:end;margin-top:20px}.data-page>.notice{margin-bottom:20px}details summary{cursor:pointer;color:var(--primary)}@media(max-width:900px){.data-layout{grid-template-columns:1fr}.upload-panel form{max-width:650px}.upload-panel{padding:22px}}@media(max-width:550px){.field-pair,.account-form{grid-template-columns:1fr}.data-facts>div{grid-template-columns:1fr;gap:4px}.section-title{align-items:start}.dataset-row{padding:16px 6px}.data-page h2{font-size:18px}}
</style>
