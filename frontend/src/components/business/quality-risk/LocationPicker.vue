<script setup lang="ts">
import { computed, ref } from "vue";
import areaData from "china-area-data";
import { Aim } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import type { LocationRef } from "@/types/quality-risk.types";

const props = defineProps<{ modelValue: LocationRef }>();
const emit = defineEmits<{ "update:modelValue": [LocationRef] }>();
const locating = ref(false);

function children(code: string) {
  return Object.entries(areaData[code] || {}).map(([value, label]) => ({
    value,
    label,
    children: Object.keys(areaData[value] || {}).length ? children(value) : undefined,
  }));
}

const options = children("86");
const selected = computed(() =>
  [props.modelValue.province_code, props.modelValue.city_code, props.modelValue.district_code].filter(
    Boolean,
  ),
);

function update(patch: Partial<LocationRef>) {
  emit("update:modelValue", { ...props.modelValue, ...patch });
}

function regionChanged(value: string[]) {
  const names = value.map((code, index) => {
    const parent = index === 0 ? "86" : value[index - 1];
    return areaData[parent]?.[code] || "";
  });
  update({
    province_code: value[0],
    city_code: value[1],
    district_code: value[2],
    formatted_address: props.modelValue.formatted_address || names.join(" "),
    location_method: "manual",
  });
}

function locate() {
  if (!navigator.geolocation) {
    ElMessage.warning("当前浏览器不支持定位，请手动选择地区");
    return;
  }
  locating.value = true;
  navigator.geolocation.getCurrentPosition(
    (position) => {
      update({
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
        accuracy_meters: position.coords.accuracy,
        location_method: "browser",
      });
      locating.value = false;
      ElMessage.success("已取得大致位置，请核对并补充地区和地址");
    },
    () => {
      locating.value = false;
      ElMessage.warning("未取得定位权限，可继续手动选择地区");
    },
    { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 },
  );
}
</script>

<template>
  <div class="location-picker">
    <div class="location-row">
      <el-cascader
        :model-value="selected"
        :options="options"
        clearable
        filterable
        placeholder="选择省、市、区县"
        @update:model-value="regionChanged"
      />
      <el-button :icon="Aim" :loading="locating" @click="locate">定位到当前位置</el-button>
    </div>
    <el-input
      :model-value="modelValue.formatted_address"
      placeholder="补充道路、园区、建筑或实验室位置"
      @update:model-value="update({ formatted_address: $event, location_method: 'manual' })"
    />
    <p v-if="modelValue.latitude != null && modelValue.longitude != null">
      坐标 {{ modelValue.longitude.toFixed(5) }}, {{ modelValue.latitude.toFixed(5) }}
      <span v-if="modelValue.accuracy_meters">· 约 {{ Math.round(modelValue.accuracy_meters) }} 米</span>
    </p>
  </div>
</template>

<style scoped>
.location-picker {
  display: grid;
  gap: 10px;
}
.location-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
}
.el-cascader {
  width: 100%;
}
p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
@media (max-width: 640px) {
  .location-row {
    grid-template-columns: 1fr;
  }
  .location-row :deep(.el-button) {
    min-height: 44px;
  }
}
</style>
