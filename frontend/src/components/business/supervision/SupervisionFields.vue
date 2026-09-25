<script setup lang="ts">
import {
  clearInvalidDependencies,
  fieldOptions,
  type FieldOption,
  type FieldSpec,
} from "./form-fields";
defineOptions({ name: "SupervisionFields" });
const props = defineProps<{
  modelValue: Record<string, any>;
  specs: FieldSpec[];
  options: Record<string, FieldOption[]>;
}>();
const emit = defineEmits<{ "update:modelValue": [Record<string, any>] }>();
function dependencyLabel(field: FieldSpec): string {
  return field.dependsOn === "product_sku_id" ? "请先选择产品" : "请先完成前置选择";
}
function availableOptions(field: FieldSpec): FieldOption[] {
  return fieldOptions(field, props.modelValue, props.options);
}
function isDisabled(field: FieldSpec): boolean {
  return !!field.dependsOn && !props.modelValue[field.dependsOn];
}
function set(key: string, value: any) {
  if (value && props.specs.find((x) => x.key === key)?.type === "date")
    value = new Date(value).toISOString();
  const next = clearInvalidDependencies(
    { ...props.modelValue, [key]: value },
    key,
    props.specs,
    props.options,
  );
  emit("update:modelValue", next);
}
function updateRow(key: string, index: number, value: Record<string, any>) {
  const rows = [...(props.modelValue[key] || [])];
  rows[index] = value;
  set(key, rows);
}
function add(f: FieldSpec) {
  const row: Record<string, any> = {};
  for (const field of f.fields || [])
    if (field.type === "array" || field.multiple) row[field.key] = [];
  set(f.key, [...(props.modelValue[f.key] || []), row]);
}
</script>
<template>
  <div class="supervision-fields">
    <template v-for="f in specs" :key="f.key">
      <section v-if="f.type === 'array'" class="repeat-section">
        <div class="repeat-heading">
          <strong>{{ f.label }}</strong
          ><el-button size="small" @click="add(f)">添加</el-button>
        </div>
        <el-empty v-if="!modelValue[f.key]?.length" description="尚未登记" :image-size="32" />
        <div v-for="(row, index) in modelValue[f.key] || []" :key="index" class="repeat-row">
          <div class="repeat-heading">
            <span>{{ f.label }} {{ index + 1 }}</span
            ><el-button
              size="small"
              type="danger"
              text
              @click="
                set(
                  f.key,
                  modelValue[f.key].filter((_: any, i: number) => i !== index),
                )
              "
              >移除</el-button
            >
          </div>
          <SupervisionFields
            :model-value="row"
            :specs="f.fields || []"
            :options="options"
            @update:model-value="updateRow(f.key, index, $event)"
          />
        </div>
      </section>
      <el-form-item v-else :label="f.label" :required="f.required">
        <el-select
          v-if="f.type === 'select'"
          :model-value="modelValue[f.key]"
          :multiple="f.multiple"
          :disabled="isDisabled(f)"
          filterable
          clearable
          :placeholder="isDisabled(f) ? dependencyLabel(f) : '请选择'"
          @update:model-value="set(f.key, $event)"
        >
          <el-option
            v-for="option in availableOptions(f)"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
        <el-date-picker
          v-else-if="f.type === 'date'"
          :model-value="modelValue[f.key]"
          type="datetime"
          value-format="YYYY-MM-DDTHH:mm:ss"
          placeholder="选择时间"
          @update:model-value="set(f.key, $event)"
        />
        <el-input-number
          v-else-if="f.type === 'number'"
          :model-value="modelValue[f.key]"
          :controls="false"
          @update:model-value="set(f.key, $event)"
        />
        <el-switch
          v-else-if="f.type === 'boolean'"
          :model-value="Boolean(modelValue[f.key])"
          active-text="启用"
          inactive-text="关闭"
          @update:model-value="set(f.key, $event)"
        />
        <el-input
          v-else-if="f.type === 'strings'"
          :model-value="(modelValue[f.key] || []).join('，')"
          @update:model-value="
            set(
              f.key,
              $event
                .split(/[,，]/)
                .map((x: string) => x.trim())
                .filter(Boolean),
            )
          "
        />
        <el-input
          v-else
          :model-value="modelValue[f.key]"
          :type="f.type === 'textarea' ? 'textarea' : 'text'"
          :rows="3"
          @update:model-value="set(f.key, $event)"
        />
      </el-form-item>
    </template>
  </div>
</template>
<style scoped>
.supervision-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 18px;
}
.el-select,
.el-date-editor,
.el-input-number {
  width: 100%;
}
.repeat-section {
  grid-column: 1 / -1;
  border-top: 1px solid var(--el-border-color-light);
  padding: 14px 0;
}
.repeat-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.repeat-row {
  padding: 14px;
  margin: 10px 0;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
@media (max-width: 640px) {
  .supervision-fields {
    grid-template-columns: 1fr;
  }
}
</style>
