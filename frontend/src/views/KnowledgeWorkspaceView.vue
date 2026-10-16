<script setup lang="ts">
import {onMounted,ref} from 'vue';
import {useRouter} from 'vue-router';
import RagSpaceView from './RagSpaceView.vue';
import KnowledgeGovernancePanel from '@/components/business/KnowledgeGovernancePanel.vue';
import {inspectionStandardApi} from '@/api/inspection-standard.api';
import type {InspectionStandardLibraryItem} from '@/types/governance.types';
import {useAuthStore} from '@/stores/auth.store';
const auth=useAuthStore();
const router=useRouter();const tab=ref('mine');const standards=ref<InspectionStandardLibraryItem[]>([]);
onMounted(async()=>{if(auth.hasPermission('inspection_standard_library_read'))standards.value=(await inspectionStandardApi.list()).data.data.items;});
</script>
<template><div class="knowledge-workspace"><header><h1>知识资料</h1><p>标准提供权威依据，资料提供参考与证据，经过核对的知识按范围复用。</p></header><el-tabs v-model="tab"><el-tab-pane label="公共标准" name="standards"><el-alert title="标准只维护一份；正式引用使用已核验、已发布的具体修订。" type="info" :closable="false"/><el-table :data="standards"><el-table-column prop="name" label="标准专题"/><el-table-column label="发布 / 待核验"><template #default="{row}">{{ row.published_document_count || 0 }} 已发布 / {{ row.pending_review_document_count || 0 }} 待核验</template></el-table-column><el-table-column label="操作"><template #default="{row}"><el-button link type="primary" @click="router.push({path:'/governance/admin/inspection-standards',query:{library:row.id}})">查看标准与出处</el-button></template></el-table-column></el-table></el-tab-pane><el-tab-pane label="已确认知识" name="published" lazy><KnowledgeGovernancePanel v-if="tab==='published'" readonly/></el-tab-pane><el-tab-pane label="授权共享资料" name="shared" lazy><RagSpaceView v-if="tab==='shared'" scope-filter="shared"/></el-tab-pane><el-tab-pane label="我的资料" name="mine" lazy><RagSpaceView v-if="tab==='mine'" scope-filter="mine"/></el-tab-pane><el-tab-pane label="知识候选与申请" name="candidates" lazy><KnowledgeGovernancePanel v-if="tab==='candidates'"/></el-tab-pane></el-tabs></div></template>
<style scoped>.knowledge-workspace{display:flex;flex-direction:column;gap:16px}.knowledge-workspace>header{border-bottom:2px solid var(--el-color-primary);padding-bottom:18px}.knowledge-workspace h1{font-size:25px;margin:0}.knowledge-workspace>header p{color:var(--el-text-color-secondary);font-size:14px;margin:10px 0 0}</style>
