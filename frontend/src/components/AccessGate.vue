<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { apiFetch } from '../api/http'
import { accessSession, type AccessSession } from '../stores/access'
const emit=defineEmits<{ready:[]}>()
const loading=ref(true), error=ref(''), token=ref(''), submitting=ref(false)
const lifetime=new AbortController()
const allowed=computed(()=>accessSession.value&&(accessSession.value.mode!=='private'||accessSession.value.authenticated))
let inspection: AbortController | undefined
async function inspect(){
 inspection?.abort(); const current=inspection=new AbortController(); loading.value=true;error.value=''
 try{const session=await apiFetch<AccessSession>('/auth/session',{signal:current.signal});if(lifetime.signal.aborted||current.signal.aborted||inspection!==current)return;accessSession.value=session;if(allowed.value)emit('ready')}
 catch(e){if(!lifetime.signal.aborted&&!current.signal.aborted)error.value=e instanceof Error?e.message:'工作区状态读取失败'}
 finally{if(!lifetime.signal.aborted&&inspection===current)loading.value=false}
}
async function login(){if(submitting.value)return;submitting.value=true;error.value='';try{await apiFetch('/auth/session',{method:'POST',body:{token:token.value},signal:lifetime.signal});if(lifetime.signal.aborted)return;token.value='';await inspect()}catch(e){if(!lifetime.signal.aborted)error.value=e instanceof Error?e.message:'工作区口令验证失败'}finally{if(!lifetime.signal.aborted)submitting.value=false}}
async function logout(){
 if(submitting.value)return;submitting.value=true;error.value='';inspection?.abort()
 try{await apiFetch('/auth/session',{method:'DELETE',signal:lifetime.signal});if(!lifetime.signal.aborted)window.location.reload()}
 catch(e){if(!lifetime.signal.aborted)error.value=e instanceof Error?e.message:'退出工作区失败，请重试'}
 finally{if(!lifetime.signal.aborted)submitting.value=false}
}
onMounted(inspect);onBeforeUnmount(()=>{lifetime.abort();inspection?.abort()})
</script>
<template>
 <template v-if="allowed"><div v-if="accessSession?.read_only" class="access-banner">公开研究展览 · 仅展示已发布的冻结结果 <span>分析提交与私人笔记已关闭</span></div><div v-else-if="accessSession?.mode==='private'" class="access-banner">私人研究工作区 <button :disabled="submitting" @click="logout">{{submitting?'正在退出…':'退出工作区'}}</button></div><div v-if="error" class="access-session-error" role="alert">{{error}}</div><slot/></template>
 <main v-else class="access-screen"><section class="access-card"><span class="eyebrow">CELLLENS / RESEARCH WORKSPACE</span><h1>{{loading?'正在连接研究工作区':accessSession?.mode==='private'?'进入私人研究工作区':'研究服务暂不可用'}}</h1><p>细胞知镜 · 连接数据、表达响应与功能证据</p><form v-if="!loading&&accessSession?.mode==='private'&&accessSession.configured" @submit.prevent="login"><label for="workspace-key">工作区访问口令</label><input id="workspace-key" v-model="token" type="password" autocomplete="current-password" required placeholder="输入部署时设置的访问口令"/><button class="btn btn-primary" :disabled="submitting||!token">{{submitting?'正在验证…':'进入工作区'}}</button></form><p v-if="accessSession?.mode==='private'&&!accessSession.configured">此工作区尚未配置访问口令，请由部署人员完成初始化。</p><p v-if="error" class="access-error" role="alert">{{error}}</p><button v-if="!loading" class="btn" @click="inspect">重新连接</button><small>口令仅用于当前工作区验证，不保存在浏览器本地存储中。</small></section></main>
</template>
<style scoped>
.access-banner{background:#163e2d;color:#e6f0dd;padding:8px 5vw;font-size:11px;display:flex;justify-content:space-between;gap:15px}.access-banner span{opacity:.7}.access-banner button{background:none;border:0;color:inherit;text-decoration:underline;cursor:pointer}.access-screen{min-height:100dvh;display:grid;place-items:center;padding:30px;background:radial-gradient(ellipse at 80% 20%,#dce9ba,transparent 55%),#e9efdf}.access-card{max-width:570px;padding:45px;background:#f8f9f1;border:1px solid #c6d4b8;border-radius:24px;box-shadow:0 20px 80px #26402918;color:#163e2d}.eyebrow{font:10px Consolas,monospace;letter-spacing:2px}h1{font-size:29px;line-height:1.4;font-weight:500;margin:24px 0 12px}p{font-size:13px;line-height:1.8;color:#5c715a}form{display:grid;gap:13px;margin:30px 0}label{font-size:12px}input{border:1px solid #bdceb1;border-radius:9px;background:#fff;padding:14px;font:inherit}small{display:block;color:#72846a;font-size:10px;line-height:1.8;margin-top:25px}.access-error{color:#9c4f36}
.access-session-error{padding:12px 5vw;font-size:12px;line-height:1.8;background:var(--danger-bg);color:var(--danger)}
</style>
