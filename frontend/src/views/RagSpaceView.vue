<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { CollectionTag, DocumentAdd } from "@element-plus/icons-vue";
import { ragSpaceApi } from "@/api/rag-space.api";
import { useChatStore } from "@/stores/chat.store";
import type { RagSpaceFile } from "@/types/rag-space.types";

const chatStore = useChatStore();

const ragDocumentInputRef = ref<HTMLInputElement | null>(null);
const ragCreating = ref(false);
const ragFiles = ref<File[]>([]);
const documentLoading = ref(false);
const deletingDocumentId = ref("");
const documentError = ref("");
const activeDocuments = ref<RagSpaceFile[]>([]);
const ragForm = ref({
  name: "",
  description: "",
});

const currentUsageLabel = computed(() => chatStore.selectedRagSpace?.name || "不使用文档");
const documentPanelSubtitle = computed(() => {
  if (!chatStore.selectedRagSpace) {
    return "当前默认不使用文档，聊天时不会附带任何 RAG 空间。";
  }
  return `${chatStore.selectedRagSpace.name} 中的数据库文档记录`;
});

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

const formatTime = (value?: string | null) => {
  if (!value) return "未知时间";
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatFileSize = (value?: number) => {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
};

const triggerRagDocumentSelect = () => {
  ragDocumentInputRef.value?.click();
};

const handleRagFilesSelected = (event: Event) => {
  const inputElement = event.target as HTMLInputElement;
  ragFiles.value = Array.from(inputElement.files || []).slice(0, 1);
  inputElement.value = "";
};

const chooseNoDocument = () => {
  chatStore.clearSelectedRagSpace();
};

const chooseRagSpace = (spaceId: string) => {
  chatStore.selectRagSpace(spaceId);
};

const loadDocuments = async (ragSpaceId: string) => {
  if (!ragSpaceId) {
    activeDocuments.value = [];
    documentError.value = "";
    documentLoading.value = false;
    return;
  }
  documentLoading.value = true;
  documentError.value = "";
  try {
    const { data } = await ragSpaceApi.listDocuments(ragSpaceId, 5000);
    if (chatStore.selectedRagSpaceId !== ragSpaceId) return;
    activeDocuments.value = data.data;
  } catch (error) {
    if (chatStore.selectedRagSpaceId !== ragSpaceId) return;
    activeDocuments.value = [];
    documentError.value = resolveErrorMessage(error, "文档列表加载失败，请稍后重试");
  } finally {
    if (chatStore.selectedRagSpaceId === ragSpaceId) {
      documentLoading.value = false;
    }
  }
};

const deleteDocument = async (file: RagSpaceFile) => {
  if (!chatStore.selectedRagSpaceId) return;
  deletingDocumentId.value = file.id;
  try {
    await ragSpaceApi.deleteDocument(chatStore.selectedRagSpaceId, file.id);
    activeDocuments.value = activeDocuments.value.filter((item) => item.id !== file.id);
    await chatStore.fetchRagSpaces();
    ElMessage.success("文档已删除");
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "文档删除失败，请稍后重试"));
  } finally {
    deletingDocumentId.value = "";
  }
};

const submitRagSpace = async () => {
  if (!ragForm.value.name.trim()) {
    ElMessage.warning("请先填写 RAG 空间名称");
    return;
  }
  if (ragFiles.value.length === 0) {
    ElMessage.warning("请先选择文档。一个文档会创建成一个独立空间。");
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

watch(
  () => chatStore.selectedRagSpaceId,
  (ragSpaceId) => {
    if (!ragSpaceId) {
      activeDocuments.value = [];
      documentError.value = "";
      documentLoading.value = false;
      return;
    }
    loadDocuments(ragSpaceId).catch(() => undefined);
  },
  { immediate: true },
);

onMounted(async () => {
  try {
    await chatStore.fetchRagSpaces();
  } catch {
    // The page renders store-level and local error states.
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
          <el-tag :type="chatStore.selectedRagSpace ? 'success' : 'info'" effect="plain">
            当前使用：{{ currentUsageLabel }}
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
                accept=".pdf,.txt,.md,.jsonl"
                class="hidden-input"
                @change="handleRagFilesSelected"
              />
              <el-button plain :icon="DocumentAdd" @click="triggerRagDocumentSelect">选择文档</el-button>
              <div class="top-gap hint-text">一个文档会创建成一个独立空间；删除文档时会同时移除空空间。</div>
              <div v-if="ragFiles.length" class="chip-row top-gap">
                <el-tag v-for="file in ragFiles" :key="file.name" size="small" effect="plain">{{ file.name }}</el-tag>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button type="primary" :loading="ragCreating" @click="submitRagSpace">提交</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="rag-browser">
          <section class="rag-panel rag-space-panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">空间列表</div>
                <div class="panel-subtitle">选择聊天默认使用的知识空间，或切回不使用文档。</div>
              </div>
              <el-tag size="small" effect="plain">共 {{ chatStore.ragSpaces.length }} 个空间</el-tag>
            </div>

            <div class="rag-space-list">
              <button class="rag-space-item no-doc-item" :class="{ active: !chatStore.selectedRagSpaceId }" @click="chooseNoDocument">
                <div class="rag-space-top">
                  <div class="rag-space-copy">
                    <div class="rag-space-name">不使用文档</div>
                    <div class="rag-space-desc">聊天时不附带任何 RAG 空间，适合普通问答或纯对话场景。</div>
                  </div>
                  <el-tag :type="chatStore.selectedRagSpaceId ? 'info' : 'success'" effect="plain" size="small">
                    {{ chatStore.selectedRagSpaceId ? "设为默认" : "当前默认" }}
                  </el-tag>
                </div>
              </button>

              <el-empty v-if="chatStore.ragSpaces.length === 0 && !chatStore.ragSpacesError" description="还没有 RAG 空间" />

              <button
                v-for="space in chatStore.ragSpaces"
                :key="space.id"
                class="rag-space-item"
                :class="{ active: chatStore.selectedRagSpaceId === space.id }"
                @click="chooseRagSpace(space.id)"
              >
                <div class="rag-space-top">
                  <div class="rag-space-copy">
                    <div class="rag-space-name">{{ space.name }}</div>
                    <div class="rag-space-desc">{{ space.description || "暂无描述" }}</div>
                  </div>
                  <el-tag :type="chatStore.selectedRagSpaceId === space.id ? 'success' : 'primary'" effect="plain" size="small">
                    {{ chatStore.selectedRagSpaceId === space.id ? "使用中" : "点击使用" }}
                  </el-tag>
                </div>

                <div class="rag-space-meta">
                  <el-tag size="small" effect="plain" :icon="CollectionTag">文档数：{{ space.file_count }}</el-tag>
                  <el-tag size="small" effect="plain">启用次数：{{ space.selected_count }}</el-tag>
                </div>
              </button>
            </div>
          </section>

          <section class="rag-panel rag-documents-panel">
            <div class="panel-header">
              <div>
                <div class="panel-title">文档列表</div>
                <div class="panel-subtitle">{{ documentPanelSubtitle }}</div>
              </div>
              <el-tag :type="chatStore.selectedRagSpace ? 'success' : 'info'" effect="plain">
                {{ chatStore.selectedRagSpace ? `${activeDocuments.length} 份文档` : "默认关闭" }}
              </el-tag>
            </div>

            <el-alert
              v-if="documentError"
              type="warning"
              :closable="false"
              show-icon
              :title="documentError"
            />

            <div v-else-if="documentLoading" class="document-loading">正在加载文档列表...</div>

            <el-empty v-else-if="!chatStore.selectedRagSpaceId" description="当前默认不使用文档" />

            <el-empty v-else-if="activeDocuments.length === 0" description="该空间还没有文档" />

            <div v-else class="rag-document-list">
              <div v-for="file in activeDocuments" :key="file.id" class="rag-document-row">
                <div class="rag-document-main">
                  <div class="rag-document-name">{{ file.file_name }}</div>
                  <div class="rag-document-subtitle">{{ formatTime(file.created_at) }}</div>
                </div>

                <div class="rag-document-meta">
                  <el-tag size="small" effect="plain">{{ file.status }}</el-tag>
                  <span>{{ formatFileSize(file.size_bytes) }}</span>
                  <el-button
                    link
                    type="danger"
                    :loading="deletingDocumentId === file.id"
                    @click="deleteDocument(file)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>
          </section>
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

.card-title,
.panel-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f766e;
}

.card-subtitle,
.panel-subtitle,
.rag-space-desc,
.rag-document-subtitle,
.hint-text {
  font-size: 12px;
  color: #475569;
  line-height: 1.6;
}

.rag-layout {
  display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 16px;
}

.rag-create,
.rag-browser,
.rag-panel,
.rag-space-copy,
.rag-space-list,
.rag-document-main {
  display: grid;
  gap: 10px;
}

.rag-browser {
  grid-template-rows: minmax(220px, 1fr) minmax(260px, 1fr);
}

.rag-panel {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid #cbe9dc;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(241, 250, 245, 0.94)),
    radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 35%);
  min-height: 0;
}

.panel-header,
.rag-space-top,
.rag-space-meta,
.rag-document-row,
.rag-document-meta,
.chip-row {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.rag-space-meta,
.rag-document-meta,
.chip-row {
  justify-content: flex-start;
  flex-wrap: wrap;
}

.rag-space-list,
.rag-document-list {
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.rag-space-list {
  gap: 12px;
}

.rag-space-item {
  width: 100%;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #fff;
  cursor: pointer;
  text-align: left;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.rag-space-item:hover {
  border-color: #7dd3a6;
  box-shadow: 0 10px 20px rgba(15, 23, 42, 0.06);
  transform: translateY(-1px);
}

.rag-space-item.active {
  border-color: #10b981;
  box-shadow: 0 12px 24px rgba(16, 185, 129, 0.14);
}

.no-doc-item {
  border-style: dashed;
  background: #f8fafc;
}

.rag-space-name,
.rag-document-name {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.rag-document-list {
  display: grid;
  gap: 10px;
}

.rag-document-row {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid #dbe7f0;
  background: rgba(255, 255, 255, 0.92);
}

.document-loading {
  padding: 18px 0;
  color: #64748b;
  font-size: 13px;
}

.rag-alert {
  margin-bottom: 16px;
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
  .panel-header,
  .rag-space-top,
  .rag-document-row {
    flex-direction: column;
    align-items: stretch;
  }

  .rag-layout {
    grid-template-columns: 1fr;
  }

  .rag-browser {
    grid-template-rows: auto auto;
  }
}
</style>
