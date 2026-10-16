<script setup lang="ts">
import { ref } from "vue";
import PermissionMatrix from "@/components/business/PermissionMatrix.vue";

const activeTab = ref("roles");
</script>

<template>
  <div class="flex flex-col gap-5">
    <header>
      <h2 class="text-2xl font-bold text-zinc-900">权限管理</h2>
      <p class="mt-2 text-sm text-zinc-500">先定义角色能做什么，再调整每个人的授权。</p>
    </header>
    <div class="card-surface p-4">
      <el-tabs v-model="activeTab" aria-label="权限管理">
        <el-tab-pane label="角色权限" name="roles" />
        <el-tab-pane label="用户授权" name="users" />
      </el-tabs>
      <PermissionMatrix :mode="activeTab" />
    </div>
  </div>
</template>
