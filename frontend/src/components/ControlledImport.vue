<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch, ApiError } from '../api/http'
import SubmissionReview from './SubmissionReview.vue'
interface Capabilities{available:boolean;reason?:string;max_bytes:number;max_cells:number;max_genes:number;max_matrix_elements:number;path_format?:string;path_example?:string;import_directory?:string|null}
interface ImportResult{import_id:string;manifest_sha256:string;cell_line:string;perturbation:string;gene_count:number;group_counts:Record<string,number>;selected_counts:Record<string,number>;normalization:{input_scale:string;output_scale:string;denominator:string};limitations:string[]}
const emit=defineEmits<{'review-change':[open:boolean];'busy-change':[busy:boolean]}>(),router=useRouter(),life=new AbortController()
const caps=ref<Capabilities|null>(null),error=ref(''),busy=ref(false),creating=ref(false),uncertain=ref(false),reviewing=ref(false),result=ref<ImportResult|null>(null)
const form=reactive({relative_path:'',expression_scale:'log1p_cp10k',full_library:false,total_counts_key:'',group_key:'gene',control_label:'non-targeting',target_label:'',cell_line:'K562',perturbation:'',batch_key:'',max_cells:256,seed:42})
const preparationScript = [
  'import anndata as ad',
  '',
  'data = ad.read_h5ad("experiment.h5ad", backed="r")',
  'try:',
  '    print("细胞 × 基因:", data.shape)',
  '    print("obs 列:", data.obs.columns.tolist())',
  '    print("基因 ID 示例:", data.var_names[:8].tolist())',
  '    if "gene" in data.obs:',
  '        print(data.obs["gene"].value_counts(dropna=False))',
  'finally:',
  '    data.file.close()',
].join('\n')
const ready=computed(()=>caps.value?.available&&form.relative_path.trim()&&form.group_key.trim()&&form.control_label&&form.target_label&&form.target_label!==form.control_label&&form.cell_line&&form.perturbation&&(form.expression_scale!=='raw_counts'||form.full_library||form.total_counts_key.trim())&&!busy.value)
watch([busy,creating],()=>emit('busy-change',busy.value||creating.value),{flush:'sync'})
function review(open:boolean){reviewing.value=open;emit('review-change',open)}
async function capabilities(){try{caps.value=await apiFetch('/research/imports/capabilities',{signal:life.signal});error.value=''}catch(e){if(!life.signal.aborted)error.value=e instanceof Error?e.message:'导入能力读取失败'}}
async function inspect(){if(!ready.value)return;busy.value=true;error.value='';result.value=null
 try{result.value=await apiFetch<ImportResult>('/research/imports',{method:'POST',body:{...form,relative_path:form.relative_path.trim(),total_counts_key:form.total_counts_key.trim()||undefined,batch_key:form.batch_key.trim()||undefined},timeoutMs:120000,signal:life.signal})}
 catch(e){if(!life.signal.aborted)error.value=e instanceof Error?e.message:'文件校验失败'}finally{busy.value=false}
}
async function create(){review(false);if(!result.value||creating.value||uncertain.value)return;creating.value=true;error.value=''
 try{const record=await apiFetch<{id:string}>(`/research/imports/${encodeURIComponent(result.value.import_id)}/analyses`,{method:'POST',signal:life.signal});if(!life.signal.aborted)await router.push(`/measured/${encodeURIComponent(record.id)}`)}
 catch(e){if(!life.signal.aborted){error.value=e instanceof Error?e.message:'任务提交失败';if(e instanceof ApiError&&['network','timeout'].includes(e.kind))uncertain.value=true}}finally{creating.value=false}
}
onMounted(capabilities);onBeforeUnmount(()=>{life.abort();emit('busy-change',false);emit('review-change',false)})
</script>
<template><section class="controlled-import">
  <section class="import-preparation" aria-labelledby="import-preparation-title">
    <h3 id="import-preparation-title">先准备文件，再建立数据版本</h3>
    <p>此入口读取部署机器的受控目录，不提供浏览器上传。请使用已有的真实对照与扰动 H5AD，并确认来源与表达尺度。</p>
    <ol>
      <li><strong>放置文件：</strong>本地部署时，将文件复制到下方目录；远程部署时，请部署者代为放入并告知相对路径。<div v-if="caps?.import_directory" class="import-directory"><span>当前受控目录</span><code>{{ caps.import_directory }}</code></div><span v-else class="directory-unavailable">目录尚未提供，请部署者确认受控导入配置后继续。</span></li>
      <li><strong>核对字段：</strong>确认 <code>X</code> 的尺度、<code>obs</code> 中的分组列和两个标签。下方可查看最小字段示例及只读检查代码。</li>
      <li><strong>填写相对路径：</strong>如目录中的 <code>experiment.h5ad</code>，填写同名文件；子目录中的文件可填写 <code>study/experiment.h5ad</code>。随后校验并保存独立快照，核对后再创建分析。</li>
    </ol>
    <details class="preparation-details">
      <summary>数据准备：最小字段示例与只读检查</summary>
      <p>以下是字段格式示例，不是可用于研究的示例数据。分组标签必须与原文件完全一致，细胞 ID 与基因 ID 必须唯一。</p>
      <div class="table-wrap"><table class="table"><thead><tr><th>H5AD 字段</th><th>示例</th><th>填写或检查</th></tr></thead><tbody>
        <tr><td><code>X</code></td><td>细胞 × 基因数值矩阵</td><td>明确选择 log1p(CP10K)、CP10K 或原始计数；不得用缩放后的 z-score 代替。</td></tr>
        <tr><td><code>obs_names</code></td><td><code>cell_001</code>、<code>cell_002</code></td><td>每个细胞使用唯一 ID。</td></tr>
        <tr><td><code>var_names</code></td><td><code>ALDOA</code>、<code>GAPDH</code></td><td>唯一、无空值和首尾空格；代谢覆盖取决于与知识库的实际匹配。</td></tr>
        <tr><td><code>obs["gene"]</code></td><td><code>non-targeting</code> / <code>ALDOA</code></td><td>分组列填 gene，对照标签填 non-targeting，目标组标签填 ALDOA。</td></tr>
        <tr><td><code>obs["cell_line"]</code>（可选）</td><td><code>K562</code></td><td>若存在，所选两组必须与声明背景一致。</td></tr>
        <tr><td><code>obs["total_counts"]</code>（按需）</td><td>每细胞的完整文库总计数</td><td>裁剪过的原始计数矩阵必须提供；当前基因面板的行和不能代替。</td></tr>
      </tbody></table></div>
      <p>在已安装 AnnData 的数据处理环境中，将以下代码保存为 <code>inspect_h5ad.py</code>，与文件放在同一目录，运行 <code>python inspect_h5ad.py</code>。它只读取字段与分组数量，不修改文件，也不推断表达尺度；完整校验仍在提交表单后执行。</p>
      <pre><code>{{ preparationScript }}</code></pre>
      <a href="https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html" target="_blank" rel="noopener">AnnData H5AD 读取说明 ↗</a>
    </details>
  </section><div v-if="!caps" class="import-empty"><p>{{error||'正在读取本地导入能力…'}}</p><button v-if="error" class="btn" @click="capabilities">重新读取</button></div><div v-else-if="!caps.available" class="import-empty"><span class="eyebrow">PRIVATE DATA / CONTROLLED IMPORT</span><h3>自有 H5AD 分析</h3><p>{{caps.reason}}</p><p>在私人或本地工作区启用受控目录后，可以导入自己的对照与扰动数据。此入口进行描述性实测比较。</p><RouterLink to="/status" class="btn">查看工作区状态</RouterLink></div><template v-else><form v-if="!result" class="import-form" @submit.prevent="inspect"><div class="import-intro"><h3>核对 H5AD 输入</h3><p>{{caps.path_format || "填写受控目录内的相对 .h5ad 路径"}}。文件已放置后，按原始字段填写下表。</p><small>文件 ≤ {{Math.floor(caps.max_bytes/1024/1024)}} MB · {{caps.max_cells.toLocaleString()}} 个细胞 · {{caps.max_genes.toLocaleString()}} 个基因 · 矩阵 ≤ {{caps.max_matrix_elements.toLocaleString()}} 个元素</small></div><label class="wide">H5AD 相对文件路径<input v-model="form.relative_path" :placeholder="caps.path_example||'experiment.h5ad'" required/></label><label>表达尺度<select v-model="form.expression_scale"><option value="log1p_cp10k">log1p(CP10K)</option><option value="cp10k">CP10K（未取对数）</option><option value="raw_counts">原始计数 raw counts</option></select></label><label>分组列（obs）<input v-model="form.group_key" required/></label><template v-if="form.expression_scale==='raw_counts'"><label class="check wide"><input v-model="form.full_library" type="checkbox"/>X 包含完整文库基因，确认可在筛选基因前计算每细胞总计数</label><label class="wide">全库总计数列（裁剪矩阵必须提供）<input v-model="form.total_counts_key" placeholder="例如 total_counts，不是当前面板的行和"/></label></template><label>对照标签<input v-model="form.control_label" required/></label><label>目标组标签<input v-model="form.target_label" required placeholder="与 obs 中目标组标签一致"/></label><label>细胞背景<input v-model="form.cell_line" required pattern="[A-Za-z0-9_. -]+" maxlength="32"/></label><label>扰动名称<input v-model="form.perturbation" required pattern="[A-Za-z0-9_.-]+" maxlength="64" placeholder="例如 ALDOA"/></label><label>批次列（可选）<input v-model="form.batch_key" placeholder="例如 gem_group"/></label><label>每组细胞上限<input v-model.number="form.max_cells" type="number" min="2" max="4096" required/></label><label>固定采样种子<input v-model.number="form.seed" type="number" min="0" max="2147483647" required/></label><p class="wide import-note">系统不根据数值猜测表达尺度。文件检查通过后，将保存独立的数据快照与指纹，再创建分析任务。</p><button class="btn btn-primary wide" :disabled="!ready">{{busy?'正在核对文件与表达尺度…':'校验并建立数据版本'}}</button></form><div v-else class="import-preview"><span class="eyebrow">INPUT VERIFIED</span><h3>数据版本已建立</h3><p>{{result.cell_line}} / {{result.perturbation}} · {{result.gene_count.toLocaleString()}} 个基因</p><div class="import-counts"><div><strong>{{result.selected_counts.control}}</strong><span>选定对照细胞 / {{result.group_counts.control}}</span></div><div><strong>{{result.selected_counts.observed}}</strong><span>选定扰动细胞 / {{result.group_counts.observed}}</span></div></div><dl><dt>输入尺度</dt><dd>{{result.normalization.input_scale}}</dd><dt>统一输出</dt><dd>{{result.normalization.output_scale}}</dd><dt>归一化分母</dt><dd>{{result.normalization.denominator}}</dd></dl><p class="import-fingerprint">{{result.manifest_sha256}}</p><ul><li v-for="line in result.limitations" :key="line">{{line}}</li></ul><div class="btn-row"><button class="btn" :disabled="creating" @click="result=null">导入另一版本</button><button class="btn btn-primary" :disabled="creating||uncertain" @click="review(true)">{{creating?'正在提交…':'核对并开始分析'}}</button></div></div></template><p v-if="error" class="notice notice-danger" role="alert">{{error}}</p><div v-if="uncertain" class="notice"><p>提交结果待确认。请先查看实验记录，避免重复创建。</p><RouterLink to="/records">核对实验记录</RouterLink> <button class="btn btn-sm" @click="uncertain=false">已核对，允许重新提交</button></div><SubmissionReview v-if="reviewing&&result" title="核对自有数据分析" :parameters="{'细胞背景':result.cell_line,'扰动':result.perturbation,'共同基因':result.gene_count,'数据版本':result.import_id}" @cancel="review(false)" @confirm="create"/></section></template>
<style scoped>.controlled-import{padding:28px}.import-form{display:grid;grid-template-columns:1fr 1fr;gap:20px 28px;max-width:900px;margin:auto}.import-intro,.wide{grid-column:1/-1}h3{font-size:21px;font-weight:500;margin:0 0 14px}.import-intro p,.import-note,.import-empty p{font-size:14px;color:var(--muted);line-height:1.9}.import-intro small{font:12px Consolas,monospace;color:var(--primary)}label{display:grid;gap:9px;font-size:14px;color:var(--muted)}input,select{width:100%;font:13px var(--font);color:var(--ink);background:var(--card);border:1px solid var(--border);padding:12px;border-radius:8px}.check{display:flex;align-items:center;line-height:1.8}.check input{width:auto}.import-empty{padding:35px;max-width:700px}.import-preview{max-width:750px;margin:auto;font-size:14px;line-height:1.9}.import-preview ul{padding-left:18px;color:var(--muted)}.import-counts{display:flex;border-block:1px solid var(--border);gap:60px;padding:20px 0;margin:25px 0}.import-counts strong{display:block;font-size:30px;font-weight:500;color:var(--primary)}.import-counts span{color:var(--muted)}dl{display:grid;grid-template-columns:130px 1fr;gap:12px}dt{color:var(--muted)}dd{margin:0}.import-fingerprint{font:12px/1.8 Consolas,monospace;overflow-wrap:anywhere;background:var(--surface-soft);padding:13px}.eyebrow{color:var(--primary);font:12px Consolas,monospace;letter-spacing:1px}@media(max-width:650px){.import-form{grid-template-columns:1fr}.controlled-import{padding:18px}.import-counts{gap:25px}}.import-preparation{max-width:900px;margin:0 auto 28px;padding:22px 24px;border:1px solid var(--border-strong);border-radius:12px;background:var(--card-soft);font-size:14px;line-height:1.85}.import-preparation h3{font-size:20px}.import-preparation p{color:var(--muted);margin:10px 0}.import-preparation ol{padding-left:22px;margin:15px 0 0}.import-preparation li+li{margin-top:12px}.import-preparation code{font-size:12px;overflow-wrap:anywhere}.import-directory{display:grid;gap:5px;margin-top:8px;padding:10px 14px;border-radius:8px;background:var(--card);border:1px solid var(--border)}.import-directory span,.directory-unavailable{font-size:12px;color:var(--muted)}.directory-unavailable{display:block}.preparation-details{margin-top:18px;border-top:1px solid var(--border);padding-top:14px}.preparation-details summary{cursor:pointer;color:var(--primary);font-weight:600}.preparation-details pre{overflow:auto;max-width:100%;padding:16px;background:var(--code-bg);border-radius:8px;line-height:1.8}.preparation-details a{font-size:12px;color:var(--primary)}.preparation-details .table-wrap{overflow:auto;margin:16px 0}.preparation-details table{min-width:600px}.preparation-details td{font-size:13px}.import-intro small{font-family:var(--font);font-size:12px;line-height:1.8;display:block}@media(max-width:650px){.import-preparation{padding:18px}.import-preparation h3{font-size:18px}.import-empty{padding:18px}dl{grid-template-columns:100px 1fr}}
</style>
