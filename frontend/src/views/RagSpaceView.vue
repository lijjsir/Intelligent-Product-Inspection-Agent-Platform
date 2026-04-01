<script setup lang="ts">
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { CollectionTag, DocumentAdd } from "@element-plus/icons-vue";
import { useChatStore } from "@/stores/chat.store";

const chatStore = useChatStore();

const ragDocumentInputRef = ref<HTMLInputElement | null>(null);
const ragCreating = ref(false);
const ragForm = ref({
  name: "",
  description: "",
});
const ragFiles = ref<File[]>([]);

const resolveErrorMessage = (error: unknown, fallback: string) => {
  if (typeof error === "object" && error !== null) {
    const candidate = error as {
      response?: {
        data?: {
          message?: string;
        };
      };
      message?: string;
    };
    return candidate.response?.data?.message || candidate.message || fallback;
  }
  return fallback;
};

const triggerRagDocumentSelect = () => {
  ragDocumentInputRef.value?.click();
};

const handleRagFilesSelected = (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  ragFiles.value = Array.from(inputElement.files || []);
  inputElement.value = "";
};

const submitRagSpace = async () => {
  if (!ragForm.value.name.trim()) {
    ElMessage.warning("请先填写 RAG 空间名称");
    return;
  }
  ragCreating.value = true;
  try {
    const created = await chatStore.createRagSpace(
      {
        name: ragForm.value.name.trim(),
        description: ragForm.value.description.trim(),
      },
      ragFiles.value,
    );
    ragForm.value = { name: "", description: "" };
    ragFiles.value = [];
    if (created?.id) {
      chatStore.selectRagSpace(created.id);
    }
    ElMessage.success("RAG 空间创建成功");
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "RAG 空间创建失败，请稍后重试"));
    console.error(error);
  } finally {
    ragCreating.value = false;
  }
};

onMounted(async () => {
  try {
    await chatStore.fetchRagSpaces();
  } catch {
    // The page will render a dedicated warning banner from store state.
  }
});
</script>

<template>
  <div class="rag-page">
    <el-card shadow="never" class="rag-card">
      <template #header>
        <div class="rag-header">
          <div>
            <div class="card-title">RAG 空间</div>
            <div class="card-subtitle">管理聊天检索用的私有知识空间，并选择当前默认使用的空间。</div>
          </div>
          <el-tag v-if="chatStore.selectedRagSpace" type="success" effect="plain">
            当前使用：{{ chatStore.selectedRagSpace.name }}
          </el-tag>
        </div>
      </template>

      <div class="rag-layout">
        <div class="rag-create">
          <el-alert
            v-if="chatStore.ragSpacesError"
            class="rag-alert"
            type="warning"
            :closable="false"
            show-icon
            :title="chatStore.ragSpacesError"
            description="RAG 管理页依赖 MySQL 中的空间元数据表；文档向量和分块仍会继续写入 Qdrant。"
          />
          <el-form label-position="top">
            <el-form-item label="名称">
              <el-input v-model="ragForm.name" maxlength="120" placeholder="例如：注塑外观标准库" />
            </el-form-item>

            <el-form-item label="描述">
              <el-input
                v-model="ragForm.description"
                type="textarea"
                :rows="4"
                maxlength="1000"
                placeholder="描述这个 RAG 空间主要包含哪些标准、工艺文档或知识。"
              />
            </el-form-item>

            <el-form-item label="文档">
              <input
                ref="ragDocumentInputRef"
                type="file"
                multiple
                accept=".pdf,.txt,.md,.jsonl"
                class="hidden-input"
                @change="handleRagFilesSelected"
              />
              <el-button plain :icon="DocumentAdd" @click="triggerRagDocumentSelect">选择文档</el-button>
              <div v-if="ragFiles.length" class="chip-row top-gap">
                <el-tag v-for="file in ragFiles" :key="file.name" size="small" effect="plain">{{ file.name }}</el-tag>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="ragCreating" @click="submitRagSpace">提交</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="rag-list">
          <el-empty v-if="chatStore.ragSpaces.length === 0 && !chatStore.ragSpacesError" description="还没有 RAG 空间" />
          <div v-else-if="chatStore.ragSpaces.length > 0" class="rag-space-list">
            <div
              v-for="space in chatStore.ragSpaces"
              :key="space.id"
              class="rag-space-item"
              :class="{ active: chatStore.selectedRagSpaceId === space.id }"
            >
              <div class="rag-space-top">
                <div class="rag-space-copy">
                  <div class="rag-space-name">{{ space.name }}</div>
                  <div class="rag-space-desc">{{ space.description || "暂无描述" }}</div>
                </div>
                <el-button
                  size="small"
                  :type="chatStore.selectedRagSpaceId === space.id ? 'success' : 'primary'"
                  plain
                  @click="chatStore.selectRagSpace(space.id)"
                >
                  {{ chatStore.selectedRagSpaceId === space.id ? "使用中" : "使用" }}
                </el-button>
              </div>

              <div class="rag-space-meta">
                <el-tag size="small" effect="plain" :icon="CollectionTag">文档数：{{ space.file_count }}</el-tag>
                <el-tag size="small" effect="plain">启用次数：{{ space.selected_count }}</el-tag>
              </div>

              <div v-if="space.files?.length" class="chip-row">
                <el-tag v-for="file in space.files" :key="file.id" size="small" effect="plain">{{ file.file_name }}</el-tag>
              </div>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.rag-page {
  display: grid;
  width: 100%;
}

.rag-card :deep(.el-card__body) {
  display: grid;
  gap: 18px;
}

.rag-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.card-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f766e;
}

.card-subtitle,
.rag-space-desc {
  font-size: 12px;
  color: #475569;
  line-height: 1.6;
}

.rag-layout {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 16px;
}

.rag-alert {
  margin-bottom: 16px;
}

.rag-space-list {
  display: grid;
  gap: 12px;
}

.rag-space-item {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #fff;
}

.rag-space-item.active {
  border-color: #10b981;
  box-shadow: 0 10px 22px rgba(16, 185, 129, 0.12);
}

.rag-space-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.rag-space-copy,
.rag-list {
  display: grid;
  gap: 8px;
}

.rag-space-name {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.rag-space-meta,
.chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.top-gap {
  margin-top: 10px;
}

.hidden-input {
  display: none;
}

@media (max-width: 960px) {
  .rag-header,
  .rag-layout,
  .rag-space-top {
    grid-template-columns: 1fr;
    flex-direction: column;
  }
}
</style>
