<script setup lang="ts" generic="TItem extends { id: string; name: string; description?: string | null; status?: string | null }">
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import AlgoWorkspaceHero from "@/components/business/algo/AlgoWorkspaceHero.vue";
import type { AlgoListQuery } from "@/types/algo-workspace.types";

const props = defineProps<{
  title: string;
  subtitle: string;
  store: {
    items: TItem[];
    total: number;
    loading: boolean;
    current: TItem | null;
    fetchList: (query: AlgoListQuery) => Promise<any>;
    fetchOne: (id: string) => Promise<any>;
    createOne: (payload: any) => Promise<any>;
    updateOne?: (id: string, payload: any) => Promise<any>;
    removeOne: (id: string) => Promise<void>;
    launchOne?: (id: string) => Promise<any>;
    cancelOne?: (id: string) => Promise<any>;
    detailPath?: (id: string) => string;
  };
  buildPayload: (form: { name: string; description: string; config_json: string }) => Record<string, unknown>;
  populateForm?: (item: TItem) => void;
  detailDescription?: (item: TItem | null) => string;
  showLaunch?: boolean;
}>();

const router = useRouter();
const drawerOpen = ref(false);
const editingId = ref("");
const query = reactive<AlgoListQuery>({
  page: 1,
  size: 20,
  keyword: "",
  status: "",
});
const form = reactive({
  name: "",
  description: "",
  config_json: "{}",
});

function resetForm() {
  editingId.value = "";
  form.name = "";
  form.description = "";
  form.config_json = "{}";
}

function openCreate() {
  resetForm();
  drawerOpen.value = true;
}

function openEdit(row: any) {
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  form.config_json = JSON.stringify(row.config_json || {}, null, 2);
  props.populateForm?.(row);
  drawerOpen.value = true;
}

async function load() {
  await props.store.fetchList(query);
}

async function submit() {
  try {
    const payload = props.buildPayload(form);
    if (editingId.value && props.store.updateOne) {
      await props.store.updateOne(editingId.value, payload);
      ElMessage.success("已更新");
    } else {
      await props.store.createOne(payload);
      ElMessage.success("已创建");
    }
    drawerOpen.value = false;
    await load();
  } catch (error) {
    if (error instanceof SyntaxError) {
      ElMessage.error("配置 JSON 格式不正确");
      return;
    }
    if (error instanceof Error && error.message === "missing-required-ref") {
      ElMessage.warning("请先补全必填的关联资源");
      return;
    }
    throw error;
  }
}

async function remove(id: string) {
  await ElMessageBox.confirm("确定删除该记录吗？", "删除确认", {
    type: "warning",
    confirmButtonText: "删除",
    cancelButtonText: "取消",
  });
  await props.store.removeOne(id);
  ElMessage.success("已删除");
  await load();
}

async function openDetail(id: string) {
  const detailPath = props.store.detailPath?.(id);
  if (detailPath) {
    await router.push(detailPath);
    return;
  }
  await props.store.fetchOne(id);
}

async function launch(id: string) {
  if (!props.store.launchOne) return;
  await props.store.launchOne(id);
  ElMessage.success("已启动");
  await load();
}

async function cancel(id: string) {
  if (!props.store.cancelOne) return;
  await props.store.cancelOne(id);
  ElMessage.success("已取消");
  await load();
}

onMounted(load);
</script>

<template>
  <div class="algo-page">
    <AlgoWorkspaceHero :title="title" :description="subtitle">
      <template #actions>
        <el-button type="primary" @click="openCreate">新增</el-button>
      </template>
    </AlgoWorkspaceHero>

    <section class="card-surface p-4">
      <div class="flex gap-3 flex-wrap">
        <el-input v-model="query.keyword" placeholder="搜索名称" class="!w-[240px]" clearable />
        <el-select v-model="query.status" clearable placeholder="状态" class="!w-[180px]">
          <el-option label="draft" value="draft" />
          <el-option label="queued" value="queued" />
          <el-option label="running" value="running" />
          <el-option label="completed" value="completed" />
          <el-option label="failed" value="failed" />
          <el-option label="cancelled" value="cancelled" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>

      <el-table :data="store.items" v-loading="store.loading" class="mt-4">
        <el-table-column prop="name" label="名称" min-width="200" />
        <el-table-column prop="description" label="描述" min-width="260" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row.id)">详情</el-button>
            <el-button v-if="['draft', 'failed'].includes(row.status)" link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="showLaunch && ['draft', 'failed'].includes(row.status)" link type="success" @click="launch(row.id)">启动</el-button>
            <el-button v-if="showLaunch && ['queued', 'running'].includes(row.status)" link type="warning" @click="cancel(row.id)">取消</el-button>
            <el-button link type="danger" @click="remove(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="drawerOpen" :title="editingId ? `编辑${title}` : `新增${title}`" size="520px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="4" /></el-form-item>
        <slot name="form-extra" :form="form" :editing-id="editingId" />
        <el-form-item label="配置 JSON"><el-input v-model="form.config_json" type="textarea" :rows="10" /></el-form-item>
      </el-form>
      <template #footer>
        <div class="flex justify-end gap-3">
          <el-button @click="drawerOpen = false">取消</el-button>
          <el-button type="primary" @click="submit">保存</el-button>
        </div>
      </template>
    </el-drawer>

  </div>
</template>

<style scoped>
.algo-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
