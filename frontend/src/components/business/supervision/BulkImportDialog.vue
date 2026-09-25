<script setup lang="ts">
import { ref } from "vue";
import { ElMessage, type UploadFile } from "element-plus";
import { http } from "@/api/http";
const props = defineProps<{ kind: string; modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; imported: [] }>();
const file = ref<File | null>(null),
  mapping = ref<Record<string, string>>({}),
  preview = ref<any>(null),
  busy = ref(false);
const labels: Record<string, string> = {
  code: "记录编号",
  name: "记录名称",
  parent_id: "上级地区编号",
  parent_code: "上级地区编码",
  dictionary_version: "字典版本",
  description: "问题描述",
  occurred_at: "发生时间",
  source_type: "来源类型",
  source_id: "来源编号",
  source_text: "原始内容",
  enterprise_id: "企业编号",
  product_sku_id: "产品编号",
  batch_id: "批次编号",
  inspection_standard_id: "标准编号",
  complaint_region_id: "投诉地区编号",
  production_region_id: "生产地区编号",
  sampling_region_id: "抽样地区编号",
  product_category: "产品类别",
};
function columns() {
  return props.kind === "regions"
    ? ["code", "name", "parent_code", "dictionary_version"]
    : [
        "code",
        "name",
        "description",
        "occurred_at",
        "source_id",
        "source_text",
        "source_type",
        "product_category",
        "enterprise_id",
        "product_sku_id",
        "batch_id",
        "inspection_standard_id",
        "complaint_region_id",
        "production_region_id",
        "sampling_region_id",
      ];
}
function changed(upload: UploadFile) {
  file.value = upload.raw || null;
  preview.value = null;
}
async function check() {
  if (!file.value) return;
  busy.value = true;
  try {
    const data = new FormData();
    data.append("file", file.value);
    data.append("mapping", JSON.stringify(mapping.value));
    preview.value = (await http.post<any>(`/v1/${props.kind}/imports/preview`, data)).data.data;
  } finally {
    busy.value = false;
  }
}
async function confirm() {
  if (!preview.value) return;
  busy.value = true;
  try {
    const result = (
      await http.post<any>(
        `/v1/${props.kind}/imports/confirm`,
        {},
        { params: { preview_id: preview.value.preview_id } },
      )
    ).data.data;
    ElMessage.success(`已导入${result.accepted}条记录`);
    emit("update:modelValue", false);
    emit("imported");
    preview.value = null;
  } finally {
    busy.value = false;
  }
}
function template() {
  const blob = new Blob(["\ufeff" + columns().join(",") + "\n"], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = props.kind === "regions" ? "地区字典模板.csv" : "风险线索模板.csv";
  anchor.click();
  URL.revokeObjectURL(url);
}
</script>
<template>
  <el-dialog
    :model-value="modelValue"
    :title="kind === 'regions' ? '导入地区字典' : '导入风险线索'"
    width="min(850px,94vw)"
    @update:model-value="emit('update:modelValue', $event)"
    ><div class="actions">
      <el-upload :auto-upload="false" :limit="1" accept=".csv,.xlsx" :on-change="changed"
        ><el-button>选择文件</el-button></el-upload
      ><el-button @click="template">下载模板</el-button
      ><el-button :loading="busy" :disabled="!file" @click="check">校验与预览</el-button>
    </div>
    <el-collapse
      ><el-collapse-item title="文件列名映射"
        ><el-form label-position="top" class="mapping"
          ><el-form-item v-for="column in columns()" :key="column" :label="labels[column]"
            ><el-input
              v-model="mapping[column]"
              :placeholder="column" /></el-form-item></el-form></el-collapse-item></el-collapse
    ><template v-if="preview"
      ><p>有效 {{ preview.valid_count }} 行，错误 {{ preview.errors.length }} 行</p>
      <el-table v-if="preview.errors.length" :data="preview.errors"
        ><el-table-column prop="row" label="行号" width="80" /><el-table-column
          prop="message"
          label="需要修正" /></el-table
      ><el-table :data="preview.rows"
        ><el-table-column prop="code" label="编号" /><el-table-column
          prop="name"
          label="名称" /></el-table></template
    ><template #footer
      ><el-button @click="emit('update:modelValue', false)">取消</el-button
      ><el-button type="primary" :loading="busy" :disabled="!preview?.can_confirm" @click="confirm"
        >确认导入</el-button
      ></template
    ></el-dialog
  >
</template>
<style scoped>
.actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.mapping {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 640px) {
  .mapping {
    grid-template-columns: 1fr;
  }
}
</style>
