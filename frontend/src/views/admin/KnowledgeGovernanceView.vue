<script setup lang="ts">
import {ref} from 'vue';
import KnowledgeGovernancePanel from '@/components/business/KnowledgeGovernancePanel.vue';
import MemoryGovernanceView from './MemoryGovernanceView.vue';
const tab=ref('admission');
</script>
<template><section class="knowledge-governance"><header><p class="eyebrow">知识治理 / 隔离与发布</p><h2>知识准入与发布</h2><p>标准文档、专家资料和普通知识分开管理；未核验文件不会进入正式标准检索或全局 RAG。</p></header><el-alert type="warning" :closable="false" title="上传文件先进入隔离区；经过来源、权限和专业内容核验后，才按指定范围发布。标准库发布不等于专家知识发布。"/><el-tabs v-model="tab"><el-tab-pane label="准入、范围与发布" name="admission"><KnowledgeGovernancePanel/></el-tab-pane><el-tab-pane label="已确认知识" name="published" lazy><KnowledgeGovernancePanel v-if="tab==='published'" readonly/></el-tab-pane><el-tab-pane label="历史记忆治理（兼容）" name="legacy" lazy><el-alert type="info" :closable="false" title="这里仅维护旧组织记忆、事件传播和回滚记录，不等同于标准库，也不参与正式标准判定。历史服务不可用时不会影响标准准入和专家 RAG。"/><MemoryGovernanceView v-if="tab==='legacy'"/></el-tab-pane></el-tabs></section></template>
<style scoped>.knowledge-governance{display:flex;flex-direction:column;gap:16px}.knowledge-governance header{padding-bottom:14px;border-bottom:2px solid var(--el-color-primary)}.knowledge-governance h2{margin:4px 0;font-size:24px}.knowledge-governance p{margin:5px 0;color:var(--el-text-color-secondary)}.eyebrow{font-size:12px;letter-spacing:1px;color:var(--el-color-primary)}</style>
