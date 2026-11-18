<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../api/http'
import { uploadH5ad, type H5adUpload, type UploadCapabilities } from '../api/uploads'
import { accessSession } from '../stores/access'
import SubmissionReview from './SubmissionReview.vue'
interface ImportResult { import_id:string; manifest_sha256:string; cell_line:string; perturbation:string; gene_count:number; group_counts:Record<string,number>; selected_counts:Record<string,number>; normalization:{input_scale:string;output_scale:string;denominator:string}; limitations:string[] }
const emit = defineEmits<{'review-change':[open:boolean];'busy-change':[busy:boolean]}>()
const router = useRouter()
let life = new AbortController(), operation: AbortController | null = null, revision = 0, disposed = false
const caps = ref<UploadCapabilities | null>(null), error = ref(''), notice = ref('')
const uploading = ref(false), busy = ref(false), creating = ref(false), uncertain = ref(false), reviewing = ref(false)
const fileInput = ref<HTMLInputElement | null>(null), selectedFile = ref<File | null>(null), upload = ref<H5adUpload | null>(null), progress = ref(0), dragging = ref(false), result = ref<ImportResult | null>(null)
const form = reactive({expression_scale:'',full_library:false,total_counts_key:'',group_key:'',control_label:'',target_label:'',cell_line:'',perturbation:'',batch_key:'',max_cells:256,seed:42})
const readOnly = computed(() => Boolean(accessSession.value?.read_only))
const active = computed(() => uploading.value || busy.value || creating.value)
const locked = computed(() => active.value || readOnly.value || uncertain.value)
const groupColumn = computed(() => upload.value?.obs_columns.find(column => column.name === form.group_key))
const numericColumns = computed(() => upload.value?.obs_columns.filter(column => column.kind === 'numeric') ?? [])
const exactLabels = computed(() => Boolean(groupColumn.value && !groupColumn.value.truncated))
const validGroups = computed(() => {
  if (!groupColumn.value || !form.control_label || !form.target_label || form.control_label === form.target_label) return false
  return !exactLabels.value || [form.control_label, form.target_label].every(label => groupColumn.value!.values.some(value => value.label === label && value.count >= 2))
})
const ready = computed(() => Boolean(caps.value?.available && upload.value && !locked.value && form.expression_scale && validGroups.value &&
  /^[A-Za-z0-9_. -]{1,32}$/.test(form.cell_line) && /^[A-Za-z0-9_.-]{1,64}$/.test(form.perturbation) &&
  Number.isInteger(form.max_cells) && form.max_cells >= 2 && form.max_cells <= 4096 && Number.isInteger(form.seed) && form.seed >= 0 && form.seed <= 2147483647 &&
  (form.expression_scale !== 'raw_counts' || form.full_library || numericColumns.value.some(column => column.name === form.total_counts_key))))
const stage = computed(() => result.value ? 3 : upload.value ? 2 : 1)
const formatBytes = (bytes: number) => bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`
watch(active, value => emit('busy-change', value), {flush:'sync'})
function review(open: boolean) {
  if (open && (!result.value || locked.value)) return
  reviewing.value = open
  emit('review-change', open)
}
function invalidate() { result.value = null; review(false) }
watch(form, () => { if (busy.value) cancelOperation(); invalidate() }, {flush:'sync'})
watch(() => form.group_key, () => { form.control_label = ''; form.target_label = '' }, {flush:'sync'})
function cancelOperation() {
  revision++
  operation?.abort()
  operation = null
  uploading.value = busy.value = creating.value = false
}
async function capabilities() {
  if (disposed || readOnly.value) return
  const signal = life.signal
  try {
    const value = await apiFetch<UploadCapabilities>('/research/uploads/capabilities', {signal})
    if (!signal.aborted && !disposed && !readOnly.value) { caps.value = value; error.value = '' }
  } catch (e) { if (!signal.aborted && !disposed) error.value = e instanceof Error ? e.message : '上传能力读取失败' }
}
async function discardUpload(signal: AbortSignal) {
  const id = upload.value?.upload_id
  if (id) {
    try { await apiFetch(`/research/uploads/${encodeURIComponent(id)}`, {method:'DELETE', signal}) }
    catch (e) {
      // Expiry, or a previous successful DELETE whose response was lost, means
      // there is no pending file left to remove.
      if (!(e instanceof ApiError && e.status === 404)) throw e
    }
  }
}
function clearConfiguration() {
  Object.assign(form, {expression_scale:'',full_library:false,total_counts_key:'',group_key:'',control_label:'',target_label:'',cell_line:'',perturbation:'',batch_key:''})
  invalidate()
}
async function selectFile(file?: File) {
  if (!file || locked.value || disposed) return
  error.value = notice.value = ''
  if (!upload.value) selectedFile.value = file
  if (!/\.h5ad$/i.test(file.name)) { error.value = '请选择 .h5ad 文件；其他文件格式无法读取。'; return }
  if (!file.size) { error.value = '文件为空，请选择包含细胞表达数据的 H5AD 文件。'; return }
  if (!caps.value?.available) { error.value = '当前工作区尚未开放上传，请重新读取工作区状态。'; return }
  if (file.size > caps.value.max_bytes) { error.value = `文件超过 ${formatBytes(caps.value.max_bytes)} 上限，请选择较小的 H5AD 文件。`; return }
  cancelOperation()
  const version = revision, controller = new AbortController()
  operation = controller
  uploading.value = true
  try {
    if (upload.value) {
      notice.value = '正在更换文件…'
      await discardUpload(controller.signal)
    }
    if (version !== revision || controller.signal.aborted || disposed || readOnly.value) return
    upload.value = null
    clearConfiguration()
    selectedFile.value = file
    progress.value = 0
    notice.value = ''
    const metadata = await uploadH5ad(file, {signal:controller.signal,onProgress:value => { if (version === revision && !controller.signal.aborted) progress.value = value }})
    if (version !== revision || controller.signal.aborted || disposed || readOnly.value) return
    upload.value = metadata
    // Only suggest a background actually observed as a single value in the file.
    const background = metadata.obs_columns.find(column => column.name === 'cell_line')
    form.cell_line = metadata.suggested_cell_line ?? (background?.unique_count === 1 && !background.truncated && background.missing_count === 0 ? background.values[0]?.label ?? '' : '')
    notice.value = '字段已读取。请按原始数据说明确认分组与表达尺度。'
  } catch (e) {
    if (version === revision && !controller.signal.aborted && !disposed) {
      notice.value = ''
      const message = e instanceof Error ? e.message : '请重试。'
      error.value = upload.value ? `更换文件未完成：${message} 请再次选择文件重试。` : message
    }
  } finally { if (version === revision) { uploading.value = false; operation = null } }
}
function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  void selectFile(input.files?.[0])
  input.value = ''
}
function dropFile(event: DragEvent) {
  dragging.value = false
  if (locked.value) return
  if (event.dataTransfer?.files.length !== 1) { error.value = '每次请选择一个 H5AD 文件。'; return }
  void selectFile(event.dataTransfer.files[0])
}
function cancelUpload() { cancelOperation(); progress.value = 0; notice.value = '上传已取消。可以重试或重新选择文件。'; error.value = '' }
async function inspect() {
  if (!ready.value || !upload.value) return
  cancelOperation()
  const version = revision, controller = new AbortController(), uploadId = upload.value.upload_id
  operation = controller
  busy.value = true
  error.value = notice.value = ''
  invalidate()
  const body = {...form, total_counts_key:form.expression_scale === 'raw_counts' && !form.full_library ? form.total_counts_key : undefined, batch_key:form.batch_key || undefined}
  try {
    const value = await apiFetch<ImportResult>(`/research/uploads/${encodeURIComponent(uploadId)}/imports`, {method:'POST',body,timeoutMs:120000,signal:controller.signal})
    if (version === revision && !controller.signal.aborted && !disposed && !readOnly.value) result.value = value
  } catch (e) { if (version === revision && !controller.signal.aborted && !disposed) error.value = e instanceof Error ? e.message : '数据校验失败，请核对输入。' }
  finally { if (version === revision) { busy.value = false; operation = null } }
}
async function create() {
  if (!reviewing.value || !result.value || locked.value) return
  const importId = result.value.import_id
  review(false)
  cancelOperation()
  const version = revision, controller = new AbortController()
  operation = controller
  creating.value = true
  error.value = ''
  try {
    const record = await apiFetch<{id:string}>(`/research/imports/${encodeURIComponent(importId)}/analyses`, {method:'POST',signal:controller.signal})
    if (version === revision && !controller.signal.aborted && !disposed && !readOnly.value) await router.push(`/measured/${encodeURIComponent(record.id)}`)
  } catch (e) {
    if (version === revision && !controller.signal.aborted && !disposed) {
      error.value = e instanceof Error ? e.message : '任务提交失败'
      if (e instanceof ApiError && ['network','timeout'].includes(e.kind)) uncertain.value = true
    }
  } finally { if (version === revision) { creating.value = false; operation = null } }
}
watch(readOnly, value => {
  if (value) {
    if (creating.value) uncertain.value = true
    life.abort(); cancelOperation(); upload.value = null; selectedFile.value = null; caps.value = null; invalidate(); error.value = notice.value = ''
  } else { life = new AbortController(); void capabilities() }
}, {flush:'sync'})
onMounted(capabilities)
onBeforeUnmount(() => { disposed = true; life.abort(); cancelOperation(); emit('busy-change', false); emit('review-change', false) })
</script>

<template>
  <section class="controlled-import" aria-labelledby="import-preparation-title">
    <header class="import-heading"><span class="eyebrow">YOUR DATA / H5AD</span><h3 id="import-preparation-title">从自己的细胞数据开始</h3><p>上传真实对照与扰动数据，核对字段后建立独立数据版本。</p></header>
    <ol class="upload-steps" aria-label="自有数据导入步骤"><li v-for="(label, index) in ['上传文件', '配置分组与尺度', '核对并分析']" :key="label" :class="{current:stage === index + 1,done:stage > index + 1}" :aria-current="stage === index + 1 ? 'step' : undefined"><span>{{ index + 1 }}</span>{{ label }}</li></ol>
    <div v-if="readOnly" class="import-empty"><h3>当前工作区仅供浏览</h3><p>请进入私人工作区上传自己的数据。</p></div>
    <div v-else-if="!caps" class="import-empty"><p>{{ error || '正在读取上传能力…' }}</p><button v-if="error" class="btn" @click="capabilities">重新读取</button></div>
    <div v-else-if="!caps.available" class="import-empty"><h3>当前工作区尚未开放上传</h3><p>{{ caps.reason }}</p><RouterLink to="/status" class="btn">查看工作区状态</RouterLink></div>
    <template v-else>
      <input ref="fileInput" class="file-input" type="file" accept=".h5ad" aria-label="选择 H5AD 文件" :disabled="locked" @change="chooseFile" />
      <div v-if="!upload" class="upload-dropzone" :class="{dragging}" @dragover.prevent="!locked && (dragging = true)" @dragleave.prevent="dragging = false" @drop.prevent="dropFile">
        <span class="file-symbol" aria-hidden="true">↑</span><h4>{{ selectedFile ? selectedFile.name : '选择或拖入 H5AD 文件' }}</h4><p>包含细胞表达矩阵 X，以及 obs 中的对照与扰动分组。</p>
        <p class="file-limits">单文件 ≤ {{ formatBytes(caps.max_bytes) }} · {{ caps.max_cells.toLocaleString() }} 个细胞 · {{ caps.max_genes.toLocaleString() }} 个基因<br />矩阵 ≤ {{ caps.max_matrix_elements.toLocaleString() }} 个元素</p>
        <div v-if="uploading" class="upload-progress" role="status" aria-live="polite"><div><strong>{{ progress >= 100 ? '正在读取字段…' : '正在上传文件…' }}</strong><span>{{ progress }}%</span></div><progress :value="progress" max="100" aria-label="文件上传进度" /><p>{{ progress >= 100 ? '文件传输完成，正在检查结构与分组字段。' : '请保持页面打开，上传后将自动读取字段。' }}</p><button class="btn btn-sm" @click="cancelUpload">取消上传</button></div>
        <div v-else class="btn-row"><button class="btn btn-primary" :disabled="locked" @click="fileInput?.click()">{{ selectedFile ? '重新选择文件' : '选择 H5AD 文件' }}</button><button v-if="selectedFile && /\.h5ad$/i.test(selectedFile.name) && selectedFile.size > 0 && selectedFile.size <= caps.max_bytes" class="btn" :disabled="locked" @click="selectFile(selectedFile)">重试上传</button></div>
      </div>
      <div v-else class="file-summary"><div><span class="file-badge">H5AD</span><strong>{{ upload.filename }}</strong><small>{{ formatBytes(upload.bytes) }} · {{ upload.cells.toLocaleString() }} 个细胞 × {{ upload.genes.toLocaleString() }} 个基因</small></div><button class="btn btn-sm" :disabled="locked" @click="fileInput?.click()">更换文件</button></div>
      <form v-if="upload && !result" class="import-form" @submit.prevent="inspect">
        <div class="form-heading wide"><h4>定义这次比较</h4><p>字段来自上传文件；标签后的数字是对应细胞数量。</p></div>
        <label class="wide">分组列（obs）<select v-model="form.group_key" required :disabled="locked"><option disabled value="">选择包含对照与目标组的字段</option><option v-for="column in upload.obs_columns" :key="column.name" :value="column.name">{{ column.name }} · {{ column.unique_count }} 个不同值{{ column.missing_count ? ` · ${column.missing_count} 个缺失` : '' }}</option></select></label>
        <template v-if="groupColumn && exactLabels"><label>对照组<select v-model="form.control_label" required :disabled="locked"><option disabled value="">选择对照标签</option><option v-for="value in groupColumn.values" :key="value.label" :value="value.label" :disabled="value.count < 2">{{ value.label }} · {{ value.count.toLocaleString() }} 个细胞</option></select></label><label>扰动组<select v-model="form.target_label" required :disabled="locked"><option disabled value="">选择目标标签</option><option v-for="value in groupColumn.values" :key="value.label" :value="value.label" :disabled="value.count < 2">{{ value.label }} · {{ value.count.toLocaleString() }} 个细胞</option></select></label></template>
        <template v-else-if="groupColumn"><p class="field-note wide">该列的值未完整列出。请填写文件中的精确标签，提交时会验证对应细胞数量。</p><label>对照标签<input v-model="form.control_label" required :disabled="locked" placeholder="与文件中的标签完全一致" /></label><label>目标组标签<input v-model="form.target_label" required :disabled="locked" placeholder="与文件中的标签完全一致" /></label></template>
        <p v-if="form.control_label && form.control_label === form.target_label" class="field-error wide" role="alert">对照组与扰动组必须选择不同标签。</p>
        <label class="wide">表达尺度 <span class="field-hint">请根据数据处理记录明确选择，系统不会根据数值猜测。</span><select v-model="form.expression_scale" required :disabled="locked"><option disabled value="">请选择 X 的真实表达尺度</option><option value="log1p_cp10k">log1p(CP10K)</option><option value="cp10k">CP10K（未取对数）</option><option value="raw_counts">原始计数 raw counts</option></select></label>
        <template v-if="form.expression_scale === 'raw_counts'"><label class="check wide"><input v-model="form.full_library" type="checkbox" :disabled="locked" />确认 X 包含完整文库基因，可用每细胞行和计算总计数</label><label v-if="!form.full_library" class="wide">完整文库总计数列<select v-model="form.total_counts_key" required :disabled="locked"><option disabled value="">选择 obs 中的数值列</option><option v-for="column in numericColumns" :key="column.name" :value="column.name">{{ column.name }}</option></select><span class="field-hint">裁剪过的基因面板需要完整文库总计数，不能使用当前面板的行和。</span></label></template>
        <label>细胞背景<input v-model="form.cell_line" required pattern="[A-Za-z0-9_. \-]+" maxlength="32" :disabled="locked" placeholder="例如 K562，请核对原始记录" /><span class="field-hint">仅在文件记录了唯一背景时预填；所选两组必须与声明一致。</span></label><label>扰动名称<input v-model="form.perturbation" required pattern="[A-Za-z0-9_.\-]+" maxlength="64" :disabled="locked" placeholder="例如 ALDOA" /><span class="field-hint">请明确填写；支持英文字母、数字、点、下划线和连字符。</span></label>
        <details class="advanced wide"><summary>高级设置 · 批次与采样</summary><div class="advanced-fields"><label>批次列（可选）<select v-model="form.batch_key" :disabled="locked"><option value="">不指定批次</option><option v-for="column in upload.obs_columns" :key="column.name" :value="column.name">{{ column.name }}</option></select></label><label>每组细胞上限<input v-model.number="form.max_cells" type="number" min="2" max="4096" required :disabled="locked" /></label><label>固定采样种子<input v-model.number="form.seed" type="number" min="0" max="2147483647" required :disabled="locked" /></label></div></details>
        <p class="import-note wide">接下来会核对矩阵、分组与归一化条件，保存独立数据快照；核对完成后再创建描述性实测分析。</p><button class="btn btn-primary wide" :disabled="!ready">{{ busy ? '正在校验并建立数据版本…' : '校验并建立数据版本' }}</button>
      </form>
      <div v-if="result" class="import-preview"><span class="eyebrow">INPUT VERIFIED</span><h3>数据版本已建立</h3><p>{{ result.cell_line }} / {{ result.perturbation }} · {{ result.gene_count.toLocaleString() }} 个基因</p><div class="import-counts"><div><strong>{{ result.selected_counts.control }}</strong><span>选定对照细胞 / {{ result.group_counts.control }}</span></div><div><strong>{{ result.selected_counts.observed }}</strong><span>选定扰动细胞 / {{ result.group_counts.observed }}</span></div></div><dl><dt>输入尺度</dt><dd>{{ result.normalization.input_scale }}</dd><dt>统一输出</dt><dd>{{ result.normalization.output_scale }}</dd><dt>归一化分母</dt><dd>{{ result.normalization.denominator }}</dd></dl><details class="fingerprint"><summary>数据指纹</summary><code>{{ result.manifest_sha256 }}</code></details><ul><li v-for="line in result.limitations" :key="line">{{ line }}</li></ul><div class="btn-row"><button class="btn" :disabled="locked" @click="invalidate">修改配置</button><button class="btn btn-primary" :disabled="locked" @click="review(true)">{{ creating ? '正在提交…' : '核对并开始分析' }}</button></div></div>
    </template>
    <p v-if="notice" class="upload-notice" role="status">{{ notice }}</p><p v-if="error" class="notice notice-danger" role="alert">{{ error }}</p>
    <div v-if="uncertain" class="notice"><p>提交结果待确认。请先查看实验记录，避免重复创建。</p><RouterLink to="/records">核对实验记录</RouterLink> <button class="btn btn-sm" :disabled="readOnly" @click="uncertain = false">已核对，允许重新提交</button></div>
    <SubmissionReview v-if="reviewing && result && !readOnly" title="核对自有数据分析" :parameters="{'细胞背景':result.cell_line,'扰动':result.perturbation,'共同基因':result.gene_count,'数据版本':result.import_id}" @cancel="review(false)" @confirm="create" />
  </section>
</template>

<style scoped>
.controlled-import{padding:28px;max-width:1050px;margin:auto}.import-heading{margin-bottom:22px}.eyebrow{font:11px Consolas,monospace;letter-spacing:1.4px;color:var(--primary)}h3{font-size:22px;font-weight:500;margin:12px 0}h4{font-size:18px;font-weight:500;margin:0 0 10px}.import-heading p,.import-empty p,.form-heading p{font-size:13px;line-height:1.8;color:var(--muted);margin:0}.upload-steps{display:flex;gap:24px;list-style:none;padding:0 0 22px;margin:0 0 24px;border-bottom:1px solid var(--border)}.upload-steps li{display:flex;align-items:center;gap:9px;font-size:12px;color:var(--muted)}.upload-steps li span{display:grid;place-items:center;width:25px;height:25px;border-radius:50%;border:1px solid var(--border)}.upload-steps .current{color:var(--primary);font-weight:600}.upload-steps .current span{background:var(--primary);border-color:var(--primary);color:white}.upload-steps .done span{background:var(--primary-weak);color:var(--primary)}.file-input{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}.upload-dropzone{text-align:center;padding:35px 24px;border:1px dashed var(--primary-soft);border-radius:14px;background:var(--card-soft)}.upload-dropzone.dragging{border:2px solid var(--primary);background:var(--primary-weak)}.upload-dropzone h4{overflow-wrap:anywhere}.upload-dropzone p{font-size:13px;line-height:1.9;color:var(--muted)}.file-symbol{display:grid;place-items:center;width:48px;height:48px;border-radius:13px;background:var(--primary-weak);color:var(--primary);font-size:28px;margin:0 auto 17px}.file-limits{font-size:12px!important;margin:16px 0 22px}.upload-dropzone .btn-row{justify-content:center}.upload-progress{max-width:440px;margin:22px auto 0}.upload-progress>div{display:flex;justify-content:space-between;font-size:13px;color:var(--primary)}progress{display:block;width:100%;height:8px;margin:12px 0;accent-color:var(--primary);border:0;border-radius:6px;overflow:hidden}progress::-webkit-progress-bar{background:var(--border)}progress::-webkit-progress-value{background:var(--primary)}.upload-progress p{font-size:12px}.file-summary{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 20px;background:var(--primary-weak);border:1px solid var(--border);border-radius:12px;margin-bottom:27px}.file-summary>div{min-width:0}.file-summary strong{font-size:14px;font-weight:500;overflow-wrap:anywhere}.file-summary small{display:block;font-size:12px;color:var(--muted);margin-top:10px}.file-badge{font:10px Consolas,monospace;color:var(--primary);border:1px solid var(--primary-soft);padding:4px 6px;border-radius:4px;margin-right:10px}.file-summary .btn{flex-shrink:0}.import-form{display:grid;grid-template-columns:1fr 1fr;gap:22px 26px}.wide{grid-column:1/-1}.form-heading{margin:3px 0 0}label{display:grid;gap:8px;font-size:13px;color:var(--ink);align-content:start}input,select{width:100%;min-width:0;font:13px var(--font);color:var(--ink);background:var(--card);border:1px solid var(--border);padding:12px;border-radius:8px}input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid var(--primary);outline-offset:3px}.field-hint{font-size:12px;color:var(--muted);line-height:1.7;font-weight:400}.check{display:flex;align-items:flex-start;line-height:1.8;background:var(--card-soft);padding:14px;border-radius:8px}.check input{width:auto;margin-top:5px}.field-note,.field-error,.import-note{font-size:12px;line-height:1.8;margin:0;color:var(--muted)}.field-error{color:var(--danger,#ac3a34)}.advanced{border-block:1px solid var(--border);padding:16px 0}.advanced summary,.fingerprint summary{font-size:13px;color:var(--primary);cursor:pointer}.advanced-fields{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:18px}.import-note{margin:0}.import-empty{padding:24px 0}.import-preview{font-size:14px;line-height:1.9}.import-preview ul{padding-left:18px;color:var(--muted)}.import-counts{display:flex;border-block:1px solid var(--border);gap:60px;padding:20px 0;margin:24px 0}.import-counts strong{display:block;font-size:30px;font-weight:500;color:var(--primary)}.import-counts span{font-size:13px;color:var(--muted)}dl{display:grid;grid-template-columns:130px 1fr;gap:12px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}.fingerprint{background:var(--card-soft);padding:12px 16px;border-radius:8px}.fingerprint code{display:block;margin-top:8px;font-size:11px;overflow-wrap:anywhere}.upload-notice{font-size:12px;line-height:1.8;color:var(--primary);margin:20px 0 0}.notice{margin-top:20px}.btn-row{display:flex;flex-wrap:wrap;gap:10px}button:disabled{opacity:.55;cursor:not-allowed}@media(max-width:650px){.controlled-import{padding:20px 18px}.upload-steps{gap:12px;justify-content:space-between}.upload-steps li{flex-direction:column;align-items:flex-start;gap:8px;font-size:11px}.import-form,.advanced-fields{grid-template-columns:1fr}.file-summary{align-items:flex-start;padding:15px;gap:12px}.file-badge{display:none}.file-summary .btn{padding:8px 10px}.upload-dropzone{padding:28px 16px}.import-counts{gap:24px}.import-counts strong{font-size:27px}dl{grid-template-columns:100px 1fr}}
</style>
