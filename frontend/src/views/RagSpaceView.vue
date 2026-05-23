<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute } from "vue-router";
import {
  Delete,
  Document,
  EditPen,
  Folder,
  FolderOpened,
  Plus,
  Refresh,
  UploadFilled,
} from "@element-plus/icons-vue";

import { ragSpaceApi } from "@/api/rag-space.api";
import { useChatStore } from "@/stores/chat.store";
import type { RagNode } from "@/types/rag-space.types";

const route = useRoute();
const chatStore = useChatStore();

const treeLoading = ref(false);
const uploadLoading = ref(false);
const treeError = ref("");
const treeData = ref<RagNode[]>([]);
const expandedKeys = ref<string[]>([]);
const currentNodeId = ref("");
const hiddenUploadInput = ref<HTMLInputElement | null>(null);
const uploadTargetNodeId = ref<string | null>(null);

const spaceDialogVisible = ref(false);
const spaceDialogMode = ref<"create" | "edit">("create");
const spaceDialogLoading = ref(false);
const spaceForm = ref({
  name: "",
  description: "",
});

const folderDialogVisible = ref(false);
const folderDialogLoading = ref(false);
const folderForm = ref({
  parent_id: null as string | null,
  name: "",
});

const nodeDialogVisible = ref(false);
const nodeDialogLoading = ref(false);
const nodeForm = ref({
  node_id: "",
  parent_id: null as string | null,
  name: "",
});

const selectedSpace = computed(() => chatStore.selectedRagSpace || null);

const flattenNodes = (nodes: RagNode[]): RagNode[] =>
  nodes.flatMap((node) => [node, ...flattenNodes(node.children || [])]);

const flatNodes = computed(() => flattenNodes(treeData.value));

const nodeMap = computed(() => {
  const map = new Map<string, RagNode>();
  for (const node of flatNodes.value) {
    map.set(node.id, node);
  }
  return map;
});

const selectedNode = computed(() => (currentNodeId.value ? nodeMap.value.get(currentNodeId.value) || null : null));

const selectedFolder = computed(() => {
  const node = selectedNode.value;
  if (!node) return null;
  if (node.node_type === "folder") return node;
  if (!node.parent_id) return null;
  return nodeMap.value.get(node.parent_id) || null;
});

const stats = computed(() => ({
  folderCount: selectedSpace.value?.folder_count ?? 0,
  fileCount: selectedSpace.value?.file_count ?? 0,
  chunkCount: selectedSpace.value?.chunk_count ?? 0,
  indexStatus: selectedSpace.value?.index_status ?? "ready",
}));

const currentFolderLabel = computed(() => selectedFolder.value?.full_path || "根目录");

const folderOptions = computed(() =>
  flatNodes.value
    .filter((node) => node.node_type === "folder")
    .map((node) => ({
      label: node.full_path,
      value: node.id,
    })),
);

const moveTargetOptions = computed(() => {
  const target = nodeForm.value.node_id ? nodeMap.value.get(nodeForm.value.node_id) || null : null;
  if (!target || target.node_type !== "folder") return folderOptions.value;
  const excludedIds = new Set(flattenNodes([target]).map((node) => node.id));
  return folderOptions.value.filter((option) => !excludedIds.has(option.value));
});

const detailRows = computed(() => {
  if (selectedNode.value) {
    const node = selectedNode.value;
    if (node.node_type === "folder") {
      return [
        { label: "节点类型", value: "文件夹" },
        { label: "子节点数", value: String(node.children_count || 0) },
        { label: "路径", value: node.full_path },
        { label: "更新时间", value: formatTime(node.updated_at) },
      ];
    }
    return [
      { label: "节点类型", value: "文件" },
      { label: "路径", value: node.full_path },
      { label: "文件大小", value: formatFileSize(node.document?.size_bytes) },
      { label: "索引状态", value: node.document?.index_status || node.status || "ready" },
      { label: "解析状态", value: node.document?.parse_status || "parsed" },
      { label: "Chunk 数", value: String(node.document?.chunk_count ?? 0) },
      { label: "对象键", value: node.document?.object_key || "-" },
      { label: "更新时间", value: formatTime(node.updated_at) },
    ];
  }

  if (selectedSpace.value) {
    return [
      { label: "空间名称", value: selectedSpace.value.name },
      { label: "文件夹总数", value: String(stats.value.folderCount) },
      { label: "文件总数", value: String(stats.value.fileCount) },
      { label: "Chunk 总数", value: String(stats.value.chunkCount) },
      { label: "索引状态", value: stats.value.indexStatus },
      { label: "更新时间", value: formatTime(selectedSpace.value.updated_at) },
    ];
  }

  return [];
});

const detailTitle = computed(() => selectedNode.value?.name || selectedSpace.value?.name || "未选择节点");
const detailTag = computed(() => {
  if (selectedNode.value?.node_type === "folder") return "文件夹";
  if (selectedNode.value?.node_type === "file") return "文件";
  return "空间";
});

const spaceDialogTitle = computed(() => (spaceDialogMode.value === "create" ? "新建空间" : "编辑空间"));

function resolveErrorMessage(error: unknown, fallback: string) {
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
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatFileSize(value?: number | null) {
  const size = Number(value || 0);
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function statusTagType(status?: string | null) {
  switch (status) {
    case "ready":
    case "parsed":
      return "success";
    case "indexing":
    case "pending":
    case "parsing":
      return "warning";
    case "failed":
      return "danger";
    default:
      return "info";
  }
}

function resolveNodeIcon(node: RagNode) {
  if (node.node_type === "file") return Document;
  return expandedKeys.value.includes(node.id) ? FolderOpened : Folder;
}

async function ensureSelectedSpace() {
  await chatStore.fetchRagSpaces();
  const requestedSpaceId = String(route.query.spaceId || "").trim();
  if (requestedSpaceId && chatStore.ragSpaces.some((item) => item.id === requestedSpaceId)) {
    if (chatStore.selectedRagSpaceId !== requestedSpaceId) {
      chatStore.selectRagSpace(requestedSpaceId);
    }
    return;
  }
  if (!chatStore.selectedRagSpaceId && chatStore.ragSpaces.length > 0) {
    chatStore.selectRagSpace(chatStore.ragSpaces[0].id);
  }
}

async function loadTree(spaceId: string) {
  if (!spaceId) {
    treeData.value = [];
    treeError.value = "";
    currentNodeId.value = "";
    expandedKeys.value = [];
    return;
  }

  treeLoading.value = true;
  treeError.value = "";

  try {
    const { data } = await ragSpaceApi.getTree(spaceId);
    if (chatStore.selectedRagSpaceId !== spaceId) return;
    treeData.value = data.data;
    expandedKeys.value = Array.from(
      new Set(
        flattenNodes(data.data)
          .filter((node) => node.node_type === "folder" && node.depth < 2)
          .map((node) => node.id),
      ),
    );
    if (currentNodeId.value && !flattenNodes(data.data).some((node) => node.id === currentNodeId.value)) {
      currentNodeId.value = "";
    }
  } catch (error) {
    if (chatStore.selectedRagSpaceId !== spaceId) return;
    treeData.value = [];
    currentNodeId.value = "";
    expandedKeys.value = [];
    treeError.value = resolveErrorMessage(error, "目录树加载失败，请稍后重试。");
  } finally {
    if (chatStore.selectedRagSpaceId === spaceId) {
      treeLoading.value = false;
    }
  }
}

async function refreshPage() {
  await ensureSelectedSpace();
  if (chatStore.selectedRagSpaceId) {
    await loadTree(chatStore.selectedRagSpaceId);
  }
}

function handleSpaceChange(spaceId: string) {
  chatStore.selectRagSpace(spaceId);
  currentNodeId.value = "";
}

function selectNode(node: RagNode) {
  currentNodeId.value = node.id;
}

function updateExpandedKeys(nodeId: string, expanded: boolean) {
  const next = new Set(expandedKeys.value);
  if (expanded) next.add(nodeId);
  else next.delete(nodeId);
  expandedKeys.value = Array.from(next);
}

function openCreateSpaceDialog() {
  spaceDialogMode.value = "create";
  spaceForm.value = { name: "", description: "" };
  spaceDialogVisible.value = true;
}

function openEditSpaceDialog() {
  if (!selectedSpace.value) {
    ElMessage.warning("请先选择一个 RAG 空间。");
    return;
  }
  spaceDialogMode.value = "edit";
  spaceForm.value = {
    name: selectedSpace.value.name,
    description: selectedSpace.value.description || "",
  };
  spaceDialogVisible.value = true;
}

async function submitSpaceDialog() {
  const name = spaceForm.value.name.trim();
  if (!name) {
    ElMessage.warning("请输入空间名称。");
    return;
  }

  spaceDialogLoading.value = true;
  try {
    if (spaceDialogMode.value === "create") {
      const { data } = await ragSpaceApi.create({
        name,
        description: spaceForm.value.description.trim(),
      });
      await chatStore.fetchRagSpaces();
      chatStore.selectRagSpace(data.data.id);
      currentNodeId.value = "";
      await loadTree(data.data.id);
      ElMessage.success("空间已创建。");
    } else if (selectedSpace.value) {
      const { data } = await ragSpaceApi.updateSpace(selectedSpace.value.id, {
        name,
        description: spaceForm.value.description.trim(),
      });
      await chatStore.fetchRagSpaces();
      chatStore.selectRagSpace(data.data.id);
      ElMessage.success("空间已更新。");
    }
    spaceDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "保存空间失败，请稍后重试。"));
  } finally {
    spaceDialogLoading.value = false;
  }
}

async function deleteCurrentSpace() {
  if (!selectedSpace.value) {
    ElMessage.warning("请先选择一个 RAG 空间。");
    return;
  }

  try {
    await ElMessageBox.confirm(
      `将删除空间“${selectedSpace.value.name}”及其全部目录、文件和索引，此操作不可恢复。`,
      "删除空间",
      {
        type: "warning",
        confirmButtonText: "删除",
        cancelButtonText: "取消",
      },
    );
    const deletingSpaceId = selectedSpace.value.id;
    await ragSpaceApi.deleteSpace(deletingSpaceId);
    await chatStore.fetchRagSpaces();
    if (chatStore.ragSpaces.length > 0) {
      chatStore.selectRagSpace(chatStore.ragSpaces[0].id);
    } else {
      chatStore.clearSelectedRagSpace();
      treeData.value = [];
      currentNodeId.value = "";
      expandedKeys.value = [];
    }
    ElMessage.success("空间已删除。");
  } catch (error) {
    if (error === "cancel") return;
    ElMessage.error(resolveErrorMessage(error, "删除空间失败，请稍后重试。"));
  }
}

function openCreateFolderDialog(parentId?: string | null) {
  if (!chatStore.selectedRagSpaceId) {
    ElMessage.warning("请先选择一个 RAG 空间。");
    return;
  }
  folderForm.value = {
    parent_id: parentId ?? selectedFolder.value?.id ?? null,
    name: "",
  };
  folderDialogVisible.value = true;
}

const folderParentLabel = computed(() => {
  const parentId = folderForm.value.parent_id;
  if (!parentId) return "根目录";
  return nodeMap.value.get(parentId)?.full_path || "根目录";
});

async function submitCreateFolder() {
  if (!chatStore.selectedRagSpaceId) return;
  const name = folderForm.value.name.trim();
  if (!name) {
    ElMessage.warning("请输入文件夹名称。");
    return;
  }

  folderDialogLoading.value = true;
  try {
    const { data } = await ragSpaceApi.createNode(chatStore.selectedRagSpaceId, {
      parent_id: folderForm.value.parent_id,
      node_type: "folder",
      name,
    });
    folderDialogVisible.value = false;
    await Promise.all([chatStore.fetchRagSpaces(), loadTree(chatStore.selectedRagSpaceId)]);
    currentNodeId.value = data.data.id;
    if (data.data.parent_id) {
      updateExpandedKeys(data.data.parent_id, true);
    }
    ElMessage.success("文件夹已创建。");
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "创建文件夹失败，请稍后重试。"));
  } finally {
    folderDialogLoading.value = false;
  }
}

function openNodeDialog(node?: RagNode | null) {
  const target = node || selectedNode.value;
  if (!target) {
    ElMessage.warning("请先选择一个节点。");
    return;
  }
  nodeForm.value = {
    node_id: target.id,
    parent_id: target.parent_id || null,
    name: target.name,
  };
  nodeDialogVisible.value = true;
}

async function submitNodeDialog() {
  if (!chatStore.selectedRagSpaceId) return;
  const nodeId = nodeForm.value.node_id;
  const name = nodeForm.value.name.trim();
  if (!nodeId || !name) {
    ElMessage.warning("请填写完整的节点信息。");
    return;
  }

  nodeDialogLoading.value = true;
  try {
    const { data } = await ragSpaceApi.updateNode(chatStore.selectedRagSpaceId, nodeId, {
      parent_id: nodeForm.value.parent_id,
      name,
    });
    nodeDialogVisible.value = false;
    await Promise.all([chatStore.fetchRagSpaces(), loadTree(chatStore.selectedRagSpaceId)]);
    currentNodeId.value = data.data.id;
    if (data.data.parent_id) {
      updateExpandedKeys(data.data.parent_id, true);
    }
    ElMessage.success("节点已更新。");
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "更新节点失败，请稍后重试。"));
  } finally {
    nodeDialogLoading.value = false;
  }
}

async function deleteNode(node?: RagNode | null) {
  const target = node || selectedNode.value;
  if (!target || !chatStore.selectedRagSpaceId) {
    ElMessage.warning("请先选择一个节点。");
    return;
  }

  const dangerText =
    target.node_type === "folder"
      ? `将删除文件夹“${target.name}”及其全部子节点和索引，此操作不可恢复。`
      : `将删除文件“${target.name}”及其索引，此操作不可恢复。`;

  try {
    await ElMessageBox.confirm(dangerText, "删除节点", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await ragSpaceApi.deleteNode(chatStore.selectedRagSpaceId, target.id);
    await Promise.all([chatStore.fetchRagSpaces(), loadTree(chatStore.selectedRagSpaceId)]);
    if (currentNodeId.value === target.id) {
      currentNodeId.value = "";
    }
    ElMessage.success("节点已删除。");
  } catch (error) {
    if (error === "cancel") return;
    ElMessage.error(resolveErrorMessage(error, "删除节点失败，请稍后重试。"));
  }
}

function resolveUploadTarget(parentNodeId?: string | null) {
  if (typeof parentNodeId !== "undefined") return parentNodeId;
  return selectedFolder.value?.id ?? null;
}

function openUploadPicker(parentNodeId?: string | null) {
  if (!chatStore.selectedRagSpaceId) {
    ElMessage.warning("请先选择一个 RAG 空间。");
    return;
  }
  uploadTargetNodeId.value = resolveUploadTarget(parentNodeId);
  hiddenUploadInput.value?.click();
}

async function handleUploadChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!chatStore.selectedRagSpaceId || files.length === 0) {
    input.value = "";
    return;
  }

  uploadLoading.value = true;
  try {
    const response = uploadTargetNodeId.value
      ? await ragSpaceApi.uploadDocumentsToNode(chatStore.selectedRagSpaceId, uploadTargetNodeId.value, files)
      : await ragSpaceApi.uploadDocuments(chatStore.selectedRagSpaceId, files);
    await Promise.all([chatStore.fetchRagSpaces(), loadTree(chatStore.selectedRagSpaceId)]);
    const lastCreated = response.data.data.at(-1);
    if (lastCreated) {
      currentNodeId.value = lastCreated.id;
      if (lastCreated.parent_id) {
        updateExpandedKeys(lastCreated.parent_id, true);
      }
    }
    ElMessage.success(`已上传 ${files.length} 个文件。`);
  } catch (error) {
    ElMessage.error(resolveErrorMessage(error, "上传文件失败，请稍后重试。"));
  } finally {
    uploadLoading.value = false;
    uploadTargetNodeId.value = null;
    input.value = "";
  }
}

watch(
  () => chatStore.selectedRagSpaceId,
  async (spaceId) => {
    if (!spaceId) {
      treeData.value = [];
      currentNodeId.value = "";
      expandedKeys.value = [];
      return;
    }
    await loadTree(spaceId);
  },
  { immediate: true },
);

onMounted(async () => {
  await ensureSelectedSpace();
});
</script>

<template>
  <div class="page-shell !min-h-full !gap-4 !p-4">
    <section class="card-surface p-4">
      <div class="flex flex-col gap-4">
        <div class="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div class="space-y-1">
            <div class="text-xs font-semibold uppercase tracking-[0.24em] text-teal-700">RAG Space Manager</div>
            <h1 class="text-[30px] font-semibold tracking-tight text-zinc-950">RAG 空间目录树</h1>
            <p class="max-w-3xl text-sm text-zinc-500">集中管理空间、目录与知识文件，保持树结构清晰、可维护、可追踪。</p>
          </div>

          <div class="flex flex-wrap gap-2">
            <div class="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-600">
              文件夹 <span class="ml-1 font-semibold text-zinc-950">{{ stats.folderCount }}</span>
            </div>
            <div class="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-600">
              文件 <span class="ml-1 font-semibold text-zinc-950">{{ stats.fileCount }}</span>
            </div>
            <div class="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-600">
              Chunk <span class="ml-1 font-semibold text-zinc-950">{{ stats.chunkCount }}</span>
            </div>
            <div class="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-sm text-zinc-600">
              索引状态
              <el-tag class="ml-2" size="small" :type="statusTagType(stats.indexStatus)" effect="plain">
                {{ stats.indexStatus }}
              </el-tag>
            </div>
          </div>
        </div>

        <div class="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div class="flex min-w-0 flex-1 flex-col gap-2 md:flex-row md:items-center">
            <span class="shrink-0 text-sm text-zinc-500">当前空间</span>
            <el-select
              :model-value="chatStore.selectedRagSpaceId || ''"
              class="w-full max-w-[360px]"
              filterable
              placeholder="请选择 RAG 空间"
              @change="handleSpaceChange"
            >
              <el-option v-for="space in chatStore.ragSpaces" :key="space.id" :label="space.name" :value="space.id" />
            </el-select>
            <div class="min-w-0 text-sm text-zinc-400">
              当前目录：
              <span class="font-medium text-zinc-600">{{ currentFolderLabel }}</span>
            </div>
          </div>

          <div class="flex flex-wrap gap-2">
            <el-button type="primary" plain :icon="Plus" @click="openCreateSpaceDialog">新建空间</el-button>
            <el-button :icon="EditPen" :disabled="!selectedSpace" @click="openEditSpaceDialog">编辑空间</el-button>
            <el-button type="danger" plain :icon="Delete" :disabled="!selectedSpace" @click="deleteCurrentSpace">删除空间</el-button>
            <el-button :icon="Plus" :disabled="!selectedSpace" @click="openCreateFolderDialog()">新建文件夹</el-button>
            <el-button :icon="UploadFilled" :loading="uploadLoading" :disabled="!selectedSpace" @click="openUploadPicker()">
              上传到当前文件夹
            </el-button>
            <el-button :icon="Refresh" :loading="treeLoading" @click="refreshPage">刷新</el-button>
          </div>
        </div>
      </div>
    </section>

    <section class="grid min-h-0 flex-1 gap-4 grid-cols-[1fr_320px]">
      <div class="card-surface flex min-h-0 flex-col overflow-hidden">
        <div class="border-b border-zinc-200 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="text-lg font-semibold text-zinc-950">知识库目录树</h2>
              <p class="mt-1 text-sm text-zinc-500">在树上直接新增、上传、重命名、移动或删除节点。</p>
            </div>
            <el-tag v-if="selectedSpace" size="small" effect="plain">{{ selectedSpace.name }}</el-tag>
          </div>
        </div>

        <div v-if="treeError" class="border-b border-zinc-200 px-4 py-3">
          <el-alert :closable="false" show-icon type="error" :title="treeError" />
        </div>

        <div class="min-h-0 flex-1 overflow-auto px-3 py-3">
          <el-empty v-if="!selectedSpace" description="先创建或选择一个 RAG 空间" />
          <el-empty v-else-if="!treeLoading && treeData.length === 0" description="当前空间还没有文件夹或文件" />

          <el-tree
            v-else
            :data="treeData"
            node-key="id"
            highlight-current
            :current-node-key="currentNodeId"
            :default-expanded-keys="expandedKeys"
            :expand-on-click-node="false"
            :props="{ children: 'children', label: 'name' }"
            class="rag-tree"
            @node-click="selectNode"
            @node-expand="(_data: any, node: any) => updateExpandedKeys(node.data.id, true)"
            @node-collapse="(_data: any, node: any) => updateExpandedKeys(node.data.id, false)"
          >
            <template #default="{ data }">
              <div class="rag-node-row">
                <el-icon
                  class="rag-node-icon"
                  :class="data.node_type === 'folder' ? 'text-amber-600' : 'text-zinc-400'"
                >
                  <component :is="resolveNodeIcon(data)" />
                </el-icon>
                <span class="rag-node-name">{{ data.name }}</span>
                <div class="rag-node-actions" @click.stop>
                  <template v-if="data.node_type === 'folder'">
                    <el-button text size="small" :icon="Plus" @click="openCreateFolderDialog(data.id)" />
                    <el-button text size="small" :icon="UploadFilled" @click="openUploadPicker(data.id)" />
                  </template>
                  <el-button text size="small" :icon="EditPen" @click="openNodeDialog(data)" />
                  <el-button text size="small" type="danger" :icon="Delete" @click="deleteNode(data)" />
                </div>
              </div>
            </template>
          </el-tree>
        </div>
      </div>

      <aside class="card-surface flex min-h-0 flex-col overflow-hidden">
        <div class="border-b border-zinc-200 px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="text-lg font-semibold text-zinc-950">节点详情</h2>
              <p class="mt-1 text-sm text-zinc-500">这里仅展示信息，操作统一放在顶部和目录树中。</p>
            </div>
            <el-tag size="small" effect="plain">{{ detailTag }}</el-tag>
          </div>
        </div>

        <div class="min-h-0 flex-1 overflow-auto p-4">
          <div v-if="selectedSpace" class="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-4">
            <div class="text-xl font-semibold text-zinc-950">{{ detailTitle }}</div>
            <div class="mt-1 text-sm text-zinc-500">
              {{ selectedNode ? "选中节点的基础信息" : "当前空间的基础信息" }}
            </div>
          </div>

          <el-empty v-if="!selectedSpace" class="mt-8" description="暂无可查看的空间信息" />

          <div v-else class="mt-4 space-y-3">
            <div
              v-for="row in detailRows"
              :key="row.label"
              class="rounded-xl border border-zinc-200 bg-white px-4 py-3"
            >
              <div class="text-xs uppercase tracking-[0.16em] text-zinc-400">{{ row.label }}</div>
              <div class="mt-1 break-all text-sm font-medium text-zinc-800">{{ row.value }}</div>
            </div>
          </div>
        </div>
      </aside>
    </section>

    <input
      ref="hiddenUploadInput"
      class="hidden"
      type="file"
      multiple
      @change="handleUploadChange"
    />

    <el-dialog v-model="spaceDialogVisible" :title="spaceDialogTitle" width="460px">
      <el-form label-position="top">
        <el-form-item label="空间名称">
          <el-input v-model="spaceForm.name" maxlength="120" placeholder="请输入空间名称" />
        </el-form-item>
        <el-form-item label="空间说明">
          <el-input
            v-model="spaceForm.description"
            type="textarea"
            :rows="3"
            maxlength="1000"
            placeholder="可选，补充空间用途或范围"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="spaceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="spaceDialogLoading" @click="submitSpaceDialog">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="folderDialogVisible" title="新建文件夹" width="420px">
      <el-form label-position="top">
        <el-form-item label="父目录">
          <el-input :model-value="folderParentLabel" disabled />
        </el-form-item>
        <el-form-item label="文件夹名称">
          <el-input v-model="folderForm.name" maxlength="255" placeholder="请输入文件夹名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="folderDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="folderDialogLoading" @click="submitCreateFolder">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="nodeDialogVisible" title="重命名 / 移动节点" width="460px">
      <el-form label-position="top">
        <el-form-item label="节点名称">
          <el-input v-model="nodeForm.name" maxlength="255" placeholder="请输入新的节点名称" />
        </el-form-item>
        <el-form-item label="目标文件夹">
          <el-select v-model="nodeForm.parent_id" clearable class="w-full" placeholder="根目录">
            <el-option label="根目录" :value="null" />
            <el-option
              v-for="option in moveTargetOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="nodeDialogLoading" @click="submitNodeDialog">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rag-tree :deep(.el-tree-node__content) {
  height: 28px;
  padding: 0;
  border-radius: 4px;
}

.rag-tree :deep(.el-tree-node__content:hover) {
  background: rgb(243 244 246);
}

.rag-tree :deep(.el-tree-node:focus > .el-tree-node__content),
.rag-tree :deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: rgb(219 234 254);
}

.rag-tree :deep(.el-tree-node.is-current > .el-tree-node__content:hover) {
  background: rgb(209 224 250);
}

.rag-tree :deep(.el-tree-node__children) {
  overflow: visible;
}

.rag-tree :deep(.el-tree-node__expand-icon) {
  font-size: 14px;
  color: rgb(113 113 122);
  padding: 0 2px;
}

.rag-node-row {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px 0 0;
  min-width: 0;
}

.rag-node-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.rag-node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: rgb(24 24 27);
}

.rag-node-actions {
  display: none;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}

.rag-tree :deep(.el-tree-node__content:hover) .rag-node-actions {
  display: flex;
}

.rag-tree :deep(.el-tree-node.is-current > .el-tree-node__content) .rag-node-actions {
  display: flex;
}
</style>
