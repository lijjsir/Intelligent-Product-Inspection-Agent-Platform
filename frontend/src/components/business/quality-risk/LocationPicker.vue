<script setup lang="ts">
import { computed, ref } from "vue";
import areaData from "china-area-data";
import { Aim } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { qualityRiskApi } from "@/api/quality-risk.api";
import { extractApiErrorMessage } from "@/api/http";
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

function normalized(value: string) {
  return String(value || "")
    .replace(/特别行政区|维吾尔自治区|壮族自治区|回族自治区|自治区|省|市|区|县/g, "")
    .replace(/\s+/g, "");
}

function findCode(parentCode: string, name: string) {
  const target = normalized(name);
  if (!target) return "";
  return (
    Object.entries(areaData[parentCode] || {}).find(([, label]) => {
      const candidate = normalized(label);
      return candidate === target || candidate.includes(target) || target.includes(candidate);
    })?.[0] || ""
  );
}

function resolveRegionCodes(province: string, city: string, district: string) {
  const provinceCode = findCode("86", province);
  if (!provinceCode) return {};
  const municipality = ["北京", "天津", "上海", "重庆"].includes(normalized(province));
  let cityCode = municipality ? "" : findCode(provinceCode, city);
  if (!cityCode && (municipality || normalized(city) === normalized(province))) {
    cityCode = Object.keys(areaData[provinceCode] || {})[0] || "";
  }
  const districtCode = cityCode
    ? findCode(cityCode, municipality ? city || district : district)
    : "";
  return {
    province_code: provinceCode,
    city_code: cityCode || undefined,
    district_code: districtCode || undefined,
  };
}

function locate() {
  if (!navigator.geolocation) {
    ElMessage.warning("当前浏览器不支持定位，请手动选择地区");
    return;
  }
  locating.value = true;
  navigator.geolocation.getCurrentPosition(
    async (position) => {
      const coordinates = {
        longitude: position.coords.longitude,
        latitude: position.coords.latitude,
        accuracy_meters: position.coords.accuracy,
        location_method: "browser" as const,
      };
      try {
        const response = await qualityRiskApi.reverseGeocode(
          position.coords.latitude,
          position.coords.longitude,
        );
        const address = response.data.data;
        update({
          ...coordinates,
          ...resolveRegionCodes(address.province, address.city, address.district),
          formatted_address: address.formatted_address,
        });
        ElMessage.success("已根据当前位置填写地区和详细地址，请核对后保存");
      } catch (error) {
        update(coordinates);
        ElMessage.warning(
          extractApiErrorMessage(error, "当前位置已取得，但地址解析失败，请手动选择地区"),
        );
      } finally {
        locating.value = false;
      }
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
      <el-button :icon="Aim" :loading="locating" @click="locate">定位并填写地址</el-button>
    </div>
    <el-input
      :model-value="modelValue.formatted_address"
      placeholder="补充道路、园区、建筑或实验室位置"
      @update:model-value="update({ formatted_address: $event, location_method: 'manual' })"
    />
    <p v-if="modelValue.location_method === 'browser'">
      已由当前位置填入<span v-if="modelValue.accuracy_meters"> · 定位精度约 {{ Math.round(modelValue.accuracy_meters) }} 米</span>
      · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap contributors</a>
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
p a {
  color: inherit;
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
