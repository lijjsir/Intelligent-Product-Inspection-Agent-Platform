<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, type FormInstance, type FormRules } from 'element-plus';
import { User, Lock, CircleCheck } from '@element-plus/icons-vue';
import { useUserStore } from '@/stores/user.store';
import { formatServerDateTime } from '@/utils/date-time';

const store = useUserStore();
const activeTab = ref<'profile'|'security'>('profile');
const loading = ref(false);
const savingProfile = ref(false);
const changingPassword = ref(false);
const profileFormRef = ref<FormInstance>();
const passwordFormRef = ref<FormInstance>();
const profileForm = reactive({ username:'', email:'' });
const passwordForm = reactive({ current_password:'', new_password:'', confirm_password:'' });
const roleNames: Record<string,string> = {user:'普通用户',expert:'质监专家',admin:'系统管理员',app_developer:'应用开发者',platform_operator:'平台运营',algorithm_engineer:'算法工程师'};
const roleLabel = computed(() => roleNames[store.current?.role || ''] || '平台用户');
const hasProfileChanges = computed(() => profileForm.username.trim() !== store.current?.username || profileForm.email.trim() !== store.current?.email);
const profileRules: FormRules = {
  username:[{required:true,message:'请输入用户名',trigger:'blur'}],
  email:[{required:true,type:'email',message:'请输入有效邮箱',trigger:'blur'}],
};
const passwordRules: FormRules = {
  current_password:[{required:true,message:'请输入当前密码',trigger:'blur'}],
  new_password:[{required:true,min:6,message:'新密码至少6个字符',trigger:'blur'}],
  confirm_password:[{validator:(_rule,value,callback) => value && value === passwordForm.new_password ? callback() : callback(new Error('两次输入的新密码不一致')),trigger:'blur'}],
};

onMounted(async () => {
  loading.value = true;
  try { const user = await store.fetchCurrentUser(); profileForm.username=user.username; profileForm.email=user.email; }
  catch { ElMessage.error('无法加载个人资料，请稍后重试'); }
  finally { loading.value=false; }
});

async function handleSaveProfile() {
  if (!await profileFormRef.value?.validate().catch(() => false)) return;
  savingProfile.value=true;
  try {
    const user=await store.updateCurrentUser({username:profileForm.username.trim(),email:profileForm.email.trim()});
    profileForm.username=user.username; profileForm.email=user.email;
    ElMessage.success('个人资料已保存');
  } catch (error: any) { ElMessage.error(error?.response?.data?.message || '保存失败，请重试'); }
  finally { savingProfile.value=false; }
}

async function handleChangePassword() {
  if (!await passwordFormRef.value?.validate().catch(() => false)) return;
  changingPassword.value=true;
  try {
    await store.updateCurrentUser({current_password:passwordForm.current_password,new_password:passwordForm.new_password});
    passwordForm.current_password=''; passwordForm.new_password=''; passwordForm.confirm_password='';
    ElMessage.success('密码已更新');
  } catch (error: any) { ElMessage.error(error?.response?.data?.message || '密码更新失败，请重试'); }
  finally { changingPassword.value=false; }
}
</script>

<template>
  <div class="profile-page" v-loading="loading">
    <header class="settings-heading"><h1>个人设置</h1><p>管理你的个人资料与账号安全</p></header>
    <div class="settings-layout">
      <nav class="settings-navigation" aria-label="设置分类">
        <button :class="{active:activeTab==='profile'}" @click="activeTab='profile'"><User />个人资料</button>
        <button :class="{active:activeTab==='security'}" @click="activeTab='security'"><Lock />账号安全</button>
      </nav>
      <main class="settings-content">
        <section v-if="activeTab==='profile'" class="settings-section">
          <div class="section-heading"><h2>个人资料</h2><p>用于登录和平台联系的基本信息</p></div>
          <div class="account-summary"><span class="account-symbol"><User /></span><div><strong>{{ store.current?.username || '当前账号' }}</strong><small>{{ roleLabel }}</small></div><span class="account-state"><CircleCheck />{{ store.current?.is_active ? '账号正常' : '账号已停用' }}</span></div>
          <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-position="top" class="settings-form">
            <el-form-item label="用户名" prop="username"><el-input v-model="profileForm.username" placeholder="你的用户名" maxlength="64" /></el-form-item>
            <el-form-item label="邮箱" prop="email"><el-input v-model="profileForm.email" placeholder="用于接收平台联系信息" /></el-form-item>
            <div class="settings-form-actions"><el-button type="primary" :loading="savingProfile" :disabled="!hasProfileChanges" @click="handleSaveProfile">保存修改</el-button></div>
          </el-form>
          <div class="account-detail"><span>加入平台</span><span>{{ formatServerDateTime(store.current?.created_at) || '暂无记录' }}</span></div>
        </section>
        <section v-else class="settings-section">
          <div class="section-heading"><h2>账号安全</h2><p>验证当前密码后设置新密码</p></div>
          <el-form ref="passwordFormRef" :model="passwordForm" :rules="passwordRules" label-position="top" class="settings-form">
            <el-form-item label="当前密码" prop="current_password"><el-input v-model="passwordForm.current_password" type="password" show-password autocomplete="current-password" /></el-form-item>
            <el-form-item label="新密码" prop="new_password"><el-input v-model="passwordForm.new_password" type="password" show-password autocomplete="new-password" placeholder="至少6个字符" /></el-form-item>
            <el-form-item label="确认新密码" prop="confirm_password"><el-input v-model="passwordForm.confirm_password" type="password" show-password autocomplete="new-password" /></el-form-item>
            <div class="settings-form-actions"><el-button type="primary" :loading="changingPassword" @click="handleChangePassword">更新密码</el-button></div>
          </el-form>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.profile-page { width:min(100%,1020px); margin:16px auto; color:#30435a; }
.settings-heading { margin:0 0 32px; }
.settings-heading h1 { font-size:26px; font-weight:600; margin:0 0 9px; letter-spacing:0; }
.settings-heading p { margin:0; font-size:13px; color:#8b9bb0; }
.settings-layout { display:grid; grid-template-columns:180px minmax(0,1fr); gap:32px; }
.settings-navigation { display:flex; flex-direction:column; gap:6px; }
.settings-navigation button { display:flex; align-items:center; gap:9px; padding:12px 14px; border:0; border-radius:9px; background:transparent; color:#8294ad; text-align:left; font:inherit; font-size:13px; cursor:pointer; }
.settings-navigation button.active { background:#eaf2ff; color:#356bac; font-weight:500; }
.settings-navigation svg { width:17px; height:17px; }
.settings-content { min-width:0; }
.settings-section { background:#fff; border:1px solid #e2e9f2; border-radius:14px; padding:30px 34px; }
.section-heading h2 { font-size:18px; font-weight:600; margin:0 0 7px; }
.section-heading p { font-size:12px; color:#92a0b3; margin:0 0 27px; }
.account-summary { display:flex; align-items:center; gap:12px; padding-bottom:22px; margin-bottom:24px; border-bottom:1px solid #edf1f6; }
.account-symbol { width:42px; height:42px; border-radius:12px; background:#edf4ff; color:#6e96c4; display:grid; place-items:center; }
.account-symbol svg { width:23px; height:23px; }
.account-summary strong { display:block; font-size:14px; font-weight:500; }
.account-summary small { display:block; margin-top:5px; font-size:11px; color:#95a2b5; }
.account-state { margin-left:auto; color:#6c9985; font-size:11px; display:flex; align-items:center; gap:5px; }
.account-state svg { width:14px; height:14px; }
.settings-form { max-width:430px; }
.settings-form :deep(.el-form-item__label) { font-size:12px; color:#526986; padding-bottom:5px; }
.settings-form :deep(.el-input__wrapper) { min-height:38px; border-radius:8px; }
.settings-form-actions { display:flex; padding-top:9px; }
.settings-form-actions :deep(.el-button) { border-radius:8px; box-shadow:none; font-size:12px; }
.account-detail { display:flex; justify-content:space-between; gap:18px; border-top:1px solid #edf1f6; padding-top:20px; margin-top:27px; font-size:11px; color:#99a6b7; }
.settings-navigation button:focus-visible { outline:2px solid #87b3ec; outline-offset:2px; }
@media(max-width:700px) { .profile-page { margin:7px auto; } .settings-layout { grid-template-columns:1fr; gap:16px; } .settings-navigation { flex-direction:row; } .settings-section { padding:22px 18px; } .settings-heading { margin-bottom:20px; } .account-state { font-size:10px; } }
</style>
