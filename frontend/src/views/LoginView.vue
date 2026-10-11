<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
const auth = useAuthStore(), route = useRoute(), router = useRouter()
const username = ref(''), password = ref(''), busy = ref(false), error = ref('')
async function submit() {
  busy.value = true; error.value = ''
  try {
    await auth.login(username.value.trim(), password.value); password.value = ''
    const next = typeof route.query.next === 'string' ? route.query.next : ''
    await router.push(next === '/datasets' || next.startsWith('/datasets?') || next.startsWith('/analyses/') ? next : '/datasets')
  } catch (reason) {error.value = reason instanceof Error ? reason.message : '登录失败'}
  finally {busy.value = false}
}
</script>
<template>
  <div class="page login-layout">
    <section class="login-intro"><span class="eyebrow">YOUR RESEARCH DATA</span><h1>让自己的数据<br />进入分析流程</h1><p>上传单细胞表达数据，检查数据质量，探索细胞结构，并追踪表达与代谢任务的关系。</p><ol><li>校验表达单位与基因标识</li><li>选择分组和分析任务</li><li>保存可复查的结果与来源</li></ol><RouterLink to="/workbench">进入预设实验工作台 →</RouterLink></section>
    <form class="card login-form" @submit.prevent="submit"><span class="eyebrow">RESEARCH ACCOUNT</span><h2>登录科研账号</h2><p class="muted">账号由部署管理员创建。个人数据与分析结果仅对所属账号开放。</p><div v-if="error || auth.error" class="notice notice-danger" role="alert">{{ error || auth.error }}</div><label class="label" for="login-user">用户名</label><input id="login-user" v-model="username" class="input" required autocomplete="username" maxlength="64" /><label class="label" for="login-password">密码</label><input id="login-password" v-model="password" class="input" type="password" required autocomplete="current-password" maxlength="256" /><button class="btn btn-primary" type="submit" :disabled="busy">{{ busy ? '正在登录…' : '登录并打开我的数据' }}</button><p class="muted">忘记密码时请联系管理员重置。会话到期后需重新登录。</p></form>
  </div>
</template>
<style scoped>
.login-layout{display:grid;grid-template-columns:1.2fr 1fr;gap:100px;align-items:center;padding-top:80px;padding-bottom:80px;max-width:1080px}.login-intro h1{font-size:42px;font-weight:500;line-height:1.45;margin:20px 0}.login-intro p{max-width:420px;color:var(--muted);font-size:15px;line-height:2}.login-intro ol{padding:0;list-style:none;counter-reset:steps;margin:36px 0}.login-intro li{counter-increment:steps;border-top:1px solid var(--border);padding:15px 0;font-size:13px}.login-intro li:before{content:'0' counter(steps);margin-right:20px;color:var(--primary);font-family:Georgia,serif}.login-form{padding:36px}.login-form h2{font-weight:500;font-size:25px;margin:12px 0}.login-form .input{margin-bottom:20px}.login-form .btn{width:100%;margin:12px 0}.muted{color:var(--muted);font-size:12px;line-height:1.9}.login-form .notice{margin-bottom:20px}@media(max-width:800px){.login-layout{gap:30px;padding-top:30px;grid-template-columns:1fr}.login-intro h1{font-size:30px}.login-intro ol{display:none}.login-form{padding:24px}}
</style>
