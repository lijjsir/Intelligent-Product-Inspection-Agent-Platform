<script setup lang="ts">
import { computed, defineAsyncComponent, ref } from "vue";
import { useAuthStore } from "@/stores/auth.store";
const IntakeView = defineAsyncComponent(() => import("@/views/quality-risk/QualityDataIntakeView.vue"));
const auth = useAuthStore();
const opened = ref(false);
const allowed = computed(() => auth.primaryRole === "user" && auth.hasPermission("quality_material_submit"));
</script>
<template>
  <el-button v-if="allowed" plain @click="opened = true">提交质量资料</el-button>
  <el-dialog v-model="opened" class="material-intake-dialog" top="3vh" title="提交与查看本人质量资料" width="min(1080px,96vw)" destroy-on-close append-to-body>
    <IntakeView v-if="opened" embedded />
  </el-dialog>
</template>

<style>
.material-intake-dialog.el-dialog{max-height:94dvh;background:#fff!important;overflow:hidden}.material-intake-dialog .el-dialog__body{max-height:calc(94dvh - 100px);overflow:auto}
</style>
