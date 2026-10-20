<script setup lang="ts">
import {onBeforeUnmount,onMounted,ref,watch} from 'vue';
import {useRoute,useRouter} from 'vue-router';
import {collabApi} from '@/api/collab.api';
import {meetingApi} from '@/api/meeting.api';
import {extractApiErrorMessage} from '@/api/http';
import type {CollabWorkItem,CollabWorkItemView,CollabThread,CollabMessage} from '@/types/collab.types';
const route=useRoute(),router=useRouter(),rows=ref<CollabWorkItem[]>([]),selected=ref<CollabWorkItem|null>(null);
const error=ref(''),loading=ref(false),view=ref<CollabWorkItemView>('initiated'),cursor=ref<string|null>(null),more=ref<string|null>(null);
const threads=ref<CollabThread[]>([]),messages=ref<CollabMessage[]>([]),threadError=ref('');
let epoch=0,threadEpoch=0;
function safeUrl(value:unknown){if(typeof value!=='string')return '';try{const url=new URL(value,location.origin);return ['http:','https:'].includes(url.protocol)?url.href:'';}catch{return '';}}
async function load(){const key=++epoch;loading.value=true;error.value='';rows.value=[];selected.value=null;more.value=null;
  try{const page=(await collabApi.workItemPage({view:view.value,cursor:cursor.value})).data.data;
    const pinned=typeof route.query.work_item==='string'?route.query.work_item:'';
    const detail=pinned?(await collabApi.workItemDetail(pinned)).data.data:null;
    if(key!==epoch)return;rows.value=page.items;more.value=page.next_cursor;selected.value=detail;
  }catch(e){if(key===epoch)error.value=extractApiErrorMessage(e,'历史记录暂不可读取，请重试');}
  finally{if(key===epoch)loading.value=false;}}
async function cancel(){const item=selected.value;if(!item||item.item_type!=='memory_share'||!item.allowed_actions.includes('cancel'))return;
  try{await meetingApi.cancelMemoryShare(item.resource_id);await load();}catch(e){error.value=extractApiErrorMessage(e,'旧申请未能撤回');}}
async function history(){const key=++threadEpoch;threadError.value='';messages.value=[];
  try{const value=(await collabApi.listThreads()).data.data;if(key===threadEpoch)threads.value=value;}
  catch(e){if(key===threadEpoch)threadError.value=extractApiErrorMessage(e,'旧会话暂不可读取');}}
async function showThread(id:string){const key=++threadEpoch;messages.value=[];threadError.value='';try{const value=(await collabApi.listMessages(id)).data.data;if(key===threadEpoch)messages.value=value;}
  catch(e){if(key===threadEpoch)threadError.value=extractApiErrorMessage(e,'旧会话无权访问或已不可用');}}
watch(()=>route.query.work_item,()=>void load());
onMounted(()=>{void load();});onBeforeUnmount(()=>{++epoch;++threadEpoch;});
</script>
<template>
  <main class="legacy-collaboration" v-loading="loading"><header><h1>历史共享与请求记录</h1><el-button @click="router.push('/app/meetings')">返回会议室</el-button></header>
    <el-alert title="独立协同中心已取消。本页仅兼容历史记录；不再新增处理请求或推进研判协作。会议记忆共享在会议室办理，组织审批在管理员入口办理。" type="info" :closable="false" />
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div class="actions"><el-radio-group v-model="view" @change="cursor=null;load()"><el-radio-button value="initiated">我发起的记录</el-radio-button><el-radio-button value="processed">已处理记录</el-radio-button><el-radio-button value="pending">历史未结记录</el-radio-button></el-radio-group><el-button @click="load">刷新历史</el-button></div>
    <el-table :data="rows" empty-text="当前范围没有历史记录"><el-table-column prop="title" label="标题" min-width="180"/><el-table-column label="类型"><template #default="{row}">{{ row.item_type==='memory_share'?'记忆共享':'历史处理请求' }}</template></el-table-column><el-table-column prop="status" label="原状态"/><el-table-column label="查看"><template #default="{row}"><el-button link @click="router.replace({query:{work_item:row.id}})">查看记录</el-button></template></el-table-column></el-table>
    <div class="actions"><el-button :disabled="!cursor" @click="cursor=null;load()">回到历史首页</el-button><el-button :disabled="!more" @click="cursor=more;load()">下一页历史</el-button></div>
    <section v-if="selected" class="record"><h2>{{ selected.title }}</h2><p class="preserve">{{ selected.description }}</p><p>{{ selected.source.label }} → {{ selected.target.label }}</p><p>原处理状态：{{ selected.status }}</p><p v-if="selected.decision_note" class="preserve">处理说明：{{ selected.decision_note }}</p><p v-for="(item,index) in selected.history" :key="index" class="preserve">{{ item.action }} · {{ item.at }}</p><p v-for="(item,index) in selected.evidence" :key="index"><a v-if="safeUrl(item.url)" :href="safeUrl(item.url)" target="_blank" rel="noopener noreferrer">{{ item.name||'原附件' }}</a><span v-else>{{ item.name||item.type||'来源记录' }}</span></p><el-button v-if="selected.item_type==='memory_share'&&selected.allowed_actions.includes('cancel')" @click="cancel">撤回旧共享申请</el-button></section>
    <details @toggle="($event.target as HTMLDetailsElement).open&&history()"><summary>查看旧协作会话</summary><el-alert v-if="threadError" :title="threadError" type="warning" :closable="false"/><el-button v-for="thread in threads" :key="thread.id" @click="showThread(thread.id)">{{ thread.title||'旧会话' }}</el-button><article v-for="message in messages" :key="message.id"><p class="preserve">{{ message.content }}</p><a v-for="attachment in message.attachments" :key="attachment.id" :href="safeUrl(attachment.url)" target="_blank" rel="noopener noreferrer">{{ attachment.file_name }}</a></article></details>
  </main>
</template>
<style scoped>.legacy-collaboration{display:grid;gap:18px;max-width:1100px;margin:auto;padding:20px;min-width:0;overflow-wrap:anywhere;}header,.actions{display:flex;gap:12px;justify-content:space-between;flex-wrap:wrap;align-items:center;}h1{font-size:24px;margin:0;}.record{border:1px solid var(--el-border-color);padding:18px;border-radius:8px;}.preserve{white-space:pre-wrap;line-height:1.8;}summary{cursor:pointer;padding:14px 0;}</style>
