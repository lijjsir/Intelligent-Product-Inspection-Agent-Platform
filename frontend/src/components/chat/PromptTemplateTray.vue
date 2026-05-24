<script setup lang="ts">
import { ArrowDown, Close, CollectionTag, Delete, Edit, Plus } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from "element-plus";
import { computed, onMounted, reactive, ref } from "vue";

import { CAPABILITY_CUSTOM_PROMPT } from "@/constants/roles";
import { usePermission } from "@/composables/usePermission";
import {
  type PromptTemplate,
  type PromptTemplateDraft,
  usePromptTemplateStore,
} from "@/stores/prompt-template.store";

const props = defineProps<{
  modelValue: string;
}>();

const emit = defineEmits<{
  (e: "update:modelValue", value: string): void;
}>();

const store = usePromptTemplateStore();
const { hasCapability } = usePermission();

const manageVisible = ref(false);
const saving = ref(false);
const templateFormRef = ref<FormInstance>();
const editingTemplateId = ref("");

const templateForm = reactive<PromptTemplateDraft>({
  name: "",
  description: "",
  content: "",
});

const canManageTemplates = computed(() => hasCapability(CAPABILITY_CUSTOM_PROMPT));
const activeTemplate = computed(() => store.activeTemplate);
const customTemplates = computed(() => store.customTemplates);
const allTemplates = computed(() => store.allTemplates);

const templateRules: FormRules = {
  name: [{ required: true, message: "请输入模板名称", trigger: "blur" }],
  content: [{ required: true, message: "请输入模板内容", trigger: "blur" }],
};

function formatTime(value?: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function resetEditor() {
  editingTemplateId.value = "";
  templateForm.name = "";
  templateForm.description = "";
  templateForm.content = "";
  templateFormRef.value?.clearValidate();
}

function startCreateTemplate() {
  resetEditor();
}

function startEditTemplate(template: PromptTemplate) {
  editingTemplateId.value = template.id;
  templateForm.name = template.name;
  templateForm.description = template.description || "";
  templateForm.content = template.content;
  templateFormRef.value?.clearValidate();
}

function openManageDialog() {
  if (!canManageTemplates.value) return;
  manageVisible.value = true;
  resetEditor();
}

function applyTemplate(template: PromptTemplate) {
  const templateContent = template.content.trim();
  const currentValue = props.modelValue;
  const currentText = currentValue.trim();
  const active = activeTemplate.value;
  let next = templateContent;

  if (currentText) {
    if (active && currentText.startsWith(active.content.trim())) {
      const tail = currentText.slice(active.content.trim().length).trimStart();
      next = tail ? `${templateContent}\n\n${tail}` : templateContent;
    } else {
      next = `${templateContent}\n\n${currentText}`;
    }
  }

  emit("update:modelValue", next);
  store.selectTemplate(template.id);
}

function handleCommand(command: string) {
  if (command === "__manage__") {
    openManageDialog();
    return;
  }
  const template = allTemplates.value.find((item) => item.id === command);
  if (template) {
    applyTemplate(template);
  }
}

async function saveTemplate() {
  if (!templateFormRef.value) return;
  const valid = await templateFormRef.value.validate().catch(() => false);
  if (!valid) return;

  saving.value = true;
  try {
    if (editingTemplateId.value) {
      const updated = store.updateTemplate(editingTemplateId.value, templateForm);
      if (!updated) {
        ElMessage.error("模板不存在或已被删除");
        return;
      }
      ElMessage.success("模板已更新");
      startEditTemplate(updated);
      return;
    }

    const created = store.createTemplate(templateForm);
    ElMessage.success("模板已创建");
    startEditTemplate(created);
  } finally {
    saving.value = false;
  }
}

async function removeTemplate(template: PromptTemplate) {
  try {
    await ElMessageBox.confirm(`确定要删除模板「${template.name}」吗？`, "删除模板", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  if (activeTemplate.value?.id === template.id) {
    removeTemplateFromInput(template);
  }
  store.deleteTemplate(template.id);
  if (editingTemplateId.value === template.id) {
    resetEditor();
  }
  ElMessage.success("模板已删除");
}

function clearSelection() {
  const active = activeTemplate.value;
  if (active) {
    removeTemplateFromInput(active);
  }
  store.clearSelection();
}

function removeTemplateFromInput(template: PromptTemplate) {
  const prefix = template.content.trim();
  const currentText = props.modelValue.trim();
  if (!currentText.startsWith(prefix)) return;
  const next = currentText.slice(prefix.length).trimStart();
  emit("update:modelValue", next);
}

onMounted(() => {
  store.loadTemplates();
});
</script>

<template>
  <div class="prompt-template-tray">
    <el-dropdown trigger="click" @command="handleCommand">
      <el-button size="small" :icon="CollectionTag">
        模板
        <el-icon class="el-icon--right"><ArrowDown /></el-icon>
      </el-button>
      <template #dropdown>
        <el-dropdown-menu class="template-dropdown-menu">
          <el-dropdown-item
            v-for="template in allTemplates"
            :key="template.id"
            :command="template.id"
            class="template-dropdown-item"
          >
            <div class="template-dropdown-row">
              <div class="template-dropdown-main">
                <span class="template-dropdown-name">{{ template.name }}</span>
                <span class="template-dropdown-desc">{{ template.description }}</span>
              </div>
              <el-tag size="small" effect="plain">{{ template.is_builtin ? "内置" : "自定义" }}</el-tag>
            </div>
          </el-dropdown-item>
          <el-dropdown-item v-if="canManageTemplates" divided command="__manage__">
            管理模板
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <el-tooltip v-if="canManageTemplates" content="管理模板" placement="top">
      <el-button size="small" :icon="Edit" @click="openManageDialog" />
    </el-tooltip>

    <el-tooltip v-if="activeTemplate" content="清除当前模板" placement="top">
      <el-tag
        closable
        effect="plain"
        size="small"
        class="template-active-tag"
        @close="clearSelection"
      >
        {{ activeTemplate.name }}
      </el-tag>
    </el-tooltip>

    <el-dialog
      v-model="manageVisible"
      title="模板管理"
      width="860px"
      destroy-on-close
      @closed="resetEditor"
    >
      <div class="template-manager">
        <div class="template-manager-head">
          <div class="template-manager-actions">
            <el-button size="small" type="primary" :icon="Plus" @click="startCreateTemplate">
              新建模板
            </el-button>
            <el-button size="small" :icon="Close" @click="clearSelection">
              清除选择
            </el-button>
          </div>
          <el-tag size="small" effect="plain">{{ customTemplates.length }} 个自定义模板</el-tag>
        </div>

        <el-table :data="customTemplates" height="220" stripe>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
          <el-table-column label="更新时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" :icon="Edit" @click="startEditTemplate(row)" />
              <el-button text size="small" :icon="Delete" @click="removeTemplate(row)" />
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无自定义模板" :image-size="72" />
          </template>
        </el-table>

        <el-divider content-position="left">模板编辑</el-divider>

        <el-form
          ref="templateFormRef"
          :model="templateForm"
          :rules="templateRules"
          label-position="top"
          size="small"
        >
          <el-form-item label="模板名称" prop="name">
            <el-input v-model="templateForm.name" placeholder="例如：专家复核" />
          </el-form-item>
          <el-form-item label="模板说明">
            <el-input v-model="templateForm.description" placeholder="用于快速识别用途" />
          </el-form-item>
          <el-form-item label="模板内容" prop="content">
            <el-input
              v-model="templateForm.content"
              type="textarea"
              :rows="10"
              resize="vertical"
              placeholder="请输入要插入的提示词内容"
            />
          </el-form-item>
          <div class="template-editor-actions">
            <el-button @click="resetEditor">重置</el-button>
            <el-button type="primary" :loading="saving" @click="saveTemplate">
              {{ editingTemplateId ? "保存修改" : "保存模板" }}
            </el-button>
          </div>
        </el-form>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.prompt-template-tray {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.prompt-template-tray :deep(.el-button) {
  flex-shrink: 0;
}

.template-active-tag {
  max-width: 240px;
}

.template-active-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-dropdown-menu {
  min-width: 360px;
}

.template-dropdown-item {
  padding: 0;
}

.template-dropdown-row {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
}

.template-dropdown-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.template-dropdown-name {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
}

.template-dropdown-desc {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.4;
}

.template-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-manager-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.template-manager-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.template-editor-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}
</style>
