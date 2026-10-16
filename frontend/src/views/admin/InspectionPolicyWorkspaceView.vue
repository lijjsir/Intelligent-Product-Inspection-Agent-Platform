<script setup lang="ts">
import {ref} from 'vue';
import InspectionPolicyPanel from '@/components/business/InspectionPolicyPanel.vue';
import InspectionSpecView from './InspectionSpecView.vue';
const tab=ref('policy');
</script>
<template><section class="policy-workspace"><header><div><p class="eyebrow">执行控制 / 版本化策略</p><h2>检测执行策略</h2><p>标准要求总览负责检测项目和限值；本页负责输入完整性、AI辅助采信、专业复核和缺陷预警。</p></div></header><el-alert type="info" :closable="false" title="历史质检门槛仅作为兼容数据保留，不再作为标准限值来源；正式策略必须查看完整内容、变更和影响范围后发布。"/><el-tabs v-model="tab"><el-tab-pane label="输入与复核策略" name="policy"><InspectionPolicyPanel/></el-tab-pane><el-tab-pane label="历史兼容配置（只读）" name="legacy" lazy><InspectionSpecView v-if="tab==='legacy'" compatibility-readonly/></el-tab-pane></el-tabs></section></template>
<style scoped>.policy-workspace{display:flex;flex-direction:column;gap:16px}.policy-workspace header{padding-bottom:14px;border-bottom:2px solid var(--el-color-primary)}.policy-workspace h2{margin:4px 0;font-size:24px}.policy-workspace p{margin:5px 0;color:var(--el-text-color-secondary)}.eyebrow{font-size:12px;letter-spacing:1px;color:var(--el-color-primary)}</style>
